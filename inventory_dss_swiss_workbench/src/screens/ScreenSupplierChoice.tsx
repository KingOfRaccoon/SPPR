import { getSupplier } from '../data/presets';
import { SUPPLIER_CONTRACT_TERMS } from '../data/supplierContracts';
import { inventoryStore } from '../store/domainStore';
import {
  computeItemCostKrub,
  computeOrderSummary,
  computeSupplierNegotiationImpact
} from '../store/replenishmentEngine';
import { SupplierContractMatrixCard } from '../components/SupplierContractMatrixCard';
import { SupplierReliabilityChartCard } from '../components/SupplierReliabilityChartCard';
import type { InventoryDomainState } from '../types/domain';

interface ScreenSupplierChoiceProps {
  state: InventoryDomainState;
}

function formatSignedValue(value: number, decimals: number): string {
  const formatted = value.toFixed(decimals);
  return value > 0 ? `+${formatted}` : formatted;
}

function formatSignedInt(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

export function ScreenSupplierChoice({ state }: ScreenSupplierChoiceProps) {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
  const selectedSupplier = getSupplier(state.selectedSupplierId);
  const selectedContract =
    SUPPLIER_CONTRACT_TERMS[selectedSupplier.id] || SUPPLIER_CONTRACT_TERMS['balt-komplekt'];

  const currentLineTotal = computeItemCostKrub(activeSku, state.backupChannel);
  const candidateLineTotal = computeItemCostKrub(
    { ...activeSku, supplierId: selectedSupplier.id },
    state.backupChannel
  );
  const lineDelta = Number((candidateLineTotal - currentLineTotal).toFixed(1));
  const negImpact = computeSupplierNegotiationImpact(
    activeSku,
    selectedSupplier.id,
    state.transitDelayDays,
    state.backupChannel
  );

  return (
    <section
      data-screen-view="screen-supplier-choice"
      data-shell="supplier-comparison-chart"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5"
    >
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch">
        <div className="xl:col-span-7 min-w-0">
          <SupplierReliabilityChartCard
            activeSku={activeSku}
            selectedSupplier={selectedSupplier}
            selectedSupplierId={state.selectedSupplierId}
            summary={summary}
          />
        </div>

        <div className="xl:col-span-5 min-w-0">
          <article
            data-card="supplier-terms-comparison"
            className="surface-card p-3.5 h-full flex flex-col justify-between gap-2.5"
          >
            <div className="space-y-1">
              <div className="text-xs text-muted">Карточка площадки отгрузки и регламент SLA</div>
              <h2 className="text-base font-semibold text-primary">
                {selectedSupplier.name} – {selectedSupplier.city}
              </h2>
              <p className="text-sm text-secondary">{selectedSupplier.termsNote}</p>
            </div>

            <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Пунктуальность OTIF</span>
                <span className="font-semibold text-primary text-right">
                  {selectedSupplier.reliabilityPct.toFixed(1)}% в срок, {selectedContract.leadVariance}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Плечо и мин. партия MOQ</span>
                <span className="font-semibold text-primary text-right">
                  {selectedSupplier.leadDays} сут., от {selectedSupplier.minBatchQty} шт.
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Базис и тарный норматив</span>
                <span className="font-semibold text-primary text-right">{selectedContract.incoterms}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Отсрочка и штраф за просрочку</span>
                <span className="font-semibold text-primary text-right">
                  {selectedContract.deferralDays} сут., пени {selectedContract.slaPenaltyPct}/дн.
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Кратность паллетной отгрузки</span>
                <span className="font-semibold text-primary text-right">{selectedContract.packaging}</span>
              </div>
            </div>

            <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Строка «{activeSku.name}»</span>
                <span className="font-semibold text-primary text-right whitespace-nowrap">
                  {currentLineTotal.toFixed(1)} → {candidateLineTotal.toFixed(1)} тыс. ₽
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="text-muted">Разница по текущей партии</span>
                <span
                  className={
                    lineDelta <= 0 ? 'font-semibold text-status-success text-right' : 'font-semibold text-status-warning text-right'
                  }
                >
                  {formatSignedValue(lineDelta, 1)} тыс. ₽
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="text-muted">Входной контроль ОТК на рампе</span>
                <span className="font-semibold text-primary text-right">Выборка 10%, штрихкод SSCC</span>
              </div>
            </div>

            <div
              data-supplier-negotiation-impact="true"
              className="surface-inset px-3 py-2 space-y-1 text-xs tabular-nums"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Закупка, σ-SS и риск</span>
                <span className="font-semibold text-primary text-right">
                  {formatSignedValue(negImpact.lineCostDeltaKrub, 1)}к, σ{' '}
                  {formatSignedInt(negImpact.sigmaBufferDeltaUnits)} шт., риск{' '}
                  {formatSignedValue(negImpact.riskDeltaKrub, 1)}к
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Вердикт TCO</span>
                <span
                  className={
                    negImpact.netImpactKrub >= 0
                      ? 'font-semibold text-status-success text-right'
                      : 'font-semibold text-status-warning text-right'
                  }
                >
                  {negImpact.verdict}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <button
                type="button"
                disabled={activeSku.supplierId === selectedSupplier.id}
                onClick={() => inventoryStore.updateSkuSupplier(activeSku.id, selectedSupplier.id)}
                className="btn-secondary w-full radius-control"
              >
                {activeSku.supplierId === selectedSupplier.id
                  ? 'Закреплен за активной позицией'
                  : `Закрепить ${selectedSupplier.name} за позицией`}
              </button>

              <button
                type="button"
                data-primary-action="true"
                onClick={() => inventoryStore.assignOptimalSuppliers()}
                className="btn-primary w-full radius-control"
              >
                Назначить лучших поставщиков
              </button>
            </div>
          </article>
        </div>
      </div>

      <SupplierContractMatrixCard
        items={state.items}
        backupChannel={state.backupChannel}
        selectedSupplierId={state.selectedSupplierId}
        selectedSupplierName={selectedSupplier.name}
      />
    </section>
  );
}
