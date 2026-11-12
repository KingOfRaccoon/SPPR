import type { OutboundFlowArc } from '../data/flowNetwork';
import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { computeEffectiveLeadDays, computeItemPallets } from '../store/replenishmentEngine';
import type { InventoryDomainState, SkuItem } from '../types/domain';

function renderPegStatusText(shortfall: boolean, late: boolean, leadDays: number): string {
  if (shortfall) return 'Дефицит шт.';
  if (late) return `Приход Д+${leadDays}`;
  return 'Обеспечено';
}

export function SkuPeggingPanel({
  state,
  activeSku,
  outbound
}: {
  state: InventoryDomainState;
  activeSku: SkuItem;
  outbound: OutboundFlowArc[];
}) {
  const activeSup = getSupplier(activeSku.supplierId);
  const skuLeadDays = computeEffectiveLeadDays(
    activeSku,
    state.transitDelayDays,
    state.backupChannel
  );
  const availableAfterOrder = activeSku.currentStock + activeSku.orderQty;
  const peggedCustomerArcs = outbound
    .map((out) => ({ out, line: out.lines.find((ln) => ln.skuId === activeSku.id) }))
    .filter((entry): entry is { out: OutboundFlowArc; line: OutboundFlowArc['lines'][number] } =>
      Boolean(entry.line)
    );
  const totalPeggedDemand = peggedCustomerArcs.reduce(
    (acc, entry) => acc + entry.line.requiredQty,
    0
  );

  return (
    <div className="space-y-2.5" data-sku-pegging-panel="true">
      <div>
        <h2 className="text-base font-semibold text-primary">{activeSku.name}</h2>
        <p className="text-xs text-muted tabular-nums">
          Завод: {activeSup.name} ({activeSup.city}), приход Д+{skuLeadDays}
        </p>
      </div>

      <div className="surface-inset p-2.5 space-y-1.5 text-sm tabular-nums">
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Полка + приход в РЦ</span>
          <span className="font-semibold text-primary">
            {activeSku.currentStock} + {activeSku.orderQty} = {availableAfterOrder} шт.
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Спрос заказов клиентов</span>
          <span
            className={`font-semibold ${
              availableAfterOrder < totalPeggedDemand ? 'text-status-danger' : 'text-status-success'
            }`}
          >
            {totalPeggedDemand} шт. ({peggedCustomerArcs.length} напр.)
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-secondary">Объем плеча от завода</span>
          <span className="font-semibold text-primary">
            {computeItemPallets(activeSku).toFixed(1)} палл., плечо {skuLeadDays} сут.
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-secondary">Связанные клиентские отгрузки:</div>
        {peggedCustomerArcs.length === 0 ? (
          <div className="surface-inset p-2 text-xs text-muted">
            Позиция формирует внутренний резерв центрального РЦ Подольск.
          </div>
        ) : (
          <div className="space-y-1">
            {peggedCustomerArcs.map(({ out, line }) => {
              const late = skuLeadDays > out.dispatchWindowDays;
              const blocked = late || line.shortfall;
              return (
                <button
                  key={`peg-${out.id}`}
                  type="button"
                  onClick={() => inventoryStore.selectMapNode(out.id)}
                  className="w-full surface-inset px-2.5 py-2 flex items-center justify-between gap-2 text-left text-xs tabular-nums"
                >
                  <span className="font-medium text-primary">
                    {out.city}, окно {out.dispatchWindowLabel}: {line.requiredQty} шт.
                  </span>
                  <span className={blocked ? 'font-semibold text-status-danger' : 'font-semibold text-status-success'}>
                    {renderPegStatusText(line.shortfall, late, skuLeadDays)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
