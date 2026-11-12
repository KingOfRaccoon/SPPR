import { BACKUP_CHANNELS, getSupplier, getSupplierBatchStep } from '../data/presets';
import type {
  BackupChannelMode,
  BalanceSnapshotMetrics,
  OrderCapacitySummary,
  SkuItem,
  TransitDelayDays,
  WarehouseConstraints
} from '../types/domain';

export function computeEffectiveLeadDays(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): number {
  const sup = getSupplier(item.supplierId);
  const ch = BACKUP_CHANNELS[backupChannel] || BACKUP_CHANNELS.direct_rail;
  return Math.max(2, sup.leadDays + transitDelayDays + ch.leadDeltaDays);
}

export function computeLineUnitCostKrub(
  item: SkuItem,
  backupChannel: BackupChannelMode
): number {
  const sup = getSupplier(item.supplierId);
  const ch = BACKUP_CHANNELS[backupChannel] || BACKUP_CHANNELS.direct_rail;
  const raw = item.unitCostKrub * sup.priceFactor * (1 + ch.costSurchargePct / 100);
  return Number(raw.toFixed(2));
}

export function computeRequiredTargetStock(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): number {
  const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
  const coverDays = leadDays + item.safetyDays;
  return Math.max(item.reorderPoint, Math.round(item.dailyDemand * coverDays));
}

export function isSkuAtStockoutRisk(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): boolean {
  const target = computeRequiredTargetStock(item, transitDelayDays, backupChannel);
  return item.currentStock + item.orderQty < target;
}

export function computeRecommendedOrderQty(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): number {
  const step = getSupplierBatchStep(item.supplierId);
  const target = computeRequiredTargetStock(item, transitDelayDays, backupChannel);
  const gap = Math.max(step, target - item.currentStock);
  return Math.ceil(gap / step) * step;
}

export interface DaysOfCoverInfo {
  runoutDays: number;
  totalCoverDays: number;
  leadDays: number;
  targetCoverDays: number;
  status: 'deficit' | 'healthy' | 'overstock';
}

export function computeDaysOfCover(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): DaysOfCoverInfo {
  const demand = Math.max(1, item.dailyDemand);
  const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
  const runoutDays = Number((item.currentStock / demand).toFixed(1));
  const totalCoverDays = Number(((item.currentStock + item.orderQty) / demand).toFixed(1));
  const targetCoverDays = leadDays + item.safetyDays;
  const atRisk = isSkuAtStockoutRisk(item, transitDelayDays, backupChannel);
  let status: DaysOfCoverInfo['status'] = 'healthy';
  if (atRisk) status = 'deficit';
  else if (totalCoverDays > targetCoverDays + 20) status = 'overstock';
  return {
    runoutDays,
    totalCoverDays,
    leadDays,
    targetCoverDays,
    status
  };
}

export interface SawtoothVertex {
  day: number;
  stock: number;
  phase: 'before' | 'arrival_low' | 'arrival_peak' | 'after';
}

export interface SawtoothProjection {
  horizonDays: number;
  leadDays: number;
  safetyUnits: number;
  reorderPoint: number;
  preArrivalStock: number;
  arrivalPeakStock: number;
  endStock: number;
  maxStock: number;
  stockoutGapDays: number;
  vertices: SawtoothVertex[];
}

