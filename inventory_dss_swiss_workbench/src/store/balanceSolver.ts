import { getSupplierBatchStep } from '../data/presets';
import {
  computeOrderSummary,
  computeRequiredTargetStock,
  toSnapshotMetrics
} from './replenishmentMetrics';
import {
  buildWhatIfBranch,
  computeCostOfInaction
} from './stochasticAnalytics';
import type {
  BackupChannelMode,
  BalanceLineDiff,
  BalanceSnapshotMetrics,
  InventoryDomainState,
  SkuItem,
  TransitDelayDays,
  WarehouseConstraints,
  WhatIfComparisonResult
} from '../types/domain';

export function formatShortBalanceReason(reason?: string): string {
  if (!reason) return '';
  return reason
    .replace(/\s*\([^)]*\)/g, '')
    .replace(/\s*·\s*/g, ', ')
    .trim();
}

function selectTrimmableCandidate(
  working: SkuItem[],
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): SkuItem | null {
  const safeStandard = working
    .filter((it) => {
      if (it.priority !== 'standard') return false;
      const step = getSupplierBatchStep(it.supplierId);
      if (it.orderQty <= step) return false;
      const minSafe = Math.max(
        step,
        computeRequiredTargetStock(it, transitDelayDays, backupChannel) - it.currentStock
      );
      return it.orderQty - step >= minSafe;
    })
    .sort((a, b) => {
      const aExcess = (a.currentStock + a.orderQty) / Math.max(1, a.dailyDemand);
      const bExcess = (b.currentStock + b.orderQty) / Math.max(1, b.dailyDemand);
      if (Math.abs(bExcess - aExcess) > 0.5) return bExcess - aExcess;
      return 1 / Math.max(1, a.unitsPerPallet) - 1 / Math.max(1, b.unitsPerPallet);
    });

  if (safeStandard.length > 0) return safeStandard[0];

  const byOrderQtyDesc = (priority: SkuItem['priority']) =>
    working
      .filter((it) => it.priority === priority && it.orderQty > getSupplierBatchStep(it.supplierId))
      .sort((a, b) => b.orderQty - a.orderQty);

  return byOrderQtyDesc('standard')[0] || byOrderQtyDesc('critical')[0] || null;
}

export function balanceOrderToWarehouse(
  items: SkuItem[],
  constraints: WarehouseConstraints,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): {
  nextItems: SkuItem[];
  before: BalanceSnapshotMetrics;
  after: BalanceSnapshotMetrics;
  adjustedLinesCount: number;
  lineDiffs: BalanceLineDiff[];
} {
  const beforeSummary = computeOrderSummary(items, constraints, transitDelayDays, backupChannel);
  const working = items.map((it) => ({ ...it }));

  for (const item of working) {
    if (item.priority !== 'critical') continue;
    const step = getSupplierBatchStep(item.supplierId);
    const target = computeRequiredTargetStock(item, transitDelayDays, backupChannel);
    const neededQty = Math.max(step, Math.ceil((target - item.currentStock) / step) * step);
    if (item.orderQty < neededQty) {
      item.orderQty = neededQty;
      item.manualOverride = false;
    }
  }

  for (let guard = 0; guard < 180; guard++) {
    const cur = computeOrderSummary(working, constraints, transitDelayDays, backupChannel);
    if (cur.overLimitCount === 0) break;
    const candidate = selectTrimmableCandidate(working, transitDelayDays, backupChannel);
    if (!candidate) break;
    candidate.orderQty -= getSupplierBatchStep(candidate.supplierId);
    candidate.manualOverride = false;
  }

  const afterSummary = computeOrderSummary(working, constraints, transitDelayDays, backupChannel);
  const lineDiffs: BalanceLineDiff[] = [];

  for (let i = 0; i < working.length; i++) {
    const orig = items[i];
    const updated = working[i];
    if (updated.orderQty === orig.orderQty) continue;

    const deltaQty = updated.orderQty - orig.orderQty;
    const deltaPallets = Number((deltaQty / Math.max(1, orig.unitsPerPallet)).toFixed(1));
    let reason: string;
    let riskAvoidedKrub: number | undefined;

    if (deltaQty > 0) {
      riskAvoidedKrub = computeCostOfInaction(orig, transitDelayDays, backupChannel).riskKrub;
      reason = `+${deltaQty} шт., защита крит. буфера (риск ${riskAvoidedKrub.toFixed(1)} тыс. ₽)`;
    } else {
      const coverDays = Number(
        ((orig.currentStock + updated.orderQty) / Math.max(1, orig.dailyDemand)).toFixed(1)
      );
      const moqNote = `MOQ ${getSupplierBatchStep(orig.supplierId)}`;
      reason = `${deltaQty} шт. (${deltaPallets.toFixed(1)} палл.), запас ${coverDays} сут. выше нормы, ${moqNote}`;
    }

    lineDiffs.push({
      skuId: orig.id,
      skuName: orig.name,
      beforeQty: orig.orderQty,
      afterQty: updated.orderQty,
      deltaPallets,
      reason,
      riskAvoidedKrub
    });
  }

  return {
    nextItems: working,
    before: toSnapshotMetrics(beforeSummary),
    after: toSnapshotMetrics(afterSummary),
    adjustedLinesCount: lineDiffs.length,
    lineDiffs
  };
}

export function computeWhatIfComparison(
  state: InventoryDomainState,
  stressDelayDays: TransitDelayDays,
  stressChannel: BackupChannelMode,
  stressMaxPallets?: number
): WhatIfComparisonResult {
  const stressConstraints: WarehouseConstraints = {
    ...state.constraints,
    maxPallets: stressMaxPallets ?? state.constraints.maxPallets
  };

  const baseline = buildWhatIfBranch(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );

  const stressBalanced = balanceOrderToWarehouse(
    state.items,
    stressConstraints,
    stressDelayDays,
    stressChannel
  );
  const stress = buildWhatIfBranch(
    stressBalanced.nextItems,
    stressConstraints,
    stressDelayDays,
    stressChannel
  );

  const riskDelta = stress.totalCostOfInactionKrub - baseline.totalCostOfInactionKrub;
  let verdict: string;
  if (stress.isFeasible && baseline.isFeasible) {
    verdict =
      riskDelta <= 0
        ? `Стресс-сценарий вписывается в лимиты (Δ риск ${riskDelta.toFixed(1)} тыс. ₽).`
        : `Стресс-сценарий выполним, но риск вырастает на ${riskDelta.toFixed(1)} тыс. ₽.`;
  } else if (stress.isFeasible) {
    verdict = `Балансировка снимает перегруз и закрывает дефицит (${stress.totalPallets.toFixed(1)} палл.).`;
  } else if (stress.overLimitCount > 0) {
    verdict = `Превышено ограничений РЦ: ${stress.overLimitCount}; дефицит позиций: ${stress.stockoutRiskCount}. Смягчите лимит паллет или смените канал.`;
  } else {
    verdict = `Габариты РЦ соблюдены (${stress.totalPallets.toFixed(1)} палл.), но остается дефицит ${stress.stockoutRiskCount} поз. (риск ${Math.round(stress.totalCostOfInactionKrub)} тыс. ₽) — выберите ускоренный канал.`;
  }

  return { baseline, stress, verdict };
}
