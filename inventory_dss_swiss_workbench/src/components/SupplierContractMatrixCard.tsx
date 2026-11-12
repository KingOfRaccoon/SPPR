import { SUPPLIER_LIST } from '../data/presets';
import { SUPPLIER_CONTRACT_TERMS } from '../data/supplierContracts';
import { inventoryStore } from '../store/domainStore';
import { computeItemCostKrub } from '../store/replenishmentEngine';
import { handleSelectableKeyDown } from '../utils/a11yDialog';
import type { BackupChannelMode, SkuItem, SupplierId } from '../types/domain';

interface SupplierContractMatrixCardProps {
  items: SkuItem[];
  backupChannel: BackupChannelMode;
  selectedSupplierId: SupplierId;
  selectedSupplierName: string;
}

export function SupplierContractMatrixCard({
  items,
  backupChannel,
  selectedSupplierId,
  selectedSupplierName
}: SupplierContractMatrixCardProps) {
  return (
    <article data-card="supplier-contract-matrix" className="surface-card p-3.5 space-y-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-primary">
            Сравнительная матрица условий поставки и отсрочки
          </h2>
          <p className="text-xs text-muted">
            Договорные квоты MOQ, отсрочка оплаты и распределение волны
          </p>
        </div>
        <span className="text-xs text-secondary tabular-nums">
          Активный контрагент: {selectedSupplierName}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="ledger-table tabular-nums">
          <thead>
            <tr className="surface-inset">
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Площадка</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-left">Базис поставки и упаковка</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Отсрочка</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Кратность MOQ</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Штраф SLA</th>
              <th scope="col" style={{ borderBottomWidth: 0 }} className="text-right tabular-nums">Сумма в волне</th>
            </tr>
          </thead>
          <tbody>
            {SUPPLIER_LIST.map((sup, idx) => {
              const terms = SUPPLIER_CONTRACT_TERMS[sup.id];
              const isSelected = sup.id === selectedSupplierId;
              const assignedSum = items
                .filter((it) => it.supplierId === sup.id)
                .reduce((acc, it) => acc + computeItemCostKrub(it, backupChannel), 0);

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
                  <td className="text-left text-sm font-semibold text-primary">
                    {sup.name}, {sup.city}
                  </td>
                  <td className="text-left text-sm text-secondary">{terms.incoterms}</td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">
                    {terms.deferralDays} сут.
                  </td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">
                    {terms.moqStepQty} шт.
                  </td>
                  <td className="text-right text-sm text-secondary whitespace-nowrap tabular-nums">
                    {terms.slaPenaltyPct} / дн.
                  </td>
                  <td className="text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums">
                    {assignedSum.toFixed(1)} тыс. ₽
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
