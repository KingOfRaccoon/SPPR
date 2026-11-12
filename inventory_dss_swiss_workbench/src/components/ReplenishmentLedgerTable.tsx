import { useCallback, useRef } from 'react';
import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeEffectiveLeadDays,
  computeStochasticBuffer,
  isSkuAtStockoutRisk
} from '../store/replenishmentEngine';
import { ReplenishmentLedgerRow, type RowKeyEvent } from './ReplenishmentLedgerRow';
import type {
  BalanceLineDiff,
  InventoryDomainState,
  OrderCapacitySummary,
  SkuItem
} from '../types/domain';

export type TriageFilter = 'all' | 'deficit' | 'manual';

interface ReplenishmentLedgerTableProps {
  state: InventoryDomainState;
  summary: OrderCapacitySummary;
  activeSku: SkuItem;
  activeRecommendedQty: number;
  triageFilter: TriageFilter;
  onChangeTriageFilter: (filter: TriageFilter) => void;
}

export function ReplenishmentLedgerTable({
  state,
  summary,
  activeSku,
  activeRecommendedQty,
  triageFilter,
  onChangeTriageFilter
}: ReplenishmentLedgerTableProps) {
  const tbodyRef = useRef<HTMLTableSectionElement | null>(null);

  const handleRowKeyDown = useCallback(
    (e: RowKeyEvent, itemId: string) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const rows = tbodyRef.current
          ? Array.from(tbodyRef.current.querySelectorAll<HTMLTableRowElement>('tr[data-entity-id]'))
          : [];
        const currentIdx = rows.findIndex((r) => r.dataset.entityId === itemId);
        const nextIdx = e.key === 'ArrowDown' ? currentIdx + 1 : currentIdx - 1;
        if (nextIdx >= 0 && nextIdx < rows.length) {
          const nextId = rows[nextIdx].dataset.entityId;
          if (nextId) {
            inventoryStore.selectSku(nextId);
            rows[nextIdx].focus();
          }
        }
      } else if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
        e.preventDefault();
        inventoryStore.selectSku(itemId);
      }
    },
    []
  );

  const appliedDiffMap = new Map<string, BalanceLineDiff>(
    (state.lastBalanceDiff?.lineDiffs || []).map((d) => [d.skuId, d])
  );
  const manualCount = state.items.filter((it) => Boolean(it.manualOverride)).length;

  const filteredItems = state.items.filter((it) => {
    if (triageFilter === 'deficit') {
      return isSkuAtStockoutRisk(it, state.transitDelayDays, state.backupChannel);
    }
    if (triageFilter === 'manual') return Boolean(it.manualOverride);
    return true;
  });

  const activeSupplier = getSupplier(activeSku.supplierId);
  const activeLeadDays = computeEffectiveLeadDays(activeSku, state.transitDelayDays, state.backupChannel);
  const activeSafetyUnits = Math.round(activeSku.dailyDemand * activeSku.safetyDays);
  const activeTargetStock = activeSku.dailyDemand * activeLeadDays + activeSafetyUnits;
  const stoch = computeStochasticBuffer(activeSku, state.transitDelayDays, state.backupChannel);

  const meterBars = [
    { label: 'Емкость', val: summary.totalPallets, max: summary.effectivePalletLimit },
    { label: 'Бюджет', val: summary.totalBudgetKrub, max: state.constraints.maxBudgetKrub },
    { label: 'Рампа', val: summary.totalWeightKg, max: state.constraints.maxWeightKg }
  ];

  return (
    <article data-card="sku-replenishment-ledger" className="surface-card p-3 flex flex-col gap-2.5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-primary">Ведомость пополнения</h2>
            <span className={`px-2 py-0.5 radius-control text-xs font-medium tabular-nums ${summary.isFeasible ? 'bg-status-success' : 'bg-status-warning'}`}>
              {summary.isFeasible
                ? 'В допуске склада'
                : `Дефицит ${summary.stockoutRiskCount}, перегруз ${summary.overLimitCount}`}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <div className="seg-group" role="group" aria-label="Триаж позиций ведомости">
              <button type="button" data-triage-filter="all" aria-pressed={triageFilter === 'all'} onClick={() => onChangeTriageFilter('all')} className="seg-btn tabular-nums">
                Все {state.items.length}
              </button>
              <button type="button" data-triage-filter="deficit" aria-pressed={triageFilter === 'deficit'} onClick={() => onChangeTriageFilter('deficit')} className="seg-btn tabular-nums">
                Дефицит {summary.stockoutRiskCount}
              </button>
              <button type="button" data-triage-filter="manual" aria-pressed={triageFilter === 'manual'} onClick={() => onChangeTriageFilter('manual')} className="seg-btn tabular-nums">
                Правки {manualCount}
              </button>
            </div>

            <div className="seg-group" role="group" aria-label="Резерв ворот приемки">
              {[2, 4].map((gateReserve) => (
                <button
                  key={gateReserve}
                  type="button"
                  aria-pressed={state.constraints.reserveGatePallets === gateReserve}
                  onClick={() => inventoryStore.updateConstraints({ reserveGatePallets: gateReserve })}
                  className="seg-btn tabular-nums"
                >
                  Ворота {gateReserve} п.
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="ledger-table tabular-nums">
            <thead>
              <tr>
                <th scope="col" className="text-left">Комплектующие</th>
                <th scope="col" className="text-right tabular-nums">Покрытие</th>
                <th scope="col" className="text-right tabular-nums">Партия, шт.</th>
                <th scope="col" className="text-right tabular-nums">Паллеты</th>
                <th scope="col" className="text-right tabular-nums">Сумма</th>
                <th scope="col" className="text-right tabular-nums">Шаг и буфер</th>
              </tr>
            </thead>
            <tbody ref={tbodyRef}>
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-left">
                    <div className="flex flex-wrap items-center justify-between gap-2 py-1">
                      <span className="text-sm text-secondary">По выбранному срезу отклонений сейчас нет.</span>
                      <button type="button" onClick={() => onChangeTriageFilter('all')} className="btn-secondary radius-control">
                        Показать все позиции
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((item, idx) => (
                  <ReplenishmentLedgerRow
                    key={item.id}
                    item={item}
                    idx={idx}
                    isSelected={item.id === state.activeSkuId}
                    transitDelayDays={state.transitDelayDays}
                    backupChannel={state.backupChannel}
                    appliedDiff={appliedDiffMap.get(item.id)}
                    onRowKeyDown={handleRowKeyDown}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="surface-inset px-3 py-2.5 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm tabular-nums">
        {meterBars.map((bar) => {
          const pct = Math.round((bar.val / Math.max(1, bar.max)) * 100);
          return (
            <div key={bar.label} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-secondary">{bar.label}</span>
                <span className="font-semibold text-primary">{pct}%</span>
              </div>
              <div className="h-2 w-full rounded-full" style={{ background: 'var(--surface-1)' }}>
                <div
                  className="h-2 rounded-full"
                  style={{
                    width: `${Math.min(100, pct)}%`,
                    background: bar.val > bar.max ? 'var(--accent-primary)' : 'oklch(0.36 0.068 248)'
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-sm tabular-nums">
        <div>
          <div className="text-muted">ROP + SS</div>
          <div className="font-semibold text-primary">{activeSku.dailyDemand}×{activeLeadDays}+{activeSafetyUnits} = {activeTargetStock}</div>
        </div>
        <div>
          <div className="text-muted">Норма / шаг</div>
          <div className="font-semibold text-primary">Норма {activeRecommendedQty}, шаг {activeSupplier.minBatchQty}</div>
        </div>
        <div data-stochastic-readout="true">
          <div className="text-muted">Буфер σ-SS</div>
          <div className="font-semibold text-primary">SL {stoch.serviceLevelPct}%, σL {stoch.sigmaLeadDays.toFixed(1)}д, SS {stoch.stochasticSafetyUnits}</div>
        </div>
      </div>
    </article>
  );
}
