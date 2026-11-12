import { balanceOrderToWarehouse } from './balanceSolver';
import {
  computeOrderSummary,
  computeRequiredTargetStock,
  toSnapshotMetrics
} from './replenishmentMetrics';
import {
  computeCostOfInaction,
  computeStochasticBuffer,
  computeSupplierNegotiationImpact,
  computeWaveFinancialSummary
} from './stochasticAnalytics';
import type {
  BackupChannelMode,
  BalanceLineDiff,
  BalanceSnapshotMetrics,
  SkuItem,
  SupplierId,
  TransitDelayDays,
  WarehouseConstraints
} from '../types/domain';

export * from './replenishmentMetrics';
export {
  computeCostOfInaction,
  computeStochasticBuffer,
  computeSupplierNegotiationImpact,
  computeWaveFinancialSummary
};
export {
  balanceOrderToWarehouse,
  computeWhatIfComparison,
  formatShortBalanceReason
} from './balanceSolver';

function resolveBestSupplierForSku(item: SkuItem): SupplierId {
  if (item.priority !== 'critical') return 'ural-privod';
  return item.dailyDemand >= 7 ? 'sever-snab' : 'balt-komplekt';
}

export function assignBestSuppliersToItems(items: SkuItem[]): {
  nextItems: SkuItem[];
  switchedCount: number;
} {
  let switchedCount = 0;
  const nextItems: SkuItem[] = items.map((item) => {
    const targetSupplier = resolveBestSupplierForSku(item);
    if (item.supplierId !== targetSupplier) {
      switchedCount += 1;
      return { ...item, supplierId: targetSupplier };
    }
    return { ...item };
  });
  return { nextItems, switchedCount };
}

export function reinforceTransitBuffers(
  items: SkuItem[],
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): {
  nextItems: SkuItem[];
  updatedCount: number;
} {
  let updatedCount = 0;
  const nextItems = items.map((item) => {
    const nextSafety = item.priority === 'critical' ? Math.min(16, item.safetyDays + 2) : item.safetyDays;
    const target = computeRequiredTargetStock(
      { ...item, safetyDays: nextSafety },
      transitDelayDays,
      backupChannel
    );
    const minOrder = Math.max(item.orderQty, Math.ceil(Math.max(10, target - item.currentStock) / 10) * 10);
    if (nextSafety !== item.safetyDays || minOrder !== item.orderQty) {
      updatedCount += 1;
    }
    return {
      ...item,
      safetyDays: nextSafety,
      orderQty: minOrder
    };
  });
  return { nextItems, updatedCount };
}

function pickEscalatedChannel(
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): BackupChannelMode {
  if (transitDelayDays >= 9) return 'express_auto';
  if (transitDelayDays >= 4 && backupChannel === 'direct_rail') return 'regional_hub';
  return backupChannel;
}

export function reconcileSupplyNetworkFlows(
  items: SkuItem[],
  constraints: WarehouseConstraints,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): {
  nextItems: SkuItem[];
  nextChannel: BackupChannelMode;
  before: BalanceSnapshotMetrics;
  after: BalanceSnapshotMetrics;
  lineDiffs: BalanceLineDiff[];
  changed: boolean;
} {
  const nextChannel = pickEscalatedChannel(transitDelayDays, backupChannel);
  const tunedItems = items.map((it) => {
    const nextSupplier: SupplierId =
      it.priority === 'critical' && it.supplierId === 'volga-pribor'
        ? 'sever-snab'
        : it.supplierId;
    return { ...it, supplierId: nextSupplier };
  });

  const balanced = balanceOrderToWarehouse(
    tunedItems,
    constraints,
    transitDelayDays,
    nextChannel
  );
  const before = computeOrderSummary(items, constraints, transitDelayDays, backupChannel);
  const lineDiffs: BalanceLineDiff[] = [];
  let skuChanged = nextChannel !== backupChannel;
  for (let i = 0; i < items.length; i++) {
    if (
      balanced.nextItems[i].orderQty !== items[i].orderQty ||
      balanced.nextItems[i].supplierId !== items[i].supplierId
    ) {
      skuChanged = true;
      if (balanced.nextItems[i].orderQty !== items[i].orderQty) {
        const dq = balanced.nextItems[i].orderQty - items[i].orderQty;
        lineDiffs.push({
          skuId: items[i].id,
          skuName: items[i].name,
          beforeQty: items[i].orderQty,
          afterQty: balanced.nextItems[i].orderQty,
          deltaPallets: Number((dq / Math.max(1, items[i].unitsPerPallet)).toFixed(1)),
          reason: dq > 0 ? 'Поднято под отгрузку' : 'Сжато под рампу'
        });
      }
    }
  }

  return {
    nextItems: balanced.nextItems,
    nextChannel,
    before: toSnapshotMetrics(before),
    after: balanced.after,
    lineDiffs,
    changed: skuChanged
  };
}
