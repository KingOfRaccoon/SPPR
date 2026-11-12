import { BACKUP_CHANNELS, getSupplier, getSupplierBatchStep } from '../data/presets';
import {
  balanceOrderToWarehouse,
  computeRecommendedOrderQty,
  computeRequiredTargetStock,
  computeStochasticBuffer
} from './replenishmentEngine';
import { createCustomSkuItem, nowHHMM, prependAuditEntry } from './storePersistence';
import type {
  BackupChannelMode,
  InventoryDomainState,
  SkuPriority,
  SupplierId,
  TransitDelayDays,
  WarehouseConstraints
} from '../types/domain';

export function updateSkuQtyMutation(
  state: InventoryDomainState,
  skuId: string,
  nextQty: number,
  summary: string,
  detail: string,
  toastMessage: string,
  manualOverride?: boolean
): InventoryDomainState {
  const nextItems = state.items.map((i) =>
    i.id === skuId
      ? {
          ...i,
          orderQty: nextQty,
          ...(manualOverride === undefined ? {} : { manualOverride })
        }
      : i
  );
  return {
    ...state,
    activeSkuId: skuId,
    items: nextItems,
    lastBalanceDiff: null,
    history: prependAuditEntry(state.history, summary, detail),
    toastMessage,
    toastCanUndo: true
  };
}

export function resetSkuMutation(state: InventoryDomainState, skuId: string): InventoryDomainState | null {
  const target = state.items.find((i) => i.id === skuId);
  if (!target) return null;
  const recQty = computeRecommendedOrderQty(target, state.transitDelayDays, state.backupChannel);
  if (target.orderQty === recQty && !target.manualOverride) return null;
  return updateSkuQtyMutation(
    state,
    skuId,
    recQty,
    `Сброс к норме «${target.name}»`,
    `Восстановлена расчетная партия ${recQty} шт. по ROP + SS`,
    `Расчетная норма: ${recQty} шт.`,
    false
  );
}

export function alignSkuStochasticMutation(
  state: InventoryDomainState,
  skuId: string
): { nextState: InventoryDomainState; pushUndo: boolean } | null {
  const target = state.items.find((i) => i.id === skuId);
  if (!target) return null;
  const stoch = computeStochasticBuffer(target, state.transitDelayDays, state.backupChannel);
  const baseTarget = computeRequiredTargetStock(target, state.transitDelayDays, state.backupChannel);
  const optTarget = Math.max(baseTarget, stoch.stochasticRop);
  const step = getSupplierBatchStep(target.supplierId);
  const optQty = Math.ceil(Math.max(step, optTarget - target.currentStock) / step) * step;
  if (target.orderQty === optQty && !target.manualOverride) {
    return {
      nextState: { ...state, toastMessage: `σ-норма уже установлена: ${optQty} шт.`, toastCanUndo: false },
      pushUndo: false
    };
  }
  return {
    nextState: updateSkuQtyMutation(
      state,
      skuId,
      optQty,
      `Выравнивание по σ-буферу «${target.name}»: ${optQty} шт.`,
      `Целевой SL ${stoch.serviceLevelPct}%, σ-ROP ${stoch.stochasticRop} шт., MOQ ${step}`,
      `Партия по σ-норме: ${optQty} шт.`,
      false
    ),
    pushUndo: true
  };
}

