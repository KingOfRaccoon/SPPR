import { BACKUP_CHANNELS } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeCostOfInaction,
  computeEffectiveLeadDays,
  computeRequiredTargetStock,
  computeStochasticBuffer
} from '../store/replenishmentEngine';
import { SawtoothProjectionChart } from './SawtoothProjectionChart';
import type { BackupChannelMode, InventoryDomainState, SkuItem, TransitDelayDays } from '../types/domain';

const DELAY_OPTIONS: Array<{ days: TransitDelayDays; label: string }> = [
  { days: 0, label: 'По графику 0д' },
  { days: 4, label: 'Задержка +4д' },
  { days: 9, label: 'Граница +9д' }
];

function formatChannelOptionLabel(ch: { id: BackupChannelMode; label: string; costSurchargePct: number }): string {
  if (ch.id === 'express_auto') return `Ускоренный авто (+${ch.costSurchargePct}%)`;
  if (ch.id === 'regional_hub') return `Региональный хаб (+${ch.costSurchargePct}%)`;
  return `${ch.label} (+${ch.costSurchargePct}%)`;
}

export function TransitBufferInspectorColumn({
  state,
  activeSku
}: {
  state: InventoryDomainState;
  activeSku: SkuItem;
}) {
  const activeLeadDays = computeEffectiveLeadDays(activeSku, state.transitDelayDays, state.backupChannel);
  const activeRunoutDays = Number((activeSku.currentStock / Math.max(1, activeSku.dailyDemand)).toFixed(1));
  const activeTotalCoverDays = Number(
    ((activeSku.currentStock + activeSku.orderQty) / Math.max(1, activeSku.dailyDemand)).toFixed(1)
  );
  const activeTarget = computeRequiredTargetStock(activeSku, state.transitDelayDays, state.backupChannel);
  const activeStoch = computeStochasticBuffer(activeSku, state.transitDelayDays, state.backupChannel);
  const activeCoi = computeCostOfInaction(activeSku, state.transitDelayDays, state.backupChannel);

  return (
    <div className="xl:col-span-5 flex flex-col gap-3.5 min-w-0">
      <article data-card="backup-channel-controls" className="surface-card p-3.5 space-y-3">
        <h2 className="text-sm font-semibold text-primary">
          Сценарий задержки на маршруте и резервный канал
        </h2>

        <div className="seg-group flex-wrap" role="group" aria-label="Поправка задержки">
          {DELAY_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              aria-pressed={state.transitDelayDays === opt.days}
              onClick={() => inventoryStore.setTransitScenario(opt.days, state.backupChannel)}
              className="seg-btn tabular-nums"
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="space-y-1">
          <label htmlFor="backup-channel-select" className="block text-xs font-medium text-secondary">
            Логистический канал доставки
          </label>
          <select
            id="backup-channel-select"
            value={state.backupChannel}
            onChange={(e) =>
              inventoryStore.setTransitScenario(state.transitDelayDays, e.target.value as BackupChannelMode)
            }
            className="w-full field-compact"
          >
            {Object.values(BACKUP_CHANNELS).map((ch) => (
              <option key={ch.id} value={ch.id}>
                {formatChannelOptionLabel(ch)}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          data-primary-action="true"
          onClick={() => inventoryStore.reinforceDeliveryBuffer()}
          className="btn-primary w-full radius-control"
        >
          Усилить страховой запас
        </button>
      </article>

      <article data-card="active-sku-runout-readout" className="surface-card p-3.5 space-y-2.5">
        <div className="space-y-0.5">
          <div className="text-xs text-muted">Расчет страховки по активной позиции</div>
          <h2 className="text-sm font-semibold text-primary">{activeSku.name}</h2>
        </div>

        <div className="surface-inset p-2.5 space-y-1 text-sm tabular-nums">
          <div className="flex items-center justify-between gap-2">
            <span className="text-secondary">Полка до обнуления / В пути</span>
            <span className="font-semibold text-primary">
              {activeRunoutDays} сут. / приход Д+{activeLeadDays}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-secondary">Покрытие с учетом дозаказа</span>
            <span className="font-semibold text-primary">
              {activeTotalCoverDays} сут. ({activeSku.currentStock + activeSku.orderQty} из {activeTarget} шт.)
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-secondary">Стохастический буфер σ-SS</span>
            <span className="font-semibold text-primary tabular-nums">
              SL {activeStoch.serviceLevelPct}%, Z={activeStoch.zScore}, σL={activeStoch.sigmaLeadDays.toFixed(1)} сут.
            </span>
          </div>
          {activeCoi.riskKrub > 0 && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-secondary">Риск простоя (не заказывать)</span>
              <span className="font-semibold text-status-danger tabular-nums">
                {Math.round(activeCoi.riskKrub)} тыс. ₽
              </span>
            </div>
          )}
        </div>

        <SawtoothProjectionChart
          item={activeSku}
          transitDelayDays={state.transitDelayDays}
          backupChannel={state.backupChannel}
          compact
        />
      </article>
    </div>
  );
}
