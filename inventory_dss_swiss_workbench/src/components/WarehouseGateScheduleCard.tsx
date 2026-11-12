import { useState } from 'react';
import { inventoryStore } from '../store/domainStore';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { OrderCapacitySummary, SkuItem } from '../types/domain';

type ShiftFilter = 'all' | 'A' | 'B';

interface WarehouseGateScheduleCardProps {
  items: SkuItem[];
  activeSkuId: string;
  summary: OrderCapacitySummary;
}

function buildShiftWindows(items: SkuItem[], summary: OrderCapacitySummary) {
  return [
    {
      id: 'gate-a1',
      shift: 'A' as const,
      gateLabel: 'Смена А, ворота №1',
      cargoNote: 'Приоритетная автоматика, БалтКомплект',
      timeSlot: '08:00–11:30',
      pallets: Number((summary.totalPallets * 0.28).toFixed(1)),
      weightKg: Math.round(summary.totalWeightKg * 0.27),
      gateCap: Math.round(summary.effectivePalletLimit * 0.3),
      skuId: items[0]?.id || 'sku-power-ctrl'
    },
    {
      id: 'gate-a2',
      shift: 'A' as const,
      gateLabel: 'Смена А, ворота №2',
      cargoNote: 'Силовая коммутация, УралПривод',
      timeSlot: '11:30–15:00',
      pallets: Number((summary.totalPallets * 0.34).toFixed(1)),
      weightKg: Math.round(summary.totalWeightKg * 0.35),
      gateCap: Math.round(summary.effectivePalletLimit * 0.34),
      skuId: items[2]?.id || items[0]?.id || 'sku-terminal-blk'
    },
    {
      id: 'gate-b3',
      shift: 'B' as const,
      gateLabel: 'Смена Б, ворота №3',
      cargoNote: 'Датчики и реле защиты, СеверСнаб',
      timeSlot: '15:30–19:00',
      pallets: Number((summary.totalPallets * 0.2).toFixed(1)),
      weightKg: Math.round(summary.totalWeightKg * 0.19),
      gateCap: Math.round(summary.effectivePalletLimit * 0.22),
      skuId: items[1]?.id || items[0]?.id || 'sku-pressure-sens'
    },
    {
      id: 'gate-b4',
      shift: 'B' as const,
      gateLabel: 'Смена Б, ворота №4',
      cargoNote: 'Кабельный монтаж и карантин, ВолгаПрибор',
      timeSlot: '19:00–22:00',
      pallets: Number((summary.totalPallets * 0.18).toFixed(1)),
      weightKg: Math.round(summary.totalWeightKg * 0.19),
      gateCap: Math.max(6, Math.round(summary.effectivePalletLimit * 0.2)),
      skuId: items[4]?.id || items[0]?.id || 'sku-cable-gland'
    }
  ];
}

export function WarehouseGateScheduleCard({
  items,
  activeSkuId,
  summary
}: WarehouseGateScheduleCardProps) {
  const [shiftFilter, setShiftFilter] = useState<ShiftFilter>('all');
  const shiftWindows = buildShiftWindows(items, summary);
  const visibleShiftRows =
    shiftFilter === 'all' ? shiftWindows : shiftWindows.filter((row) => row.shift === shiftFilter);
  const hasSelectedInShift = visibleShiftRows.some((s) => s.skuId === activeSkuId);

  return (
    <article data-card="dock-gate-shift-schedule" className="surface-card p-3.5 space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
        <div>
          <h2 className="text-sm font-semibold text-primary">
            Расписание окон разгрузки ворот РЦ по сменам (Смена А / Б)
          </h2>
          <p className="text-xs text-muted">
            Распределение паллет и тоннажа текущей волны по слотам рампы
          </p>
        </div>

        <div className="seg-group" role="group" aria-label="Фильтр смен разгрузки">
          {(
            [
              { id: 'all', label: 'Все смены' },
              { id: 'A', label: 'Смена А' },
              { id: 'B', label: 'Смена Б' }
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              aria-pressed={shiftFilter === tab.id}
              onClick={() => setShiftFilter(tab.id)}
              className="seg-btn"
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Смена и ворота</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Назначение потока</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Окно приемки</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Паллеты</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Тоннаж</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Квота ворот</th>
            </tr>
          </thead>
          <tbody>
            {visibleShiftRows.map((slot, idx) => {
              const isSelected = slot.skuId === activeSkuId;
              const overSlot = slot.pallets > slot.gateCap + 0.2;
              return (
                <tr
                  key={slot.id}
                  data-selected={isSelected ? 'true' : undefined}
                  tabIndex={isSelected || (!hasSelectedInShift && idx === 0) ? 0 : -1}
                  aria-selected={isSelected}
                  style={{ borderBottomWidth: 0 }}
                  onClick={() => inventoryStore.selectSku(slot.skuId)}
                  onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectSku(slot.skuId))}
                  className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
                >
                  <td className="text-left text-sm font-semibold text-primary whitespace-nowrap">{slot.gateLabel}</td>
                  <td className="text-left text-sm text-secondary">{slot.cargoNote}</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{slot.timeSlot}</td>
                  <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{slot.pallets.toFixed(1)} палл.</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{slot.weightKg} кг</td>
                  <td className={`text-right text-sm font-semibold whitespace-nowrap tabular-nums ${overSlot ? 'text-status-warning' : 'text-status-success'}`}>
                    до {slot.gateCap} палл.
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
