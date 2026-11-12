import { useState } from 'react';
import type { InboundFlowArc, OutboundFlowArc } from '../data/flowNetwork';
import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { SelectedMapNodeId } from '../types/domain';

type LedgerFilter = 'all' | 'inbound' | 'outbound';

interface SupplyCorridorLedgerProps {
  inbound: InboundFlowArc[];
  outbound: OutboundFlowArc[];
  selectedNodeId: SelectedMapNodeId;
}

function getInboundBadge(flow: InboundFlowArc): { cls: string; text: string } {
  if (flow.atRisk) return { cls: 'bg-status-danger', text: 'Риск срока' };
  if (flow.skuCount === 0) return { cls: 'surface-inset text-secondary', text: 'Резерв' };
  return { cls: 'bg-status-success', text: 'По графику' };
}

function getOutboundBadgeClass(status: OutboundFlowArc['status']): string {
  if (status === 'ready') return 'bg-status-success';
  if (status === 'gate_wait') return 'bg-status-warning';
  return 'bg-status-danger';
}

export function SupplyCorridorLedger({
  inbound,
  outbound,
  selectedNodeId
}: SupplyCorridorLedgerProps) {
  const [ledgerFilter, setLedgerFilter] = useState<LedgerFilter>('all');

  return (
    <article data-card="inbound-outbound-ledger" className="surface-card p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-primary">
            Реестр направлений: поставки в РЦ и отгрузки клиентам
          </h2>
          <p className="text-xs text-muted">Выберите строку маршрута для фокуса на карте</p>
        </div>

        <div className="seg-group" role="group" aria-label="Фильтр таблицы плеч">
          <button
            type="button"
            aria-pressed={ledgerFilter === 'all'}
            onClick={() => setLedgerFilter('all')}
            className="seg-btn"
          >
            Все 8 плеч
          </button>
          <button
            type="button"
            aria-pressed={ledgerFilter === 'inbound'}
            onClick={() => setLedgerFilter('inbound')}
            className="seg-btn"
          >
            Вход в РЦ
          </button>
          <button
            type="button"
            aria-pressed={ledgerFilter === 'outbound'}
            onClick={() => setLedgerFilter('outbound')}
            className="seg-btn"
          >
            Клиентам
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Маршрут</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Контрагент и груз</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Статус</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Плечо</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Паллеты</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Масса</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Срок</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Сумма</th>
            </tr>
          </thead>
          <tbody>
            {ledgerFilter !== 'outbound' &&
              inbound.map((f, idx) => {
                const isSel = selectedNodeId === f.id;
                const badge = getInboundBadge(f);
                return (
                  <tr
                    key={`row-in-${f.id}`}
                    data-selected={isSel ? 'true' : undefined}
                    tabIndex={0}
                    aria-current={isSel ? 'true' : undefined}
                    style={{ borderBottomWidth: 0 }}
                    onClick={() => inventoryStore.selectMapNode(f.id)}
                    onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectMapNode(f.id))}
                    className={`cursor-pointer ${!isSel && idx % 2 === 1 ? 'surface-inset' : ''}`}
                  >
                    <td className="text-left text-sm font-semibold text-primary">Вход: {f.city}</td>
                    <td className="text-left text-sm text-secondary">{f.supplierName}, {f.skuCount} поз.</td>
                    <td className="text-left whitespace-nowrap">
                      <span className={`px-2 py-0.5 radius-control text-xs font-medium ${badge.cls}`}>
                        {badge.text}
                      </span>
                    </td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{f.geo.distanceKm} км</td>
                    <td className="text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums">{f.pallets.toFixed(1)} палл.</td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{f.weightKg} кг</td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{f.leadDays} сут.</td>
                    <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{f.budgetKrub.toFixed(1)} тыс. ₽</td>
                  </tr>
                );
              })}

            {ledgerFilter !== 'inbound' &&
              outbound.map((o, idx) => {
                const isSel = selectedNodeId === o.id;
                const firstSup = o.peggedSuppliers[0] ? getSupplier(o.peggedSuppliers[0]).city : 'РЦ';
                return (
                  <tr
                    key={`row-out-${o.id}`}
                    data-selected={isSel ? 'true' : undefined}
                    tabIndex={0}
                    aria-current={isSel ? 'true' : undefined}
                    style={{ borderBottomWidth: 0 }}
                    onClick={() => inventoryStore.selectMapNode(o.id)}
                    onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectMapNode(o.id))}
                    className={`cursor-pointer ${!isSel && idx % 2 === 0 ? 'surface-inset' : ''}`}
                  >
                    <td className="text-left text-sm font-semibold text-primary">Вывоз: {o.city}</td>
                    <td className="text-left text-sm text-secondary">{o.customerName}, база {firstSup}</td>
                    <td className="text-left whitespace-nowrap">
                      <span className={`px-2 py-0.5 radius-control text-xs font-medium ${getOutboundBadgeClass(o.status)}`}>
                        {o.statusLabel}
                      </span>
                    </td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{o.geo.distanceKm} км</td>
                    <td className="text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums">{o.pallets.toFixed(1)} палл.</td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{o.weightKg} кг</td>
                    <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{o.dispatchWindowDays} сут.</td>
                    <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{o.valueKrub.toFixed(1)} тыс. ₽</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </article>
  );
}
