import { BACKUP_CHANNELS, getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeEffectiveLeadDays,
  computeOrderSummary,
  computeRequiredTargetStock,
  isSkuAtStockoutRisk
} from '../store/replenishmentEngine';
import { ShieldClockIcon } from '../components/Icons';
import { CorridorSlaMatrixCard } from '../components/CorridorSlaMatrixCard';
import { TransitBufferInspectorColumn } from '../components/TransitBufferInspectorColumn';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { InventoryDomainState } from '../types/domain';

interface ScreenDeliveryBufferProps {
  state: InventoryDomainState;
}

export function ScreenDeliveryBuffer({ state }: ScreenDeliveryBufferProps) {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
  const activeLeadDays = computeEffectiveLeadDays(
    activeSku,
    state.transitDelayDays,
    state.backupChannel
  );
  const channelInfo = BACKUP_CHANNELS[state.backupChannel];
  const channelShiftLabel =
    channelInfo.leadDeltaDays <= 0 ? `${channelInfo.leadDeltaDays}` : `+${channelInfo.leadDeltaDays}`;

  return (
    <section
      data-screen-view="screen-delivery-buffer"
      data-shell="transit-buffer-matrix"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5"
    >
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start">
        <div className="xl:col-span-7 min-w-0">
          <article data-card="transit-risk-matrix" className="surface-card p-3.5 space-y-2.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2 min-w-0">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-primary">
                  Страховка сроков при задержках в пути
                </h1>
                <p className="text-sm text-secondary tabular-nums">
                  Канал: {channelInfo.label}, задержка маршрута +{state.transitDelayDays} сут.
                </p>
              </div>
              <span className="text-sm font-semibold text-secondary tabular-nums">
                Риск дефицита: {summary.stockoutRiskCount} поз., плечо {summary.avgLeadDays.toFixed(1)} сут.
              </span>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
              <div className="flex items-center gap-1.5">
                <ShieldClockIcon size={15} className="text-accent-primary" />
                <h2 className="text-sm font-semibold text-primary">
                  Матрица покрытия полки и страхового запаса
                </h2>
              </div>
              <span className="text-xs text-muted">Нажмите на буфер для сдвига дней</span>
            </div>

            <div className="overflow-x-auto">
              <table className="ledger-table tabular-nums">
                <thead>
                  <tr>
                    <th scope="col" className="text-left">Позиция</th>
                    <th scope="col" className="text-right tabular-nums">Полка</th>
                    <th scope="col" className="text-right tabular-nums">В пути</th>
                    <th scope="col" className="text-left">Статус</th>
                    <th scope="col" className="text-right tabular-nums">Буфер</th>
                  </tr>
                </thead>
                <tbody>
                  {state.items.map((item, idx) => {
                    const lead = computeEffectiveLeadDays(item, state.transitDelayDays, state.backupChannel);
                    const shelfDays = Number((item.currentStock / Math.max(1, item.dailyDemand)).toFixed(1));
                    const target = computeRequiredTargetStock(item, state.transitDelayDays, state.backupChannel);
                    const atRisk = isSkuAtStockoutRisk(item, state.transitDelayDays, state.backupChannel);
                    const sup = getSupplier(item.supplierId);
                    const isSelected = item.id === state.activeSkuId;

                    return (
                      <tr
                        key={item.id}
                        data-entity-id={item.id}
                        data-selected={isSelected ? 'true' : undefined}
                        tabIndex={0}
                        aria-current={isSelected ? 'true' : undefined}
                        style={{ borderBottomWidth: 0 }}
                        onClick={() => inventoryStore.selectSku(item.id)}
                        onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectSku(item.id))}
                        className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
                      >
                        <td className="text-left">
                          <div className="text-sm font-semibold text-primary">{item.name}</div>
                          <div className="text-xs text-muted">{sup.name}, цель {target} шт.</div>
                        </td>
                        <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">
                          {shelfDays.toFixed(1)} сут.
                        </td>
                        <td className="text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums">
                          {lead} сут.
                        </td>
                        <td className="text-left whitespace-nowrap">
                          <span className={`px-2 py-0.5 radius-control text-xs font-medium ${atRisk ? 'bg-status-danger' : 'bg-status-success'}`}>
                            {atRisk ? 'Дозаказ' : 'Покрыто'}
                          </span>
                        </td>
                        <td className="text-right whitespace-nowrap tabular-nums" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            aria-label={`${item.safetyDays} сут.: изменить страховой буфер ${item.name}`}
                            onClick={() => inventoryStore.cycleSafetyDays(item.id)}
                            className="btn-row tabular-nums"
                          >
                            {item.safetyDays} сут.
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="surface-inset p-3 space-y-2 text-sm tabular-nums">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-primary">Баланс страхового горизонта РЦ Москва</span>
                <span className="text-secondary">
                  Сдвиг канала: {channelShiftLabel} сут., тариф +{channelInfo.costSurchargePct}%
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div>
                  <div className="text-secondary">Защищено буфером</div>
                  <div className="font-semibold text-primary">
                    {state.items.length - summary.stockoutRiskCount} из {state.items.length} поз.
                  </div>
                </div>
                <div>
                  <div className="text-secondary">Среднее плечо пула</div>
                  <div className="font-semibold text-primary">
                    {summary.avgLeadDays.toFixed(1)} сут. (откл. +{state.transitDelayDays} сут.)
                  </div>
                </div>
                <div>
                  <div className="text-secondary">Загрузка приемки</div>
                  <div className="font-semibold text-primary">
                    {summary.totalPallets.toFixed(1)} из {summary.effectivePalletLimit} палл.
                  </div>
                </div>
              </div>
              <div className="text-secondary">
                Регламент смены: при задержке от +4 суток позиции с полкой менее {activeLeadDays} сут. переводятся на ускоренный коридор или получают +2 сут. страхового запаса.
              </div>
            </div>
          </article>
        </div>

        <TransitBufferInspectorColumn state={state} activeSku={activeSku} />
      </div>

      <CorridorSlaMatrixCard
        items={state.items}
        activeSkuId={state.activeSkuId}
        transitDelayDays={state.transitDelayDays}
        backupChannel={state.backupChannel}
        channelLabel={channelInfo.label}
        channelLeadDeltaDays={channelInfo.leadDeltaDays}
        channelCostSurchargePct={channelInfo.costSurchargePct}
      />
    </section>
  );
}
