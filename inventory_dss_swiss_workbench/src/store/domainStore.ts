import { useSyncExternalStore } from 'react';
import { SUPPLIERS } from '../data/presets';
import {
  STORAGE_KEY,
  buildInitialState,
  hydrateStoredState,
  prependAuditEntry,
  saveStoredState
} from './storePersistence';
import {
  addCustomSkuMutation,
  alignSkuStochasticMutation,
  balanceOrderMutation,
  resetSkuMutation,
  setTransitScenarioMutation,
  updateConstraintsMutation,
  updateSkuQtyMutation
} from './domainMutations';
import {
  assignOptimalSuppliersMutation,
  cycleSafetyMutation,
  loadPresetState,
  reconcileNetworkFlowsMutation,
  reinforceBufferMutation,
  selectMapNodeState,
  updateSkuSupplierMutation
} from './domainNetworkMutations';
import type {
  BackupChannelMode,
  FlowLensMode,
  InventoryDomainState,
  ScenarioPresetId,
  ScreenId,
  SelectedMapNodeId,
  SkuPriority,
  SupplierId,
  TransitDelayDays,
  WarehouseConstraints
} from '../types/domain';

export { STORAGE_KEY };

class LocalFirstDomainStore {
  private state: InventoryDomainState;
  private undoStack: InventoryDomainState[] = [];
  private listeners = new Set<() => void>();
  private exportSeq = 0;
  private statusSeq = 0;

  constructor() {
    this.state = hydrateStoredState();
  }

  private notify(): void {
    for (const listener of this.listeners) listener();
  }

  private commit(nextState: InventoryDomainState, prevForUndo: InventoryDomainState | null): void {
    this.state = nextState;
    if (prevForUndo) {
      this.undoStack.push(prevForUndo);
      if (this.undoStack.length > 20) this.undoStack.shift();
    }
    saveStoredState(this.state);
    this.notify();
  }

  private commitMaybeUndo(nextState: InventoryDomainState | null): void {
    if (nextState) this.commit(nextState, structuredClone(this.state));
  }

  private applyRes(res: { nextState: InventoryDomainState; pushUndo: boolean }): void {
    if (!res.pushUndo) this.statusSeq += 1;
    this.commit(res.nextState, res.pushUndo ? structuredClone(this.state) : null);
  }

  getSnapshot = (): InventoryDomainState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  canUndo(): boolean { return this.undoStack.length > 0; }

  dismissToast(): void {
    if (!this.state.toastMessage) return;
    this.state = { ...this.state, toastMessage: null, toastCanUndo: false };
    this.notify();
  }

  setScreen(screenId: ScreenId): void {
    if (this.state.activeScreenId === screenId) return;
    this.state = { ...this.state, activeScreenId: screenId };
    this.notify();
  }

  selectSku(skuId: string): void {
    if (this.state.activeSkuId === skuId) return;
    const found = this.state.items.find((i) => i.id === skuId);
    this.commit(
      { ...this.state, activeSkuId: skuId, selectedSupplierId: found ? found.supplierId : this.state.selectedSupplierId },
      null
    );
  }

  undo(): void {
    const previous = this.undoStack.pop();
    if (!previous) return;
    this.commit(
      { ...previous, activeScreenId: this.state.activeScreenId, toastMessage: 'Последнее действие отменено', toastCanUndo: false },
      null
    );
  }

  resetToSeed(): void {
    this.undoStack = [];
    this.commit({ ...buildInitialState('preset-seasonal-peak'), toastMessage: 'Восстановлена эталонная ведомость', toastCanUndo: false }, null);
  }

  selectChartSku(skuId: string): void {
    if (this.state.activeSkuId === skuId && this.state.items.length > 1) {
      const idx = this.state.items.findIndex((i) => i.id === skuId);
      this.selectSku(this.state.items[(idx + 1) % this.state.items.length].id);
      return;
    }
    this.selectSku(skuId);
  }

  selectSupplier(supplierId: SupplierId): void {
    if (this.state.selectedSupplierId === supplierId) return;
    this.commit({ ...this.state, selectedSupplierId: supplierId, selectedMapNodeId: supplierId }, null);
  }

  selectMapNode(nodeId: SelectedMapNodeId): void {
    if (this.state.selectedMapNodeId !== nodeId) this.commit(selectMapNodeState(this.state, nodeId), null);
  }

  selectChartSupplier(supplierId: SupplierId): void {
    if (this.state.selectedSupplierId === supplierId) {
      const ids = Object.keys(SUPPLIERS) as SupplierId[];
      this.selectSupplier(ids[(ids.indexOf(supplierId) + 1) % ids.length]);
      return;
    }
    this.selectSupplier(supplierId);
  }

  loadPreset(presetId: ScenarioPresetId): void { this.commitMaybeUndo(loadPresetState(this.state, presetId)); }

  setMapLens(lens: FlowLensMode): void {
    if ((this.state.mapLens || 'all') !== lens) this.commit({ ...this.state, mapLens: lens }, null);
  }

