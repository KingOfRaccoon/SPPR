import { BACKUP_CHANNELS, SCENARIO_PRESETS, SUPPLIERS } from '../data/presets';
import {
  assignBestSuppliersToItems,
  computeOrderSummary,
  reconcileSupplyNetworkFlows,
  reinforceTransitBuffers
} from './replenishmentEngine';
import { buildInitialState, nowHHMM, prependAuditEntry } from './storePersistence';
import type {
  BackupChannelMode,
  InventoryDomainState,
  ScenarioPresetId,
  SelectedMapNodeId,
  SupplierId
} from '../types/domain';

const OUTBOUND_SKU_MAP: Record<string, string> = {
  'out-tula': 'sku-power-ctrl',
  'out-nn': 'sku-pressure-sens',
  'out-voronezh': 'sku-line-relay',
  'out-samara': 'sku-terminal-blk'
};

export function selectMapNodeState(
  state: InventoryDomainState,
  nodeId: SelectedMapNodeId
): InventoryDomainState {
  const isSup = nodeId in SUPPLIERS;
  const matchedSku = isSup
    ? state.items.find((i) => i.supplierId === nodeId)
    : state.items.find((i) => i.id === OUTBOUND_SKU_MAP[nodeId]);
  return {
    ...state,
    selectedMapNodeId: nodeId,
    selectedSupplierId: isSup ? (nodeId as SupplierId) : state.selectedSupplierId,
    activeSkuId: matchedSku ? matchedSku.id : state.activeSkuId
  };
}

export function loadPresetState(
  state: InventoryDomainState,
  presetId: ScenarioPresetId
): InventoryDomainState {
  const fresh = buildInitialState(presetId);
  const label = SCENARIO_PRESETS.find((p) => p.id === presetId)?.label || presetId;
  return {
    ...fresh,
    activeScreenId: state.activeScreenId,
    toastMessage: `Загружен сценарий: ${label}`,
    toastCanUndo: true
  };
}

export function cycleSafetyMutation(
  state: InventoryDomainState,
  skuId: string
): InventoryDomainState | null {
  const target = state.items.find((i) => i.id === skuId);
  if (!target) return null;
  const cycle = [6, 8, 10, 12, 14];
  const nextSafety = cycle[(cycle.indexOf(target.safetyDays) + 1) % cycle.length];
  return {
    ...state,
    activeSkuId: skuId,
    items: state.items.map((i) => (i.id === skuId ? { ...i, safetyDays: nextSafety } : i)),
    lastBalanceDiff: null,
    history: prependAuditEntry(
      state.history,
      `Страховой запас «${target.name}», ${nextSafety} дн.`,
      `Точка дозаказа: ${target.reorderPoint} шт.`
    ),
    toastMessage: `Страховой буфер: ${nextSafety} дн.`,
    toastCanUndo: true
  };
}

export function updateSkuSupplierMutation(
  state: InventoryDomainState,
  skuId: string,
  supplierId: SupplierId
): InventoryDomainState | null {
  const target = state.items.find((i) => i.id === skuId);
  if (!target || target.supplierId === supplierId) return null;
  const sup = SUPPLIERS[supplierId];
  return {
    ...state,
    activeSkuId: skuId,
    selectedSupplierId: supplierId,
    items: state.items.map((i) => (i.id === skuId ? { ...i, supplierId } : i)),
    lastBalanceDiff: null,
    history: prependAuditEntry(
      state.history,
      `Поставщик «${target.name}», ${sup.name}`,
      `Срок ${sup.leadDays} дн., надежность ${sup.reliabilityPct.toFixed(1)}%`
    ),
    toastMessage: `Назначен поставщик: ${sup.name}`,
    toastCanUndo: true
  };
}

