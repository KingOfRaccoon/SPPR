import { getSupplier } from '../data/presets';
import {
  computeEffectiveLeadDays,
  computeItemCostKrub,
  computeOrderSummary,
  computeRequiredTargetStock
} from './replenishmentMetrics';
import type {
  BackupChannelMode,
  CostOfInactionInfo,
  SkuItem,
  StochasticBufferMetrics,
  SupplierId,
  SupplierNegotiationImpact,
  TransitDelayDays,
  WarehouseConstraints,
  WaveFinancialSummary,
  WhatIfScenarioBranch
} from '../types/domain';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function computeStochasticBuffer(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): StochasticBufferMetrics {
  const sup = getSupplier(item.supplierId);
  const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);

  const serviceLevelPct = item.priority === 'critical' ? 98.5 : 92.0;
  const zScore = item.priority === 'critical' ? 2.17 : 1.41;

  const r = clamp(sup.reliabilityPct / 100, 0.5, 0.995);
  const sigmaLeadDays = Number((leadDays * Math.sqrt((1 - r) / r)).toFixed(1));

  const cv = item.priority === 'critical' ? 0.30 : 0.20;
  const sigmaDemand = Number((item.dailyDemand * cv).toFixed(1));

  const variance = leadDays * sigmaDemand ** 2 + item.dailyDemand ** 2 * sigmaLeadDays ** 2;
  const stochasticSafetyUnits = Math.round(zScore * Math.sqrt(variance));
  const stochasticSafetyDays = Number(
    (stochasticSafetyUnits / Math.max(1, item.dailyDemand)).toFixed(1)
  );
  const stochasticRop = Math.round(item.dailyDemand * leadDays + stochasticSafetyUnits);
  const staticSafetyUnits = Math.round(item.dailyDemand * item.safetyDays);
  const deltaUnits = stochasticSafetyUnits - staticSafetyUnits;

  return {
    serviceLevelPct,
    zScore,
    sigmaLeadDays,
    sigmaDemand,
    stochasticSafetyUnits,
    stochasticSafetyDays,
    stochasticRop,
    staticSafetyUnits,
    deltaUnits
  };
}

export function computeCostOfInaction(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): CostOfInactionInfo {
  const stoch = computeStochasticBuffer(item, transitDelayDays, backupChannel);
  const target = Math.max(
    computeRequiredTargetStock(item, transitDelayDays, backupChannel),
    stoch.stochasticRop
  );
  const covered = item.currentStock + item.orderQty;
  const shortfallUnits = Math.max(0, target - covered);
  const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);

  let stockoutProb: number;
  if (shortfallUnits === 0) {
    stockoutProb = clamp(0.04 + (1 - stoch.serviceLevelPct / 100) * 0.5, 0.01, 0.15);
  } else if (covered < leadDays * item.dailyDemand) {
    stockoutProb = clamp(0.70 + (shortfallUnits / Math.max(1, item.dailyDemand)) * 0.03, 0.70, 0.92);
  } else {
    stockoutProb = clamp(
      0.15 + (shortfallUnits / Math.max(1, stoch.stochasticSafetyUnits + 1)) * 0.55,
      0.15,
      0.80
    );
  }

  const dailyDowntimeRate = item.priority === 'critical' ? 180 : 38;
  const expectedDeficitDays = (shortfallUnits / Math.max(1, item.dailyDemand)) * stockoutProb;
  const downtimeKrub = Number((dailyDowntimeRate * expectedDeficitDays).toFixed(1));

  const orderValueKrub = item.orderQty * item.unitCostKrub;
  const expressDeltaKrub =
    shortfallUnits > 0 ? Number(Math.max(14, orderValueKrub * 0.075).toFixed(1)) : 0;

  const otifPenaltyKrub = Number(
    (shortfallUnits * item.unitCostKrub * 0.12 * stockoutProb).toFixed(1)
  );

  const riskKrub = Number((downtimeKrub + expressDeltaKrub + otifPenaltyKrub).toFixed(1));

  return {
    riskKrub,
    stockoutProbPct: Math.round(stockoutProb * 100),
    shortfallUnits,
    downtimeKrub,
    expressDeltaKrub,
    otifPenaltyKrub
  };
}