  openSkuTraceOnMap(skuId: string): void {
    const found = this.state.items.find((i) => i.id === skuId) || this.state.items[0];
    if (!found) return;
    this.state = {
      ...this.state,
      activeSkuId: found.id,
      selectedSupplierId: found.supplierId,
      selectedMapNodeId: found.supplierId,
      mapLens: 'sku_peg',
      activeScreenId: 'screen-supply-map'
    };
    this.notify();
  }

  setOrderQty(skuId: string, rawQty: number): void {
    const target = this.state.items.find((i) => i.id === skuId);
    if (!target || !Number.isFinite(rawQty)) return;
    const nextQty = Math.max(10, Math.min(990, Math.round(rawQty)));
    if (nextQty === target.orderQty) return;
    this.commitMaybeUndo(
      updateSkuQtyMutation(
        this.state, skuId, nextQty,
        `Ручной ввод «${target.name}»: ${nextQty} шт.`,
        `Прямая корректировка в ведомости (было ${target.orderQty} шт.)`,
        `Партия вручную: ${nextQty} шт.`, true
      )
    );
  }

  adjustOrderQty(skuId: string, deltaQty: number): void {
    const target = this.state.items.find((i) => i.id === skuId);
    if (!target) return;
    const nextQty = Math.max(10, Math.min(990, target.orderQty + deltaQty));
    if (nextQty === target.orderQty) return;
    const sign = deltaQty > 0 ? `+${deltaQty}` : String(deltaQty);
    this.commitMaybeUndo(
      updateSkuQtyMutation(
        this.state, skuId, nextQty,
        `Партия «${target.name}» ${sign} шт.`,
        `Новый объем дозаказа: ${nextQty} шт.`,
        `Партия обновлена: ${nextQty} шт.`, true
      )
    );
  }

  resetSkuToRecommended(skuId: string): void { this.commitMaybeUndo(resetSkuMutation(this.state, skuId)); }

  alignSkuToStochasticBuffer(skuId: string): void {
    const res = alignSkuStochasticMutation(this.state, skuId);
    if (res) this.applyRes(res);
  }

  cycleSafetyDays(skuId: string): void { this.commitMaybeUndo(cycleSafetyMutation(this.state, skuId)); }

  updateSkuSupplier(skuId: string, supplierId: SupplierId): void {
    this.commitMaybeUndo(updateSkuSupplierMutation(this.state, skuId, supplierId));
  }

  updateConstraints(patch: Partial<WarehouseConstraints>): void {
    this.commitMaybeUndo(updateConstraintsMutation(this.state, patch));
  }

  addCustomSku(input: {
    name: string;
    category: string;
    orderQty: number;
    unitCostKrub?: number;
    safetyDays?: number;
    supplierId: SupplierId;
    priority: SkuPriority;
  }): void {
    this.commitMaybeUndo(addCustomSkuMutation(this.state, input));
  }

  setTransitScenario(transitDelayDays: TransitDelayDays, backupChannel: BackupChannelMode): void {
    this.commitMaybeUndo(setTransitScenarioMutation(this.state, transitDelayDays, backupChannel));
  }

  balanceOrder(): void { this.applyRes(balanceOrderMutation(this.state, true, this.statusSeq)); }

  applyWarehouseLimitsAndBalance(): void { this.applyRes(balanceOrderMutation(this.state, false, this.statusSeq)); }

  reconcileNetworkFlows(): void { this.applyRes(reconcileNetworkFlowsMutation(this.state)); }

  assignOptimalSuppliers(): void { this.applyRes(assignOptimalSuppliersMutation(this.state, this.statusSeq)); }

  reinforceDeliveryBuffer(): void { this.applyRes(reinforceBufferMutation(this.state, this.statusSeq)); }

  setExportFormat(fmt: 'csv' | 'memo'): void {
    if (this.state.exportFormat === fmt) return;
    this.commit(
      {
        ...this.state,
        exportFormat: fmt,
        exportNotice: fmt === 'csv'
          ? 'Показана табличная спецификация заказа .csv с разделителем точка с запятой'
          : 'Показана пояснительная записка для согласования закупки'
      },
      null
    );
  }

  recordArtifactExport(actionLabel: string): void {
    this.exportSeq += 1;
    this.commit(
      {
        ...this.state,
        exportNotice: `${actionLabel}, строк ${this.state.items.length}, выгрузка #${this.exportSeq}`,
        history: prependAuditEntry(this.state.history, actionLabel, `${this.state.waveLabel}, позиций ${this.state.items.length}`),
        toastMessage: actionLabel,
        toastCanUndo: false
      },
      null
    );
  }
}

export const inventoryStore = new LocalFirstDomainStore();

export function useInventoryStore(): InventoryDomainState {
  return useSyncExternalStore(inventoryStore.subscribe, inventoryStore.getSnapshot, inventoryStore.getSnapshot);
}
