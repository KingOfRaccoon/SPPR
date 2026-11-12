import React from 'react';
import { getSupplier, SUPPLIER_LIST } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  balanceOrderToWarehouse,
  formatShortBalanceReason
} from '../store/replenishmentEngine';
import { RouteMapIcon, ScaleBalanceIcon } from './Icons';
import { SawtoothProjectionChart } from './SawtoothProjectionChart';
import type { InventoryDomainState, SkuItem, SupplierId } from '../types/domain';

interface ReplenishmentInspectorColumnProps {
  state: InventoryDomainState;
  activeSku: SkuItem;
  activeRecommendedQty: number;
}

export function ReplenishmentInspectorColumn({
  state,
  activeSku,
  activeRecommendedQty
}: ReplenishmentInspectorColumnProps) {
  const activeSupplier = getSupplier(activeSku.supplierId);

  const previewDiff = balanceOrderToWarehouse(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );

  const beforeMetrics = state.lastBalanceDiff ? state.lastBalanceDiff.before : previewDiff.before;
  const afterMetrics = state.lastBalanceDiff ? state.lastBalanceDiff.after : previewDiff.after;
  const activeLineDiffs = state.lastBalanceDiff?.lineDiffs || previewDiff.lineDiffs;

  const isAlreadyBalanced =
    state.lastBalanceDiff !== null &&
    previewDiff.adjustedLinesCount === 0 &&
    previewDiff.after.overLimitCount === 0 &&
    previewDiff.after.stockoutRiskCount === 0;

  return (
    <div className="xl:col-span-4 flex flex-col justify-between gap-2.5 min-w-0">
      <article
        data-card="before-after-balance"
        data-before-after-card="true"
        className="surface-card p-2.5 space-y-1.5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <div className="flex items-center gap-1.5">
            <ScaleBalanceIcon size={15} className="text-accent-primary" />
            <h2 className="text-sm font-semibold text-primary">Было → Стало</h2>
          </div>
          <span className="text-xs text-muted tabular-nums">
            {state.lastBalanceDiff
              ? `Применено: ${state.lastBalanceDiff.adjustedLinesCount}`
              : `Прогноз: ${previewDiff.adjustedLinesCount}`}
          </span>
        </div>

        <div className="surface-inset p-2 space-y-1 tabular-nums text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="text-secondary">Паллетоместа</span>
            <span data-numeric="true" className="font-semibold text-primary">
              {beforeMetrics.totalPallets.toFixed(1)} → {afterMetrics.totalPallets.toFixed(1)} п.
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-secondary">Дефицит и масса</span>
            <span data-numeric="true" className="font-semibold text-primary">
              {beforeMetrics.stockoutRiskCount} → {afterMetrics.stockoutRiskCount} поз.,{' '}
              {afterMetrics.totalWeightKg} кг
            </span>
          </div>
          {activeLineDiffs.length > 0 && (
            <div className="pt-0.5 text-xs text-secondary" data-diff-lines-summary="true">
              {activeLineDiffs.slice(0, 1).map((d) => {
                const shortReason = formatShortBalanceReason(d.reason);
                return (
                  <div key={d.skuId} className="space-y-0.5">
                    <div className="flex items-center justify-between gap-2">
                      <span>{d.skuName}</span>
                      <span className="font-medium text-primary">
                        {d.beforeQty} → {d.afterQty} шт.
                      </span>
                    </div>
                    {shortReason && <div className="text-muted leading-tight">{shortReason}</div>}
                  </div>
                );
              })}
              {activeLineDiffs.length > 1 && (
                <div className="text-muted">+{activeLineDiffs.length - 1} стр.</div>
              )}
            </div>
          )}
        </div>

        <button
          type="button"
          data-primary-action="true"
          onClick={() => inventoryStore.balanceOrder()}
          className="btn-primary w-full radius-control"
        >
          {isAlreadyBalanced ? 'Сбалансировано, сверить' : 'Сбалансировать склад'}
        </button>
      </article>

      <article data-card="active-sku-inspector" className="surface-card p-2.5 space-y-1.5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-sm font-semibold text-primary min-w-0">{activeSku.name}</h2>

          <div className="flex flex-wrap items-center gap-1">
            {(activeSku.manualOverride || activeSku.orderQty !== activeRecommendedQty) && (
              <button
                type="button"
                data-reset-recommended="true"
                onClick={() => inventoryStore.resetSkuToRecommended(activeSku.id)}
                className="btn-row tabular-nums"
              >
                Норма {activeRecommendedQty}
              </button>
            )}
            <button
              type="button"
              data-align-stochastic="true"
              onClick={() => inventoryStore.alignSkuToStochasticBuffer(activeSku.id)}
              className="btn-row tabular-nums"
            >
              σ-норма
            </button>
            <button
              type="button"
              data-open-sku-map="true"
              onClick={() => inventoryStore.openSkuTraceOnMap(activeSku.id)}
              className="btn-row"
            >
              <RouteMapIcon size={12} />
              <span>На карте</span>
            </button>
          </div>
        </div>

        <SawtoothProjectionChart
          item={activeSku}
          transitDelayDays={state.transitDelayDays}
          backupChannel={state.backupChannel}
          compact
        />

        <div className="space-y-1">
          <label
            htmlFor="inspector-supplier-select"
            className="block text-xs font-medium text-secondary"
          >
            Поставщик, {activeSupplier.city}
          </label>
          <select
            id="inspector-supplier-select"
            value={activeSku.supplierId}
            onChange={(e) =>
              inventoryStore.updateSkuSupplier(activeSku.id, e.target.value as SupplierId)
            }
            className="w-full field-compact"
          >
            {SUPPLIER_LIST.map((sup) => (
              <option key={sup.id} value={sup.id}>
                {sup.name}, {sup.leadDays}д
              </option>
            ))}
          </select>
        </div>
      </article>
    </div>
  );
}