export function computeWaveFinancialSummary(
  items: SkuItem[],
  constraints: WarehouseConstraints,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): WaveFinancialSummary {
  let totalCostOfInactionKrub = 0;
  let atRiskSkuCount = 0;
  let workingCapitalKrub = 0;
  let discreteRampSlots = 0;
  let totalFloatPallets = 0;

  for (const item of items) {
    const coi = computeCostOfInaction(item, transitDelayDays, backupChannel);
    totalCostOfInactionKrub += coi.riskKrub;
    if (coi.stockoutProbPct > 15) atRiskSkuCount += 1;
    workingCapitalKrub += item.orderQty * item.unitCostKrub;

    const pallets = item.orderQty / Math.max(1, item.unitsPerPallet);
    discreteRampSlots += Math.ceil(pallets);
    totalFloatPallets += pallets;
  }

  const summary = computeOrderSummary(items, constraints, transitDelayDays, backupChannel);
  const estAnnualWcSavingsKrub = Number((workingCapitalKrub * 12 * 0.22 * 0.16).toFixed(1));
  const tcoWaveKrub = Number((summary.totalBudgetKrub + totalCostOfInactionKrub).toFixed(1));

  return {
    totalCostOfInactionKrub: Number(totalCostOfInactionKrub.toFixed(1)),
    atRiskSkuCount,
    workingCapitalKrub: Number(workingCapitalKrub.toFixed(1)),
    discreteRampSlots,
    floatPallets: Number(totalFloatPallets.toFixed(1)),
    estAnnualWcSavingsKrub,
    tcoWaveKrub
  };
}

export function buildWhatIfBranch(
  items: SkuItem[],
  constraints: WarehouseConstraints,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): WhatIfScenarioBranch {
  const summary = computeOrderSummary(items, constraints, transitDelayDays, backupChannel);
  const financials = computeWaveFinancialSummary(
    items,
    constraints,
    transitDelayDays,
    backupChannel
  );
  return {
    totalPallets: summary.totalPallets,
    totalWeightKg: summary.totalWeightKg,
    totalBudgetKrub: summary.totalBudgetKrub,
    stockoutRiskCount: summary.stockoutRiskCount,
    overLimitCount: summary.overLimitCount,
    totalCostOfInactionKrub: financials.totalCostOfInactionKrub,
    atRiskSkuCount: financials.atRiskSkuCount,
    isFeasible: summary.isFeasible
  };
}

export function computeSupplierNegotiationImpact(
  sku: SkuItem,
  candidateSupplierId: SupplierId,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): SupplierNegotiationImpact {
  const currentCost = computeItemCostKrub(sku, backupChannel);
  const currentStoch = computeStochasticBuffer(sku, transitDelayDays, backupChannel);
  const currentCoi = computeCostOfInaction(sku, transitDelayDays, backupChannel);

  const candidateSku: SkuItem = { ...sku, supplierId: candidateSupplierId };
  const candidateCost = computeItemCostKrub(candidateSku, backupChannel);
  const candidateStoch = computeStochasticBuffer(candidateSku, transitDelayDays, backupChannel);
  const candidateCoi = computeCostOfInaction(candidateSku, transitDelayDays, backupChannel);

  const lineCostDeltaKrub = Number((candidateCost - currentCost).toFixed(1));
  const sigmaBufferDeltaUnits = candidateStoch.stochasticSafetyUnits - currentStoch.stochasticSafetyUnits;
  const riskDeltaKrub = Number((candidateCoi.riskKrub - currentCoi.riskKrub).toFixed(1));
  const netImpactKrub = Number((-(lineCostDeltaKrub + riskDeltaKrub)).toFixed(1));

  let verdict: string;
  if (candidateSupplierId === sku.supplierId) {
    verdict = 'Текущий контрагент позиции, параметры зафиксированы';
  } else if (netImpactKrub > 0) {
    verdict = `Выгода перехода +${netImpactKrub.toFixed(1)} тыс. ₽ по TCO`;
  } else if (netImpactKrub < 0) {
    verdict = `Удорожание TCO на ${Math.abs(netImpactKrub).toFixed(1)} тыс. ₽, нужен дисконт`;
  } else {
    verdict = 'Паритет совокупной стоимости TCO';
  }

  return {
    currentSupplierId: sku.supplierId,
    candidateSupplierId,
    lineCostDeltaKrub,
    sigmaBufferDeltaUnits,
    riskDeltaKrub,
    netImpactKrub,
    verdict
  };
}