export function assignOptimalSuppliersMutation(
  state: InventoryDomainState,
  statusSeq: number
): { nextState: InventoryDomainState; pushUndo: boolean } {
  const res = assignBestSuppliersToItems(state.items);
  const summary = computeOrderSummary(
    res.nextItems,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  if (res.switchedCount === 0) {
    const seq = statusSeq + 1;
    return {
      nextState: {
        ...state,
        exportNotice: `Пул поставщиков оптимален, надежность ${summary.avgReliabilityPct.toFixed(1)}%, #${seq}`,
        toastMessage: `Лучшие поставщики уже закреплены, ${summary.avgReliabilityPct.toFixed(1)}%`,
        toastCanUndo: false
      },
      pushUndo: false
    };
  }
  const activeUpdated = res.nextItems.find((i) => i.id === state.activeSkuId) || res.nextItems[0];
  return {
    nextState: {
      ...state,
      items: res.nextItems,
      selectedSupplierId: activeUpdated ? activeUpdated.supplierId : state.selectedSupplierId,
      lastBalanceDiff: null,
      history: prependAuditEntry(
        state.history,
        'Назначены оптимальные поставщики по пулу',
        `Переключено позиций: ${res.switchedCount}, надежность ${summary.avgReliabilityPct.toFixed(1)}%, срок ${summary.avgLeadDays.toFixed(1)} дн.`
      ),
      toastMessage: `Поставщики обновлены, надежность ${summary.avgReliabilityPct.toFixed(1)}%`,
      toastCanUndo: true
    },
    pushUndo: true
  };
}

export function reinforceBufferMutation(
  state: InventoryDomainState,
  statusSeq: number
): { nextState: InventoryDomainState; pushUndo: boolean } {
  const nextChannel: BackupChannelMode =
    state.transitDelayDays >= 4 && state.backupChannel === 'direct_rail'
      ? 'regional_hub'
      : state.backupChannel;
  const res = reinforceTransitBuffers(state.items, state.transitDelayDays, nextChannel);
  if (res.updatedCount === 0 && nextChannel === state.backupChannel) {
    const seq = statusSeq + 1;
    return {
      nextState: {
        ...state,
        exportNotice: `Страховой буфер максимален, канал ${BACKUP_CHANNELS[nextChannel].label}, #${seq}`,
        toastMessage: 'Страховой запас уже на защитном уровне',
        toastCanUndo: false
      },
      pushUndo: false
    };
  }
  return {
    nextState: {
      ...state,
      backupChannel: nextChannel,
      items: res.nextItems,
      lastBalanceDiff: null,
      history: prependAuditEntry(
        state.history,
        'Усилен страховой запас на время в пути',
        `Обновлено строк: ${res.updatedCount}, канал ${BACKUP_CHANNELS[nextChannel].label}`
      ),
      toastMessage: `Страховой буфер усилен для ${res.updatedCount} позиций`,
      toastCanUndo: true
    },
    pushUndo: true
  };
}

export function reconcileNetworkFlowsMutation(
  state: InventoryDomainState
): { nextState: InventoryDomainState; pushUndo: boolean } {
  const res = reconcileSupplyNetworkFlows(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  if (!res.changed && res.after.overLimitCount === 0 && res.after.stockoutRiskCount === 0) {
    return {
      nextState: {
        ...state,
        toastMessage: `Потоки сети сбалансированы, приемка ${res.after.totalPallets.toFixed(1)} паллет`,
        toastCanUndo: false
      },
      pushUndo: false
    };
  }
  const chLabel = BACKUP_CHANNELS[res.nextChannel].label;
  return {
    nextState: {
      ...state,
      backupChannel: res.nextChannel,
      items: res.nextItems,
      lastBalanceDiff: {
        appliedAt: nowHHMM(),
        before: res.before,
        after: res.after,
        adjustedLinesCount: Math.max(1, res.lineDiffs.length),
        lineDiffs: res.lineDiffs
      },
      history: prependAuditEntry(
        state.history,
        'Выровнены входящие и исходящие потоки сети',
        `Канал: ${chLabel}, паллеты ${res.after.totalPallets.toFixed(1)}, дефицит ${res.after.stockoutRiskCount}`
      ),
      toastMessage: `Сеть выровнена: ${res.after.totalPallets.toFixed(1)} паллет, канал ${chLabel}`,
      toastCanUndo: true
    },
    pushUndo: true
  };
}
