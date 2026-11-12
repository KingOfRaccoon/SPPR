import { SUPPLIER_LIST } from '../data/presets';
import { SHORT_SUPPLIER_NAMES } from '../data/supplierContracts';
import { inventoryStore } from '../store/domainStore';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import { SupplierTruckIcon } from './Icons';
import type { OrderCapacitySummary, SkuItem, SupplierId, SupplierOption } from '../types/domain';

interface SupplierReliabilityChartCardProps {
  activeSku: SkuItem;
  selectedSupplier: SupplierOption;
  selectedSupplierId: SupplierId;
  summary: OrderCapacitySummary;
}

export function SupplierReliabilityChartCard({
  activeSku,
  selectedSupplier,
  selectedSupplierId,
  summary
}: SupplierReliabilityChartCardProps) {
  return (
    <article
      data-card="supplier-reliability-chart"
      className="surface-card p-3.5 h-full flex flex-col justify-between gap-2.5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 min-w-0">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-primary">
            Сравнение поставщиков по цене и срокам
          </h1>
          <p className="text-sm text-secondary tabular-nums">
            Позиция: {activeSku.name}, партия {activeSku.orderQty} шт.
          </p>
        </div>
        <span className="text-sm font-semibold text-secondary tabular-nums">
          Пул: {summary.avgReliabilityPct.toFixed(1)}%, срок {summary.avgLeadDays.toFixed(1)} сут.
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-1.5">
          <SupplierTruckIcon size={15} className="text-accent-primary" />
          <h2 className="text-sm font-semibold text-primary">
            Индекс надежности и плечо отгрузки
          </h2>
        </div>
        <span data-chart-context="true" className="text-sm text-secondary tabular-nums">
          {selectedSupplier.name}: {selectedSupplier.reliabilityPct.toFixed(1)}%, {selectedSupplier.leadDays} сут.
        </span>
      </div>

      <div className="surface-inset p-2.5">
        <svg
          data-chart="true"
          width="620"
          height="164"
          viewBox="0 0 620 164"
          style={{ width: '100%', height: 'auto', maxHeight: '172px' }}
          role="img"
          aria-label="График индекса надежности поставщиков"
          className="w-full block"
        >
          <line x1="54" y1="22" x2="596" y2="22" stroke="var(--border-subtle)" strokeWidth="1" />
          <line x1="54" y1="76" x2="596" y2="76" stroke="var(--border-subtle)" strokeWidth="1" />
          <line x1="54" y1="130" x2="596" y2="130" stroke="var(--border-subtle)" strokeWidth="1" />
          <text x="6" y="26" fontSize="11" fontFamily="var(--font-sans)" fill="var(--text-muted)">100%</text>
          <text x="6" y="80" fontSize="11" fontFamily="var(--font-sans)" fill="var(--text-muted)">92%</text>
          <text x="6" y="134" fontSize="11" fontFamily="var(--font-sans)" fill="var(--text-muted)">84%</text>

          {SUPPLIER_LIST.map((sup, idx) => {
            const cx = 132 + idx * 134;
            const barWidth = 52;
            const clamped = Math.max(84, Math.min(100, sup.reliabilityPct));
            const barHeight = Math.round(((clamped - 84) / 16) * 98) + 10;
            const barTop = 130 - barHeight;
            const isSelected = sup.id === selectedSupplierId;

            return (
              <g
                key={sup.id}
                data-chart-node={sup.id}
                data-canvas-node={sup.id}
                onClick={() => inventoryStore.selectChartSupplier(sup.id)}
                className="cursor-pointer"
              >
                <rect
                  x={cx - barWidth / 2}
                  y={barTop}
                  width={barWidth}
                  height={barHeight}
                  rx="2"
                  fill={isSelected ? 'var(--accent-primary)' : 'var(--border-strong)'}
                  fillOpacity={isSelected ? '0.94' : '0.62'}
                />
                <text
                  x={cx}
                  y={barTop - 6}
                  textAnchor="middle"
                  fontSize="11"
                  fontFamily="var(--font-sans)"
                  fontWeight="600"
                  fill="var(--text-primary)"
                >
                  {sup.reliabilityPct.toFixed(1)}%
                </text>
                <text
                  x={cx}
                  y="151"
                  textAnchor="middle"
                  fontSize="11"
                  fontFamily="var(--font-sans)"
                  fontWeight={isSelected ? '600' : '400'}
                  fill="var(--text-secondary)"
                >
                  {SHORT_SUPPLIER_NAMES[sup.id] || sup.name}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="seg-group flex-wrap" role="group" aria-label="Площадки поставщиков">
        {SUPPLIER_LIST.map((sup) => (
          <button
            key={sup.id}
            type="button"
            aria-pressed={sup.id === selectedSupplierId}
            onClick={() => inventoryStore.selectSupplier(sup.id)}
            className="seg-btn tabular-nums"
          >
            {sup.name}, {sup.leadDays}д
          </button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr>
              <th scope="col" className="text-left">Поставщик</th>
              <th scope="col" className="text-left">Город</th>
              <th scope="col" className="text-right tabular-nums">Срок</th>
              <th scope="col" className="text-right tabular-nums">Мин. партия</th>
              <th scope="col" className="text-right tabular-nums">Индекс цены</th>
            </tr>
          </thead>
          <tbody>
            {SUPPLIER_LIST.map((sup, idx) => {
              const isSelected = sup.id === selectedSupplierId;
              return (
                <tr
                  key={sup.id}
                  data-selected={isSelected ? 'true' : undefined}
                  tabIndex={0}
                  aria-current={isSelected ? 'true' : undefined}
                  style={{ borderBottomWidth: 0 }}
                  onClick={() => inventoryStore.selectSupplier(sup.id)}
                  onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectSupplier(sup.id))}
                  className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
                >
                  <td className="text-left font-semibold text-primary text-sm">{sup.name}</td>
                  <td className="text-left text-secondary text-sm">{sup.city}</td>
                  <td className="text-right text-sm tabular-nums whitespace-nowrap">{sup.leadDays} сут.</td>
                  <td className="text-right text-sm tabular-nums whitespace-nowrap">{sup.minBatchQty} шт.</td>
                  <td className="text-right text-sm font-medium text-primary tabular-nums whitespace-nowrap">
                    ×{sup.priceFactor.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}