export function balanceOrderMutation(
  state: InventoryDomainState,
  requireStockoutZero: boolean,
  statusSeq: number
): { nextState: InventoryDomainState; pushUndo: boolean } {
  const res = balanceOrderToWarehouse(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const isClean =
    state.lastBalanceDiff !== null &&
    res.adjustedLinesCount === 0 &&
    res.after.overLimitCount === 0 &&
    (!requireStockoutZero || res.after.stockoutRiskCount === 0);

  if (isClean) {
    const seq = statusSeq + 1;
    const notice = requireStockoutZero
      ? `Ведомость проверена, паллет ${res.after.totalPallets.toFixed(1)}, сверка #${seq}`
      : `Габаритные лимиты подтверждены, ${res.after.totalPallets.toFixed(1)} паллет, #${seq}`;
    const toast = requireStockoutZero
      ? `Ведомость уже сбалансирована, ${res.after.totalPallets.toFixed(1)} паллет`
      : `Габаритные лимиты уже соблюдены, ${res.after.totalPallets.toFixed(1)} паллет`;
    return {
      nextState: { ...state, exportNotice: notice, toastMessage: toast, toastCanUndo: false },
      pushUndo: false
    };
  }

  return {
    nextState: {
      ...state,
      items: res.nextItems,
      lastBalanceDiff: {
        appliedAt: nowHHMM(),
        before: res.before,
        after: res.after,
        adjustedLinesCount: res.adjustedLinesCount,
        lineDiffs: res.lineDiffs
      },
      history: prependAuditEntry(
        state.history,
        requireStockoutZero ? 'Сбалансирован заказ под емкость склада' : 'Применены габаритные лимиты склада',
        requireStockoutZero
          ? `Паллеты: ${res.before.totalPallets.toFixed(1)} → ${res.after.totalPallets.toFixed(1)}, дефицит: ${res.before.stockoutRiskCount} → ${res.after.stockoutRiskCount}`
          : `Загрузка ${res.after.totalPallets.toFixed(1)} паллет, ${res.after.totalWeightKg} кг, ${res.after.totalBudgetKrub.toFixed(1)} тыс. ₽`
      ),
      toastMessage: requireStockoutZero
        ? `Заказ уложен: ${res.after.totalPallets.toFixed(1)} паллет, дефицит ${res.after.stockoutRiskCount}`
        : `Партии поджаты под лимит: ${res.after.totalPallets.toFixed(1)} паллет`,
      toastCanUndo: true
    },
    pushUndo: true
  };
}

export function updateConstraintsMutation(
  state: InventoryDomainState,
  patch: Partial<WarehouseConstraints>
): InventoryDomainState {
  const nextConstraints: WarehouseConstraints = { ...state.constraints, ...patch };
  return {
    ...state,
    constraints: nextConstraints,
    lastBalanceDiff: null,
    history: prependAuditEntry(
      state.history,
      'Обновлен габаритный лимит склада',
      `Приемка ${nextConstraints.maxPallets} паллет, резерв ворот ${nextConstraints.reserveGatePallets}, до ${nextConstraints.maxWeightKg} кг`
    ),
    toastMessage: `Лимит склада: ${nextConstraints.maxPallets - nextConstraints.reserveGatePallets} рабочих паллет`,
    toastCanUndo: true
  };
}

export function addCustomSkuMutation(
  state: InventoryDomainState,
  input: {
    name: string;
    category: string;
    orderQty: number;
    unitCostKrub?: number;
    safetyDays?: number;
    supplierId: SupplierId;
    priority: SkuPriority;
  }
): InventoryDomainState | null {
  const newItem = createCustomSkuItem(input);
  if (!newItem) return null;
  return {
    ...state,
    activeSkuId: newItem.id,
    items: [...state.items, newItem],
    lastBalanceDiff: null,
    history: prependAuditEntry(
      state.history,
      `Добавлена позиция «${newItem.name}»`,
      `Партия ${newItem.orderQty} шт., ${getSupplier(newItem.supplierId).name}`
    ),
    toastMessage: `Добавлено в заказ: ${newItem.name}`,
    toastCanUndo: true
  };
}

export function setTransitScenarioMutation(
  state: InventoryDomainState,
  transitDelayDays: TransitDelayDays,
  backupChannel: BackupChannelMode
): InventoryDomainState | null {
  if (state.transitDelayDays === transitDelayDays && state.backupChannel === backupChannel) {
    return null;
  }
  const ch = BACKUP_CHANNELS[backupChannel];
  return {
    ...state,
    transitDelayDays,
    backupChannel,
    lastBalanceDiff: null,
    history: prependAuditEntry(
      state.history,
      `Маршрутный режим: ${ch.label}`,
      `Поправка задержки +${transitDelayDays} дн.`
    ),
    toastMessage: `Канал доставки: ${ch.label}`,
    toastCanUndo: true
  };
}
