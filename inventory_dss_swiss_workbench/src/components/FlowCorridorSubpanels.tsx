import {
  CENTRAL_HUB_META,
  InboundFlowArc,
  OutboundFlowArc
} from '../data/flowNetwork';
import { inventoryStore } from '../store/domainStore';
import { computeItemPallets } from '../store/replenishmentEngine';
import type {
  FlowLensMode,
  InventoryDomainState,
  OrderCapacitySummary
} from '../types/domain';

export { SkuPeggingPanel } from './FlowCorridorPeggingPanel';

export function resolveHeaderTitle(
  lens: FlowLensMode,
  selectedInbound?: InboundFlowArc,
  selectedOutbound?: OutboundFlowArc
): string {
  if (lens === 'sku_peg') return 'Сквозная трасса позиции';
  if (selectedInbound) return 'Входящий коридор';
  if (selectedOutbound) return 'Поставка заказчику';
  return 'Узел консолидации';
}

export function resolveOutboundStatusColor(status: OutboundFlowArc['status']): string {
  if (status === 'ready') return 'text-status-success';
  if (status === 'gate_wait') return 'text-status-warning';
  return 'text-status-danger';
}

export function InboundCorridorPanel({
  selectedInbound,
  dependentCustomers
}: {
  selectedInbound: InboundFlowArc;
  dependentCustomers: OutboundFlowArc[];
}) {
  return (
    <div className="space-y-2.5">
      <div>
        <h2 className="text-base font-semibold text-primary">
          {selectedInbound.supplierName}, {selectedInbound.city}
        </h2>
        <p className="text-xs text-muted tabular-nums">
          {selectedInbound.geo.highwayLabel}, {selectedInbound.geo.distanceKm} км,{' '}
          {selectedInbound.geo.gateLabel}
        </p>
      </div>

      <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Объем в волне</span>
          <span className="font-semibold text-primary">
            {selectedInbound.pallets.toFixed(1)} палл., {selectedInbound.weightKg} кг
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Срок до ворот РЦ</span>
          <span className="font-semibold text-primary">
            {selectedInbound.leadDays} сут., OTIF {selectedInbound.reliabilityPct}%
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Сумма отгрузки</span>
          <span className="font-semibold text-primary">{selectedInbound.budgetKrub.toFixed(1)} тыс. ₽</span>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-secondary">Номенклатура в пути, {selectedInbound.skuCount} поз.:</div>
        {selectedInbound.items.length === 0 ? (
          <div className="surface-inset p-2 text-xs text-muted">
            Заказы волны распределены на соседние площадки
          </div>
        ) : (
          <div className="space-y-1">
            {selectedInbound.items.map((it) => (
              <div key={it.id} className="surface-inset px-2.5 py-1.5 flex items-center justify-between gap-2 text-xs tabular-nums">
                <span className="font-medium text-primary">{it.name}</span>
                <span className="text-secondary shrink-0">{it.orderQty} шт., {computeItemPallets(it).toFixed(1)} п.</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-secondary">Связанные получатели:</div>
        <div className="flex flex-wrap gap-1.5">
          {dependentCustomers.length === 0 ? (
            <span className="text-xs text-muted">Прямых блокировок нет</span>
          ) : (
            dependentCustomers.map((dc) => (
              <button key={dc.id} type="button" onClick={() => inventoryStore.selectMapNode(dc.id)} className="btn-row text-xs">
                {dc.city}, {dc.dispatchWindowLabel}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function OutboundCorridorPanel({ selectedOutbound }: { selectedOutbound: OutboundFlowArc }) {
  return (
    <div className="space-y-2.5">
      <div>
        <h2 className="text-base font-semibold text-primary">{selectedOutbound.customerName}</h2>
        <p className="text-xs text-muted tabular-nums">
          {selectedOutbound.city}, {selectedOutbound.geo.highwayLabel}, {selectedOutbound.geo.distanceKm} км
        </p>
      </div>

      <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Статус комплектации</span>
          <span className={`font-semibold ${resolveOutboundStatusColor(selectedOutbound.status)}`}>
            {selectedOutbound.statusLabel}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Окно и объем вывоза</span>
          <span className="font-semibold text-primary">
            {selectedOutbound.dispatchWindowLabel}, {selectedOutbound.pallets.toFixed(1)} палл.
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Товарная стоимость</span>
          <span className="font-semibold text-primary">{selectedOutbound.valueKrub.toFixed(1)} тыс. ₽</span>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-secondary">Состав отгрузки и заводы:</div>
        <div className="space-y-1">
          {selectedOutbound.lines.map((ln) => (
            <div key={`${selectedOutbound.id}-${ln.skuId}`} className="surface-inset px-2.5 py-1.5 space-y-0.5 text-xs tabular-nums">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-primary">{ln.skuName}</span>
                <span className={ln.shortfall ? 'font-semibold text-status-danger' : 'text-secondary'}>
                  {ln.requiredQty} из {ln.availableAfterOrder} шт.
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-muted">
                <span>Завод: {ln.supplierCity}, {ln.leadDays} сут.</span>
                <button type="button" onClick={() => inventoryStore.selectMapNode(ln.supplierId)} className="btn-row text-xs">
                  К заводу
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CentralHubPanel({
  state,
  summary,
  outbound,
  outboundPallets,
  outboundValueKrub
}: {
  state: InventoryDomainState;
  summary: OrderCapacitySummary;
  outbound: OutboundFlowArc[];
  outboundPallets: number;
  outboundValueKrub: number;
}) {
  return (
    <div className="space-y-2.5">
      <div>
        <h2 className="text-base font-semibold text-primary">{CENTRAL_HUB_META.title}</h2>
        <p className="text-xs text-muted tabular-nums">Подольск, {CENTRAL_HUB_META.gateLabel}</p>
      </div>

      <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Приемка от заводов</span>
          <span className={`font-semibold ${summary.overLimitCount === 0 ? 'text-status-success' : 'text-status-danger'}`}>
            {summary.totalPallets.toFixed(1)} / {summary.effectivePalletLimit} палл.
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Тоннаж на рампе</span>
          <span className="font-semibold text-primary">
            {summary.totalWeightKg} / {state.constraints.maxWeightKg} кг
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Отгрузки со склада</span>
          <span className="font-semibold text-primary">
            {outboundPallets.toFixed(1)} палл., {outboundValueKrub.toFixed(0)} тыс. ₽
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-secondary">Очередь ворот отгрузки:</div>
        <div className="space-y-1">
          {outbound.map((out) => (
            <button
              key={out.id}
              type="button"
              onClick={() => inventoryStore.selectMapNode(out.id)}
              className="w-full surface-inset px-2.5 py-2 flex items-center justify-between gap-2 text-left text-xs tabular-nums"
            >
              <span className="font-medium text-primary">{out.city}, {out.dispatchWindowLabel}</span>
              <span className={`${resolveOutboundStatusColor(out.status)} font-semibold`}>{out.pallets.toFixed(1)} п.</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