export function computeSawtoothProjection(
  item: SkuItem,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode,
  horizonDays = 21
): SawtoothProjection {
  const demand = Math.max(1, item.dailyDemand);
  const leadDays = Math.min(
    horizonDays - 1,
    computeEffectiveLeadDays(item, transitDelayDays, backupChannel)
  );
  const safetyUnits = Math.round(demand * item.safetyDays);
  const rawAtArrival = item.currentStock - leadDays * demand;
  const preArrivalStock = Math.max(0, rawAtArrival);
  const stockoutGapDays =
    rawAtArrival < 0 ? Number((Math.abs(rawAtArrival) / demand).toFixed(1)) : 0;
  const arrivalPeakStock = preArrivalStock + item.orderQty;
  const vertices: SawtoothVertex[] = [];

  for (let d = 0; d < leadDays; d++) {
    vertices.push({
      day: d,
      stock: Math.max(0, Math.round(item.currentStock - d * demand)),
      phase: 'before'
    });
  }
  vertices.push({
    day: leadDays,
    stock: Math.round(preArrivalStock),
    phase: 'arrival_low'
  });
  vertices.push({
    day: leadDays,
    stock: Math.round(arrivalPeakStock),
    phase: 'arrival_peak'
  });
  for (let d = leadDays + 1; d <= horizonDays; d++) {
    vertices.push({
      day: d,
      stock: Math.max(0, Math.round(arrivalPeakStock - (d - leadDays) * demand)),
      phase: 'after'
    });
  }

  const endStock = vertices[vertices.length - 1]?.stock ?? 0;
  const maxStock = Math.max(
    item.currentStock,
    arrivalPeakStock,
    item.reorderPoint,
    safetyUnits,
    20
  );

  return {
    horizonDays,
    leadDays,
    safetyUnits,
    reorderPoint: item.reorderPoint,
    preArrivalStock: Math.round(preArrivalStock),
    arrivalPeakStock: Math.round(arrivalPeakStock),
    endStock,
    maxStock,
    stockoutGapDays,
    vertices
  };
}

export function computeItemPallets(item: SkuItem): number {
  return Number((item.orderQty / Math.max(1, item.unitsPerPallet)).toFixed(1));
}

export function computeItemWeightKg(item: SkuItem): number {
  return Math.round(item.orderQty * item.unitWeightKg);
}

export function computeItemCostKrub(
  item: SkuItem,
  backupChannel: BackupChannelMode
): number {
  const unitCost = computeLineUnitCostKrub(item, backupChannel);
  return Number((item.orderQty * unitCost).toFixed(1));
}

export function computeOrderSummary(
  items: SkuItem[],
  constraints: WarehouseConstraints,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): OrderCapacitySummary {
  const effectivePalletLimit = Math.max(10, constraints.maxPallets - constraints.reserveGatePallets);
  let totalPalletsRaw = 0;
  let totalWeightKg = 0;
  let totalBudgetRaw = 0;
  let stockoutRiskCount = 0;
  let reliabilityAcc = 0;
  let leadAcc = 0;

  for (const item of items) {
    totalPalletsRaw += item.orderQty / Math.max(1, item.unitsPerPallet);
    totalWeightKg += Math.round(item.orderQty * item.unitWeightKg);
    totalBudgetRaw += computeItemCostKrub(item, backupChannel);
    if (isSkuAtStockoutRisk(item, transitDelayDays, backupChannel)) {
      stockoutRiskCount += 1;
    }
    reliabilityAcc += getSupplier(item.supplierId).reliabilityPct;
    leadAcc += computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
  }

  const totalPallets = Number(totalPalletsRaw.toFixed(1));
  const totalBudgetKrub = Number(totalBudgetRaw.toFixed(1));

  let overLimitCount = 0;
  if (totalPallets > effectivePalletLimit + 0.05) overLimitCount += 1;
  if (totalWeightKg > constraints.maxWeightKg) overLimitCount += 1;
  if (totalBudgetKrub > constraints.maxBudgetKrub + 0.05) overLimitCount += 1;

  const count = Math.max(1, items.length);
  return {
    totalPallets,
    effectivePalletLimit,
    totalWeightKg,
    totalBudgetKrub,
    stockoutRiskCount,
    overLimitCount,
    avgReliabilityPct: Number((reliabilityAcc / count).toFixed(1)),
    avgLeadDays: Number((leadAcc / count).toFixed(1)),
    isFeasible: overLimitCount === 0 && stockoutRiskCount === 0
  };
}

export function toSnapshotMetrics(summary: OrderCapacitySummary): BalanceSnapshotMetrics {
  return {
    totalPallets: summary.totalPallets,
    totalWeightKg: summary.totalWeightKg,
    totalBudgetKrub: summary.totalBudgetKrub,
    stockoutRiskCount: summary.stockoutRiskCount,
    overLimitCount: summary.overLimitCount
  };
}
