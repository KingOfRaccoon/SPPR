import { useState } from 'react';
import { inventoryStore } from '../store/domainStore';
import { computeOrderSummary } from '../store/replenishmentEngine';
import {
  buildOrderCsv,
  buildProcurementMemo,
  triggerBrowserCsvDownload
} from '../utils/orderExport';
import { ErpDispatchLedgerCard } from '../components/ErpDispatchLedgerCard';
import { CsvExportIcon, UndoIcon } from '../components/Icons';
import type { InventoryDomainState, OrderCapacitySummary } from '../types/domain';

interface ScreenOrderExportProps {
  state: InventoryDomainState;
}

const ARTIFACT_PRE_CLASS = 'surface-inset p-3 font-mono text-sm text-primary tabular-nums'; /* taste-skill-ignore */

function resolveDockStatus(summary: OrderCapacitySummary): { text: string; cls: string } {
  if (summary.overLimitCount > 0) {
    return { text: 'Требует укладки', cls: 'text-status-danger' };
  }
  if (summary.stockoutRiskCount > 0) {
    return { text: `Габарит ОК, дефицит ${summary.stockoutRiskCount}`, cls: 'text-status-warning' };
  }
  return { text: 'Подтвержден РЦ', cls: 'text-status-success' };
}

export function ScreenOrderExport({ state }: ScreenOrderExportProps) {
  const [copied, setCopied] = useState(false);

  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const artifactText =
    state.exportFormat === 'csv' ? buildOrderCsv(state) : buildProcurementMemo(state);
  const budgetReserve = Number((state.constraints.maxBudgetKrub - summary.totalBudgetKrub).toFixed(1));
  const totalUnits = state.items.reduce((acc, it) => acc + it.orderQty, 0);
  const dockStatus = resolveDockStatus(summary);

  const handleCopyText = () => {
    if (
      typeof navigator !== 'undefined' &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === 'function'
    ) {
      void navigator.clipboard.writeText(artifactText).catch(() => undefined);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
    inventoryStore.recordArtifactExport(
      state.exportFormat === 'csv'
        ? 'Текст спецификации .csv скопирован'
        : 'Пояснительная записка скопирована'
    );
  };

  const handleDownloadCsv = () => {
    triggerBrowserCsvDownload('zapas-navigator-order.csv', buildOrderCsv(state));
    inventoryStore.recordArtifactExport('Выгружен файл спецификации .csv');
  };

  return (
    <section
      data-screen-view="screen-order-export"
      data-shell="order-specification-export"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5"
    >
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch">
        <div className="xl:col-span-7 min-w-0">
          <article
            data-card="order-artifact-preview"
            className="surface-card p-3.5 h-full flex flex-col justify-between gap-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-primary">
                  Спецификация заказа поставщику CSV и записка
                </h1>
                <p className="text-sm text-secondary tabular-nums">
                  {state.waveLabel}, позиций {state.items.length}, паллет {summary.totalPallets.toFixed(1)}
                </p>
              </div>

              <div className="seg-group" role="group" aria-label="Формат выгрузки">
                <button
                  type="button"
                  aria-pressed={state.exportFormat === 'csv'}
                  onClick={() => inventoryStore.setExportFormat('csv')}
                  className="seg-btn"
                >
                  Таблица .csv
                </button>
                <button
                  type="button"
                  aria-pressed={state.exportFormat === 'memo'}
                  onClick={() => inventoryStore.setExportFormat('memo')}
                  className="seg-btn"
                >
                  Записка
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
              <div className="space-y-0.5 min-w-0">
                <div className="flex items-center gap-1.5">
                  <CsvExportIcon size={15} className="text-accent-primary" />
                  <h2 className="text-sm font-semibold text-primary">
                    Итоговый документ для поставщика и склада
                  </h2>
                </div>
                <div className="text-sm text-secondary">{state.exportNotice}</div>
              </div>

              <button
                type="button"
                data-artifact-copy="true"
                data-export-copy="true"
                onClick={handleCopyText}
                className="btn-secondary radius-control shrink-0"
              >
                {copied ? 'Скопировано' : 'Скопировать текст'}
              </button>
            </div>

            <pre
              data-artifact-preview="true"
              data-code-token="true"
              style={{
                margin: 0,
                whiteSpace: 'pre-wrap',
                overflowWrap: 'anywhere',
                wordBreak: 'break-word',
                maxWidth: '100%'
              }}
              className={ARTIFACT_PRE_CLASS}
            >
              {artifactText}
            </pre>

            <div className="surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm tabular-nums">
              <div>
                <span className="text-secondary">Шлюз WMS: </span>
                <strong className="text-primary">Готов, UTF-8</strong>
              </div>
              <div>
                <span className="text-secondary">Ворота: </span>
                <strong className="text-primary">
                  {summary.totalPallets.toFixed(1)} / {summary.effectivePalletLimit} палл.
                </strong>
              </div>
              <div>
                <span className="text-secondary">Резерв: </span>
                <strong className={budgetReserve >= 0 ? 'text-status-success' : 'text-status-danger'}>
                  {budgetReserve.toFixed(1)} тыс. ₽
                </strong>
              </div>
            </div>

            <div className="surface-inset px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs tabular-nums">
              <span className="text-secondary">Разделитель колонок: точка с запятой, числа с точкой</span>
              <span className="font-semibold text-primary">Совместимо с 1С:ERP и WMS</span>
            </div>

            <button
              type="button"
              data-primary-action="true"
              data-artifact-download="true"
              data-export-download="true"
              onClick={handleDownloadCsv}
              className="btn-primary w-full radius-control"
            >
              Скачать спецификацию .csv
            </button>
          </article>
        </div>

        <div className="xl:col-span-5 min-w-0">
          <article
            data-card="order-audit-log"
            data-audit-log="true"
            className="surface-card p-3.5 h-full flex flex-col justify-between gap-2.5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
              <h2 className="text-sm font-semibold text-primary">Журнал согласования и правок</h2>
              <button
                type="button"
                disabled={!inventoryStore.canUndo()}
                onClick={() => inventoryStore.undo()}
                className="btn-ghost radius-control"
              >
                <UndoIcon size={13} />
                <span>Отменить шаг</span>
              </button>
            </div>

            <div className="space-y-1.5 tabular-nums">
              {state.history.slice(0, 4).map((entry) => (
                <div key={entry.id} className="surface-inset px-2.5 py-2 space-y-0.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-primary">{entry.summary}</span>
                    <span className="text-xs text-muted tabular-nums">{entry.timeLabel}</span>
                  </div>
                  <div className="text-sm text-secondary">{entry.detail}</div>
                </div>
              ))}
            </div>

            <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
              <div className="font-semibold text-primary">Контроль отправки в ERP и эффект смены</div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-secondary">Статус габаритного допуска</span>
                <span className={`font-semibold ${dockStatus.cls}`}>{dockStatus.text}</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-secondary">Итоговая сумма заявки</span>
                <span className="font-semibold text-primary">{summary.totalBudgetKrub.toFixed(1)} тыс. ₽</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-secondary">Суммарный объем отгрузки</span>
                <span className="font-semibold text-primary">{totalUnits} шт., {summary.totalWeightKg} кг</span>
              </div>
            </div>
          </article>
        </div>
      </div>

      <ErpDispatchLedgerCard
        items={state.items}
        activeSkuId={state.activeSkuId}
        transitDelayDays={state.transitDelayDays}
        backupChannel={state.backupChannel}
        avgReliabilityPct={summary.avgReliabilityPct}
      />
    </section>
  );
}
