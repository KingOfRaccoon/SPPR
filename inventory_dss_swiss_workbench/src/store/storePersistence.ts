import { SCENARIO_PRESETS } from '../data/presets';
import type {
  AuditHistoryEntry,
  InventoryDomainState,
  ScenarioPresetId,
  SkuItem,
  SkuPriority,
  SupplierId
} from '../types/domain';

export const STORAGE_KEY = 'inventory_notebook_v7_store';

export function nowHHMM(): string {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const hh = h < 10 ? `0${h}` : String(h);
  const mm = m < 10 ? `0${m}` : String(m);
  return `${hh}:${mm}`;
}

export function buildInitialState(
  presetId: ScenarioPresetId = 'preset-seasonal-peak'
): InventoryDomainState {
  const preset = SCENARIO_PRESETS.find((p) => p.id === presetId) || SCENARIO_PRESETS[0];
  const clonedItems = preset.items.map((it) => ({ ...it }));
  return {
    activeScreenId: 'screen-replenishment-notebook',
    activePresetId: preset.id,
    activeSkuId: clonedItems[0]?.id || 'sku-power-ctrl',
    selectedSupplierId: clonedItems[0]?.supplierId || 'balt-komplekt',
    selectedMapNodeId: 'dc-moscow',
    mapLens: 'all',
    waveLabel: preset.waveLabel,
    transitDelayDays: preset.transitDelayDays,
    backupChannel: preset.backupChannel,
    constraints: { ...preset.constraints },
    items: clonedItems,
    lastBalanceDiff: null,
    exportFormat: 'csv',
    exportNotice: 'Готово к выгрузке спецификации .csv или копированию записки',
    history: [
      {
        id: 'hist-seed-1',
        timeLabel: '09:15',
        summary: `Открыт сценарий «${preset.label}»`,
        detail: `Позиций: ${clonedItems.length}, лимит приемки ${preset.constraints.maxPallets} паллет`
      },
      {
        id: 'hist-seed-2',
        timeLabel: '09:05',
        summary: 'Подтвержден резерв разгрузочных ворот Смены А',
        detail: `Буфер рампы: ${preset.constraints.reserveGatePallets} паллет, лимит тоннажа ${preset.constraints.maxWeightKg} кг`
      },
      {
        id: 'hist-seed-3',
        timeLabel: '08:50',
        summary: 'Синхронизация остатков WMS терминала Шушары',
        detail: `Проверены страховые нормативы и точки дозаказа по ${clonedItems.length} узлам`
      },
      {
        id: 'hist-seed-4',
        timeLabel: '08:35',
        summary: 'Утвержден финансовый потолок закупочной волны',
        detail: `Лимит казначейства: ${preset.constraints.maxBudgetKrub} тыс. ₽ на текущую неделю`
      }
    ],
    toastMessage: null,
    toastCanUndo: false
  };
}

export function hydrateStoredState(): InventoryDomainState {
  if (typeof window === 'undefined' || !window.localStorage) {
    return buildInitialState();
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return buildInitialState();
    const parsed = JSON.parse(raw) as Partial<InventoryDomainState>;
    if (!parsed || !Array.isArray(parsed.items) || parsed.items.length === 0) {
      return buildInitialState();
    }
    return {
      ...buildInitialState(parsed.activePresetId || 'preset-seasonal-peak'),
      ...parsed,
      activeScreenId: 'screen-replenishment-notebook',
      toastMessage: null,
      toastCanUndo: false
    };
  } catch (err: unknown) {
    if (err instanceof Error) {
      return buildInitialState();
    }
    return buildInitialState();
  }
}

export function saveStoredState(state: InventoryDomainState): boolean {
  if (typeof window === 'undefined' || !window.localStorage) {
    return false;
  }
  try {
    const persistedPayload: InventoryDomainState = {
      ...state,
      activeScreenId: 'screen-replenishment-notebook',
      toastMessage: null,
      toastCanUndo: false
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persistedPayload));
    return true;
  } catch (err: unknown) {
    if (err instanceof Error) {
      return false;
    }
    return false;
  }
}

export function prependAuditEntry(
  history: AuditHistoryEntry[],
  summary: string,
  detail: string
): AuditHistoryEntry[] {
  const entry: AuditHistoryEntry = {
    id: `hist-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timeLabel: nowHHMM(),
    summary,
    detail
  };
  return [entry, ...history].slice(0, 12);
}

export function createCustomSkuItem(input: {
  name: string;
  category: string;
  orderQty: number;
  unitCostKrub?: number;
  safetyDays?: number;
  supplierId: SupplierId;
  priority: SkuPriority;
}): SkuItem | null {
  const cleanName = input.name.trim();
  if (!cleanName) return null;
  const safeQty = Math.max(10, Math.min(1200, Math.round(input.orderQty) || 40));
  const safeCost = Number(
    (input.unitCostKrub && input.unitCostKrub > 0 ? input.unitCostKrub : 6.8).toFixed(2)
  );
  const safeBuffer = Math.max(4, Math.min(24, Math.round(input.safetyDays || 8)));
  return {
    id: `sku-custom-${Date.now()}`,
    name: cleanName,
    category: input.category || 'Комплектация',
    currentStock: 18,
    dailyDemand: 4,
    reorderPoint: 36,
    safetyDays: safeBuffer,
    orderQty: safeQty,
    unitCostKrub: safeCost,
    unitWeightKg: 7.5,
    unitsPerPallet: 20,
    supplierId: input.supplierId,
    priority: input.priority
  };
}
