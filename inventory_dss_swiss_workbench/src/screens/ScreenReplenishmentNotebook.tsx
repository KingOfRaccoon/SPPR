import { useState } from 'react';
import { SCENARIO_PRESETS } from '../data/presets';
import { useAnimatedNumber } from '../hooks/useAnimatedNumber';
import { inventoryStore } from '../store/domainStore';
import {
  computeOrderSummary,
  computeRecommendedOrderQty,
  computeWaveFinancialSummary
} from '../store/replenishmentEngine';
import { CapacityHorizonChart } from '../components/CapacityHorizonChart';
import { ReplenishmentInspectorColumn } from '../components/ReplenishmentInspectorColumn';
import { ReplenishmentLedgerTable, TriageFilter } from '../components/ReplenishmentLedgerTable';
import { CsvExportIcon, PlusIcon } from '../components/Icons';
import type { InventoryDomainState } from '../types/domain';

interface ScreenReplenishmentNotebookProps {
  state: InventoryDomainState;
  onOpenAddModal: () => void;
}

export function ScreenReplenishmentNotebook({
  state,
  onOpenAddModal
}: ScreenReplenishmentNotebookProps) {
  const [triageFilter, setTriageFilter] = useState<TriageFilter>('all');

  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const animatedPallets = useAnimatedNumber(summary.totalPallets, 160);
  const animatedBudget = useAnimatedNumber(summary.totalBudgetKrub, 160);

  const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
  const activeRecommendedQty = computeRecommendedOrderQty(
    activeSku,
    state.transitDelayDays,
    state.backupChannel
  );
  const waveFin = computeWaveFinancialSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );

  return (
    <section
      data-screen-view="screen-replenishment-notebook"
      data-paradigm="editorial-notebook"
      data-signature="swiss-replenishment-solver-ledger"
      data-shell="replenishment-ledger"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3 space-y-3"
    >
      <article
        data-card="constraint-solver-strip"
        data-constraint-solver="warehouse-capacity"
        className="surface-card p-3 space-y-2"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight text-primary">
              Расчет партий дозаказа и емкости склада
            </h1>
            <p className="text-sm text-secondary">{state.waveLabel}</p>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 min-w-0">
            <div className="seg-group" role="group" aria-label="Сценарии снабжения">
              {SCENARIO_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  data-scenario-preset={preset.id}
                  aria-pressed={state.activePresetId === preset.id}
                  onClick={() => inventoryStore.loadPreset(preset.id)}
                  className="seg-btn"
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <button
              type="button"
              data-open-create-modal="true"
              data-create-trigger="true"
              onClick={onOpenAddModal}
              className="btn-secondary radius-control shrink-0"
            >
              <PlusIcon size={13} />
              <span>Позиция</span>
            </button>

            <button
              type="button"
              data-export-artifact="true"
              onClick={() => inventoryStore.setScreen('screen-order-export')}
              className="btn-ghost radius-control shrink-0"
            >
              <CsvExportIcon size={13} />
              <span>CSV</span>
            </button>
          </div>
        </div>

        <div className="surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 items-center tabular-nums">
          <div className="flex flex-wrap items-baseline justify-between gap-1.5 min-w-0">
            <div>
              <div className="text-sm text-secondary">Паллетоместа</div>
              <div data-hero-metric="true" className="hero-metric">
                {animatedPallets.toFixed(1)} палл.
              </div>
            </div>
            <span className="text-sm text-secondary font-medium">
              лимит {summary.effectivePalletLimit}
              <span className="text-muted">, {waveFin.discreteRampSlots} слот.</span>
            </span>
          </div>

          <div className="flex flex-wrap items-baseline justify-between gap-1.5 min-w-0">
            <div>
              <div className="text-sm text-secondary">Бюджет заявки</div>
              <div className="text-base font-bold text-primary">
                {animatedBudget.toFixed(1)} тыс. ₽
              </div>
            </div>
            <span className="text-sm text-secondary">
              из {state.constraints.maxBudgetKrub} тыс.
            </span>
          </div>

          <div className="flex flex-wrap items-baseline justify-between gap-1.5 min-w-0">
            <div>
              <div className="text-sm text-secondary">Масса отгрузки</div>
              <div className="text-base font-bold text-primary">
                {summary.totalWeightKg} кг
              </div>
            </div>
            <span className="text-sm text-secondary">
              рампа {state.constraints.maxWeightKg} кг
            </span>
          </div>

          <div className="flex flex-wrap items-baseline justify-between gap-1.5 min-w-0">
            <div>
              <div className="text-sm text-secondary">Цена бездействия</div>
              <div
                data-cost-of-inaction-total="true"
                className={`text-base font-bold ${waveFin.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'}`}
              >
                {waveFin.totalCostOfInactionKrub > 0
                  ? `Риск ${Math.round(waveFin.totalCostOfInactionKrub)}к ₽`
                  : 'Риск 0 ₽, защищено'}
              </div>
            </div>
            <span className="text-sm text-secondary">
              SLA {summary.avgReliabilityPct.toFixed(1)}%, {summary.avgLeadDays.toFixed(1)}д
            </span>
          </div>
        </div>

        <CapacityHorizonChart
          state={state}
          onSelectSku={(id) => inventoryStore.selectChartSku(id)}
        />
      </article>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start">
        <div className="xl:col-span-8 min-w-0">
          <ReplenishmentLedgerTable
            state={state}
            summary={summary}
            activeSku={activeSku}
            activeRecommendedQty={activeRecommendedQty}
            triageFilter={triageFilter}
            onChangeTriageFilter={setTriageFilter}
          />
        </div>

        <ReplenishmentInspectorColumn
          state={state}
          activeSku={activeSku}
          activeRecommendedQty={activeRecommendedQty}
        />
      </div>
    </section>
  );
}
