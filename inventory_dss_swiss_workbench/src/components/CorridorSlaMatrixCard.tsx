import { SUPPLIER_LIST } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { BackupChannelMode, SkuItem, SupplierId, TransitDelayDays } from '../types/domain';

const CORRIDOR_META: Record<
  SupplierId,
  { corridorName: string; hubRoute: string; slaTargetPct: number; normBufferDays: number }
> = {
  'balt-komplekt': { corridorName: 'Северо-Западный коридор', hubRoute: 'СПб Шушары – ворота РЦ', slaTargetPct: 98.0, normBufferDays: 6 },
  'ural-privod': { corridorName: 'Уральский магистральный ход', hubRoute: 'Екатеринбург – сортировка РЦ', slaTargetPct: 94.5, normBufferDays: 8 },
  'volga-pribor': { corridorName: 'Волжское направление', hubRoute: 'Казань – транзитный терминал', slaTargetPct: 91.0, normBufferDays: 10 },
  'sever-snab': { corridorName: 'Северный экспресс-канал', hubRoute: 'Ярославль – прямая рампа РЦ', slaTargetPct: 98.5, normBufferDays: 6 }
};

interface CorridorSlaMatrixCardProps {
  items: SkuItem[];
  activeSkuId: string;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  channelLabel: string;
  channelLeadDeltaDays: number;
  channelCostSurchargePct: number;
}

export function CorridorSlaMatrixCard({
  items,
  activeSkuId,
  transitDelayDays,
  backupChannel,
  channelLabel,
  channelLeadDeltaDays,
  channelCostSurchargePct
}: CorridorSlaMatrixCardProps) {
  return (
    <article data-card="corridor-sla-matrix" className="surface-card p-3.5 space-y-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-primary">
            Матрица соблюдения SLA коридоров и страховых буферов по направлениям
          </h2>
          <p className="text-xs text-muted">
            Соблюдение коридоров по каналу «{channelLabel}»
          </p>
        </div>
        <span className="text-xs text-secondary tabular-nums">
          Надбавка логистики: +{channelCostSurchargePct}%
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Направление и площадка</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Маршрутный узел</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Норма SLA</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Плечо факт</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Норматив буфера</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Индекс OTIF</th>
            </tr>
          </thead>
          <tbody>
            {SUPPLIER_LIST.map((sup, idx) => {
              const meta = CORRIDOR_META[sup.id];
              const effectiveCorridorDays = Math.max(2, sup.leadDays + transitDelayDays + channelLeadDeltaDays);
              const linkedSku = items.find((it) => it.supplierId === sup.id) || items[0];
              const isSelected = Boolean(linkedSku && linkedSku.id === activeSkuId);
              const effectiveOtif = Number(
                Math.max(82, sup.reliabilityPct - transitDelayDays * 0.6 + (backupChannel === 'direct_rail' ? 0 : 1.8)).toFixed(1)
              );

              return (
                <tr
                  key={sup.id}
                  data-selected={isSelected ? 'true' : undefined}
                  tabIndex={0}
                  aria-current={isSelected ? 'true' : undefined}
                  style={{ borderBottomWidth: 0 }}
                  onClick={() => { if (linkedSku) inventoryStore.selectSku(linkedSku.id); }}
                  onKeyDown={(e) => handleSelectableKeyDown(e, () => { if (linkedSku) inventoryStore.selectSku(linkedSku.id); })}
                  className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
                >
                  <td className="text-left text-sm font-semibold text-primary">
                    {meta.corridorName}, {sup.name}
                  </td>
                  <td className="text-left text-sm text-secondary">{meta.hubRoute}</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{sup.leadDays} сут.</td>
                  <td className={`text-right text-sm font-semibold whitespace-nowrap tabular-nums ${effectiveCorridorDays > sup.leadDays + 2 ? 'text-status-warning' : 'text-primary'}`}>
                    {effectiveCorridorDays} сут.
                  </td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{meta.normBufferDays} сут.</td>
                  <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{effectiveOtif.toFixed(1)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}
