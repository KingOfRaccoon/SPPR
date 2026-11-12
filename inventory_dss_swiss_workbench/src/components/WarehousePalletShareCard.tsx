import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { computeItemPallets, computeItemWeightKg } from '../store/replenishmentEngine';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { InventoryDomainState, OrderCapacitySummary } from '../types/domain';

interface WarehousePalletShareCardProps {
  state: InventoryDomainState;
  summary: OrderCapacitySummary;
  discreteRampSlots: number;
}

export function WarehousePalletShareCard({
  state,
  summary,
  discreteRampSlots
}: WarehousePalletShareCardProps) {
  return (
    <article
      data-card="pallet-share-breakdown"
      className="surface-card p-3.5 h-full flex flex-col justify-between gap-2.5"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-primary">
          Доля паллетомест и массы по строкам
        </h2>
        <span className="text-sm font-semibold text-primary tabular-nums">
          Итого {summary.totalPallets.toFixed(1)} палл., {summary.totalWeightKg} кг
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Позиция и площадка</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Партия</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Масса</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Паллеты</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Доля РЦ</th>
            </tr>
          </thead>
          <tbody>
            {state.items.map((item, idx) => {
              const pallets = computeItemPallets(item);
              const weight = computeItemWeightKg(item);
              const sharePct = Math.round(
                (pallets / Math.max(0.1, summary.effectivePalletLimit)) * 100
              );
              const sup = getSupplier(item.supplierId);
              const isActive = item.id === state.activeSkuId;

              return (
                <tr
                  key={item.id}
                  data-entity-id={item.id}
                  data-selected={isActive ? 'true' : undefined}
                  tabIndex={isActive ? 0 : -1}
                  aria-selected={isActive}
                  style={{ borderBottomWidth: 0 }}
                  onClick={() => inventoryStore.selectSku(item.id)}
                  onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectSku(item.id))}
                  className={`cursor-pointer ${!isActive && idx % 2 === 1 ? 'surface-inset' : ''}`}
                >
                  <td className="text-left">
                    <div className="text-sm font-semibold text-primary">{item.name}</div>
                    <div className="text-xs text-muted">{sup.name}, {item.category}</div>
                  </td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{item.orderQty} шт.</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{weight} кг</td>
                  <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{pallets.toFixed(1)} палл.</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{sharePct}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="surface-inset px-3 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs tabular-nums">
        <span className="text-secondary">Стандарт паллетирования РЦ: EUR 1200×800 мм, до 1,8 м</span>
        <span className="font-semibold text-primary tabular-nums">
          Ворота 1–4, {discreteRampSlots} слот. WMS
        </span>
      </div>

      <div className="surface-inset px-3 py-2.5 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs tabular-nums">
        <div>
          <div className="text-muted">Сухой сектор РЦ</div>
          <div className="font-semibold text-primary">
            {(summary.totalPallets * 0.62).toFixed(1)} палл. стеллажи
          </div>
        </div>
        <div>
          <div className="text-muted">Климат и карантин ОТК</div>
          <div className="font-semibold text-primary">
            {(summary.totalPallets * 0.38).toFixed(1)} палл. контроль
          </div>
        </div>
        <div>
          <div className="text-muted">Буфер маневра рампы</div>
          <div className="font-semibold text-primary">
            {state.constraints.reserveGatePallets} палл. под разгрузку
          </div>
        </div>
      </div>
    </article>
  );
}
