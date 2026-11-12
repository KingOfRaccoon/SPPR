import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeCostOfInaction,
  computeDaysOfCover,
  computeItemCostKrub,
  computeItemPallets,
  formatShortBalanceReason,
  isSkuAtStockoutRisk
} from '../store/replenishmentEngine';
import { InlineOrderQtyInput } from './InlineOrderQtyInput';
import type { BalanceLineDiff, BackupChannelMode, SkuItem, TransitDelayDays } from '../types/domain';

function resolveCoverPillClass(atRisk: boolean, status: 'deficit' | 'healthy' | 'overstock'): string {
  if (atRisk) return 'bg-status-danger';
  if (status === 'overstock') return 'surface-inset text-secondary';
  return 'bg-status-success';
}

export interface RowKeyEvent {
  key: string;
  target: EventTarget | null;
  currentTarget: EventTarget | null;
  preventDefault: () => void;
}

interface ReplenishmentLedgerRowProps {
  item: SkuItem;
  idx: number;
  isSelected: boolean;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  appliedDiff?: BalanceLineDiff;
  onRowKeyDown: (e: RowKeyEvent, itemId: string) => void;
}

export function ReplenishmentLedgerRow({
  item,
  idx,
  isSelected,
  transitDelayDays,
  backupChannel,
  appliedDiff,
  onRowKeyDown
}: ReplenishmentLedgerRowProps) {
  const atRisk = isSkuAtStockoutRisk(item, transitDelayDays, backupChannel);
  const cover = computeDaysOfCover(item, transitDelayDays, backupChannel);
  const pallets = computeItemPallets(item);
  const lineCost = computeItemCostKrub(item, backupChannel);
  const sup = getSupplier(item.supplierId);
  const nonMultiple = item.orderQty % sup.minBatchQty !== 0;
  const coi = computeCostOfInaction(item, transitDelayDays, backupChannel);

  return (
    <tr
      data-entity-id={item.id}
      data-canvas-node={item.id}
      data-selected={isSelected ? 'true' : undefined}
      tabIndex={isSelected ? 0 : -1}
      aria-selected={isSelected}
      style={{ borderBottomWidth: 0 }}
      onClick={() => inventoryStore.selectSku(item.id)}
      onKeyDown={(e) => onRowKeyDown(e, item.id)}
      className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
    >
      <td className="text-left">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-semibold text-primary">{item.name}</span>
          {item.manualOverride && (
            <span data-manual-override={item.id} className="px-1.5 py-0.5 radius-control text-xs font-medium bg-status-warning">
              ручн.
            </span>
          )}
          {coi.riskKrub > 0 && (
            <span data-sku-inaction-risk={item.id} className="px-1.5 py-0.5 radius-control text-xs font-medium bg-status-danger tabular-nums">
              Риск {Math.round(coi.riskKrub)}к
            </span>
          )}
        </div>
        {appliedDiff ? (
          <div data-row-diff={item.id} className="text-xs font-medium text-accent-primary tabular-nums">
            Было {appliedDiff.beforeQty} → {appliedDiff.afterQty} шт., {formatShortBalanceReason(appliedDiff.reason)}
          </div>
        ) : (
          <div className="text-xs text-muted tabular-nums">
            {sup.name}, полка {cover.runoutDays}д{nonMultiple ? `, шаг ${sup.minBatchQty}` : ''}
          </div>
        )}
      </td>
      <td className="whitespace-nowrap text-right text-sm tabular-nums">
        <span data-cover-pill={item.id} className={`px-2 py-0.5 radius-control text-sm font-semibold ${resolveCoverPillClass(atRisk, cover.status)}`}>
          {cover.totalCoverDays.toFixed(1)} сут.
        </span>
      </td>
      <td data-numeric="true" className="whitespace-nowrap text-right text-sm font-semibold text-primary tabular-nums">
        <InlineOrderQtyInput item={item} step={sup.minBatchQty} />
      </td>
      <td className="whitespace-nowrap text-right text-sm text-secondary tabular-nums">{pallets.toFixed(1)} п.</td>
      <td className="whitespace-nowrap text-right text-sm font-medium text-primary tabular-nums">{lineCost.toFixed(1)} тыс.</td>
      <td className="whitespace-nowrap text-right tabular-nums">
        <div className="inline-flex items-center justify-end gap-1">
          <button
            type="button"
            data-inline-control={`dec-${item.id}`}
            aria-label={`-10: уменьшить партию ${item.name}`}
            onClick={(e) => { e.stopPropagation(); inventoryStore.adjustOrderQty(item.id, -10); }}
            className="btn-row tabular-nums"
          >
            -10
          </button>
          <button
            type="button"
            data-inline-control={`inc-${item.id}`}
            aria-label={`+10: увеличить партию ${item.name}`}
            onClick={(e) => { e.stopPropagation(); inventoryStore.adjustOrderQty(item.id, 10); }}
            className="btn-row tabular-nums"
          >
            +10
          </button>
          <button
            type="button"
            data-inline-control={`buf-${item.id}`}
            aria-label={`${item.safetyDays}д: страховой запас ${item.name}`}
            onClick={(e) => { e.stopPropagation(); inventoryStore.cycleSafetyDays(item.id); }}
            className="btn-row tabular-nums"
          >
            {item.safetyDays}д
          </button>
        </div>
      </td>
    </tr>
  );
}
