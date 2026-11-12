import { BACKUP_CHANNELS, SCENARIO_PRESETS } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import type {
  InventoryDomainState,
  OrderCapacitySummary,
  ScreenId,
  ViewState
} from '../types/domain';

const SCREEN_TITLES: Record<ScreenId, string> = {
  'screen-replenishment-notebook': 'Расчет партий дозаказа и емкости склада',
  'screen-supply-map': 'Карта входящих поставок и клиентских отгрузок',
  'screen-warehouse-limits': 'Ограничения паллетомест, массы и бюджета',
  'screen-supplier-choice': 'Сравнение поставщиков по цене и срокам',
  'screen-delivery-buffer': 'Страховка сроков при задержках в пути',
  'screen-order-export': 'Спецификация заказа поставщику CSV и записка'
};

interface StateFallbackViewProps {
  state: InventoryDomainState;
  summary: OrderCapacitySummary;
  viewState: Exclude<ViewState, 'Ideal'>;
  onRecoverToIdeal: () => void;
}

export function StateFallbackView({ state, summary, viewState, onRecoverToIdeal }: StateFallbackViewProps) {
  const screenTitle = SCREEN_TITLES[state.activeScreenId] || SCREEN_TITLES['screen-replenishment-notebook'];
  const channel = BACKUP_CHANNELS[state.backupChannel];

  return (
    <section
      data-screen-view={state.activeScreenId}
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5"
    >
      <article
        data-card="inframe-screen-header"
        className="surface-card p-3.5 flex flex-wrap items-center justify-between gap-2"
      >
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-primary">{screenTitle}</h1>
          <p className="text-sm text-secondary">{state.waveLabel}</p>
        </div>
        <div className="seg-group" role="group" aria-label="Сценарии снабжения">
          {SCENARIO_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              aria-pressed={state.activePresetId === preset.id}
              onClick={() => {
                inventoryStore.loadPreset(preset.id);
                onRecoverToIdeal();
              }}
              className="seg-btn"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </article>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start">
        <div className="xl:col-span-8 min-w-0">
          {viewState === 'Loading' && (
            <article
              data-card="loading-skeleton"
              role="status"
              aria-live="polite"
              aria-busy="true"
              className="surface-card p-4 space-y-3"
            >
              <span className="sr-only">Загрузка ведомости запасов...</span>
              <div className="text-sm font-medium text-secondary">
                Синхронизация остатков ячеек приемки и графиков отгрузки поставщиков...
              </div>
              <div className="h-6 w-72 skeleton-bar" />
              <div className="h-16 w-full skeleton-bar" />
              <div className="h-16 w-full skeleton-bar" />
              <div className="h-16 w-full skeleton-bar" />
            </article>
          )}

          {viewState === 'Empty' && (
            <article data-card="empty-ledger" className="surface-card p-5 space-y-3.5">
              <div className="space-y-2">
                <span className="inline-flex px-2 py-0.5 radius-control surface-inset text-xs font-medium text-secondary">
                  Пустая закупочная волна
                </span>
                <h2 className="text-base font-semibold text-primary">
                  В текущей закупочной волне пока нет позиций к заказу
                </h2>
                <p className="text-sm text-secondary">
                  Загрузите типовой сценарий спроса для расчета паллет и бюджета.
                </p>
              </div>
              <div className="surface-inset p-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-secondary tabular-nums">
                <div>Шаблон 1: Осенний пик, 46 палл.</div>
                <div>Шаблон 2: Граница, сдвиг +9 сут.</div>
                <div>Шаблон 3: Сжатый склад, 34 палл.</div>
              </div>
              <div>
                <button
                  type="button"
                  data-primary-action="true"
                  onClick={() => {
                    inventoryStore.loadPreset('preset-seasonal-peak');
                    onRecoverToIdeal();
                  }}
                  className="btn-primary radius-control"
                >
                  Загрузить ведомость пикового спроса
                </button>
              </div>
            </article>
          )}

          {viewState === 'Error' && (
            <article data-card="error-ledger" role="alert" className="surface-card p-5 space-y-3.5">
              <div className="space-y-2">
                <div className="inline-flex px-2 py-0.5 radius-control bg-status-danger text-xs font-semibold">
                  Черновик ведомости требует восстановления
                </div>
                <h2 className="text-base font-semibold text-primary">
                  Локальная копия закупочного расчета прервана при обновлении вкладки
                </h2>
                <p className="text-sm text-secondary">
                  Нормативы склада сохранены, восстановите ведомость одним нажатием.
                </p>
              </div>
              <div className="surface-inset p-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-secondary tabular-nums">
                <div>Код: ERR_LEDGER_SNAPSHOT</div>
                <div>Резерв: {summary.effectivePalletLimit} палл.</div>
                <div>Канал: {channel.label}</div>
              </div>
              <div>
                <button
                  type="button"
                  data-primary-action="true"
                  onClick={() => {
                    inventoryStore.resetToSeed();
                    onRecoverToIdeal();
                  }}
                  className="btn-primary radius-control"
                >
                  Восстановить эталонную ведомость
                </button>
              </div>
            </article>
          )}
        </div>

        <div className="xl:col-span-4 min-w-0">
          <article data-card="inframe-warehouse-parameters" className="surface-card p-4 space-y-2.5">
            <h2 className="text-sm font-semibold text-primary">Действующие нормативы зоны приемки</h2>
            <div className="surface-inset p-3 space-y-2 text-sm tabular-nums">
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Лимит паллетомест</span>
                <span className="font-semibold text-primary">{summary.effectivePalletLimit} палл.</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Несущий порог рампы</span>
                <span className="font-semibold text-primary">{state.constraints.maxWeightKg} кг</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Потолок бюджета волны</span>
                <span className="font-semibold text-primary">{state.constraints.maxBudgetKrub} тыс. ₽</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary">Логистический канал</span>
                <span className="font-semibold text-primary">{channel.label}</span>
              </div>
            </div>
            <p className="text-xs text-muted">Параметры приемки и журнал активны в сессии.</p>
          </article>
        </div>
      </div>
    </section>
  );
}
