import { getSupplier } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeEffectiveLeadDays,
  computeItemCostKrub,
  computeItemPallets,
  computeItemWeightKg
} from '../store/replenishmentEngine';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { BackupChannelMode, SkuItem, TransitDelayDays } from '../types/domain';

interface ErpDispatchLedgerCardProps {
  items: SkuItem[];
  activeSkuId: string;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  avgReliabilityPct: number;
}

export function ErpDispatchLedgerCard({
  items,
  activeSkuId,
  transitDelayDays,
  backupChannel,
  avgReliabilityPct
}: ErpDispatchLedgerCardProps) {
  return (
    <article data-card="erp-dispatch-ledger" className="surface-card p-3.5 space-y-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-primary">
            Ведомость строк заказа к передаче в контур ERP и приемки РЦ
          </h2>
          <p className="text-sm text-secondary">
            Контрольный реестр партий, паллетомест и сумм перед отправкой
          </p>
        </div>
        <span className="text-sm font-medium text-secondary tabular-nums">
          Надежность пула: {avgReliabilityPct.toFixed(1)}%
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Номенклатура заказа</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Поставщик</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Партия</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Паллеты</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Масса</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Срок</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Сумма</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => {
              const sup = getSupplier(item.supplierId);
              const pallets = computeItemPallets(item);
              const weight = computeItemWeightKg(item);
              const cost = computeItemCostKrub(item, backupChannel);
              const lead = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
              const isSelected = item.id === activeSkuId;

              return (
                <tr
                  key={item.id}
                  data-entity-id={item.id}
                  data-selected={isSelected ? 'true' : undefined}
                  tabIndex={0}
                  aria-current={isSelected ? 'true' : undefined}
                  style={{ borderBottomWidth: 0 }}
                  onClick={() => inventoryStore.selectSku(item.id)}
                  onKeyDown={(e) => handleSelectableKeyDown(e, () => inventoryStore.selectSku(item.id))}
                  className={`cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}`}
                >
                  <td className="text-left text-sm font-semibold text-primary">{item.name}</td>
                  <td className="text-left text-sm text-secondary whitespace-nowrap">{sup.name}</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{item.orderQty} шт.</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{pallets.toFixed(1)} палл.</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{weight} кг</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">{lead} сут.</td>
                  <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">{cost.toFixed(1)} тыс. ₽</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}
