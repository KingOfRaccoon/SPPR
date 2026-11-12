import React, { useRef, useState } from 'react';
import { SUPPLIER_LIST } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import {
  computeOrderSummary,
  computeWaveFinancialSummary
} from '../store/replenishmentEngine';
import { WarehouseBoxIcon } from '../components/Icons';
import { WarehouseGateScheduleCard } from '../components/WarehouseGateScheduleCard';
import { WarehousePalletShareCard } from '../components/WarehousePalletShareCard';
import type { InventoryDomainState, SkuPriority, SupplierId } from '../types/domain';

interface ScreenWarehouseLimitsProps {
  state: InventoryDomainState;
}

const PALLET_CEILINGS = [34, 46, 56] as const;

export function ScreenWarehouseLimits({ state }: ScreenWarehouseLimitsProps) {
  const [draftName, setDraftName] = useState('');
  const [formError, setFormError] = useState('');
  const [draftQtyStr, setDraftQtyStr] = useState('40');
  const [draftSupplier, setDraftSupplier] = useState<SupplierId>('balt-komplekt');
  const [draftPriority, setDraftPriority] = useState<SkuPriority>('standard');
  const inputRef = useRef<HTMLInputElement | null>(null);

  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const freeReserve = Number((summary.effectivePalletLimit - summary.totalPallets).toFixed(1));
  const waveFin = computeWaveFinancialSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );

  const handleComposeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = draftName.trim();
    if (!clean) {
      setFormError('Укажите наименование узла или расходника');
      inputRef.current?.focus();
      return;
    }
    setFormError('');
    const parsedQty = Number(String(draftQtyStr).replace(',', '.'));
    inventoryStore.addCustomSku({
      name: clean,
      category: 'Складской заказ',
      orderQty: Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty : 40,
      supplierId: draftSupplier,
      priority: draftPriority
    });
    setDraftName('');
  };

  return (
    <section
      data-screen-view="screen-warehouse-limits"
      data-shell="warehouse-capacity-composer"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5"
    >
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch">
        <div className="xl:col-span-6 flex flex-col justify-between gap-2 min-w-0">
          <article data-card="warehouse-ceiling-controls" className="surface-card p-2.5 space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2 min-w-0">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-primary">
                  Ограничения паллетомест, массы и бюджета
                </h1>
                <p className="text-sm text-secondary tabular-nums">
                  Доступно {summary.effectivePalletLimit} паллетомест, рампа {state.constraints.maxWeightKg} кг
                </p>
              </div>
              <span className={`text-sm font-semibold tabular-nums ${freeReserve >= 0 ? 'text-status-success' : 'text-status-danger'}`}>
                Остаток: {freeReserve.toFixed(1)} палл.
              </span>
            </div>

            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5">
                <WarehouseBoxIcon size={15} className="text-accent-primary" />
                <h2 className="text-sm font-semibold text-primary">
                  Нормативы зоны приемки и потолок бюджета
                </h2>
              </div>

              <div className="seg-group" role="group" aria-label="Потолок паллетомест">
                {PALLET_CEILINGS.map((cap) => (
                  <button
                    key={cap}
                    type="button"
                    aria-pressed={state.constraints.maxPallets === cap}
                    onClick={() => inventoryStore.updateConstraints({ maxPallets: cap })}
                    className="seg-btn tabular-nums"
                  >
                    {cap} палл.
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div className="flex flex-col justify-end gap-1 min-w-0">
                <label htmlFor="limit-weight-select" className="block text-xs font-medium text-secondary">
                  Предельная масса на рампу
                </label>
                <select
                  id="limit-weight-select"
                  value={state.constraints.maxWeightKg}
                  onChange={(e) => inventoryStore.updateConstraints({ maxWeightKg: Number(e.target.value) })}
                  className="w-full field-compact tabular-nums"
                >
                  <option value={9600}>9 600 кг, малая</option>
                  <option value={11800}>11 800 кг, штатная</option>
                  <option value={12400}>12 400 кг, 2 бригады</option>
                  <option value={14500}>14 500 кг, расшир.</option>
                </select>
              </div>

              <div className="flex flex-col justify-end gap-1 min-w-0">
                <label htmlFor="limit-budget-select" className="block text-xs font-medium text-secondary">
                  Потолок бюджета волны
                </label>
                <select
                  id="limit-budget-select"
                  value={state.constraints.maxBudgetKrub}
                  onChange={(e) => inventoryStore.updateConstraints({ maxBudgetKrub: Number(e.target.value) })}
                  className="w-full field-compact tabular-nums"
                >
                  <option value={3150}>3 150 тыс. ₽, строгий</option>
                  <option value={3650}>3 650 тыс. ₽, базовый</option>
                  <option value={3900}>3 900 тыс. ₽, резерв</option>
                  <option value={4400}>4 400 тыс. ₽, пиковый</option>
                </select>
              </div>
            </div>

            <button
              type="button"
              data-primary-action="true"
              onClick={() => inventoryStore.applyWarehouseLimitsAndBalance()}
              className="btn-primary w-full radius-control"
            >
              Применить габаритные лимиты
            </button>
          </article>

          <article data-card="custom-sku-composer" className="surface-card p-2.5 space-y-1.5">
            <h2 className="text-sm font-semibold text-primary">
              Быстрое включение нестандартной позиции в ведомость
            </h2>
            <form noValidate onSubmit={handleComposeSubmit} className="space-y-2">
              <div className="space-y-1">
                <label htmlFor="composer-sku-name" className="block text-xs font-medium text-secondary">
                  Наименование узла или расходника
                </label>
                <input
                  ref={inputRef}
                  id="composer-sku-name"
                  type="text"
                  value={draftName}
                  aria-invalid={formError ? 'true' : undefined}
                  aria-describedby={formError ? 'inv-s2-form-err' : undefined}
                  onChange={(e) => {
                    setDraftName(e.target.value);
                    if (formError) setFormError('');
                  }}
                  placeholder="Добавить коммерческую заявку: Автомат защиты 16А"
                  className="w-full field-compact"
                />
                {formError ? (
                  <p id="inv-s2-form-err" role="alert" className="text-xs text-status-danger mt-0.5">
                    {formError}
                  </p>
                ) : null}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <div className="flex flex-col justify-end gap-1 min-w-0">
                  <label htmlFor="composer-sup-select" className="block text-xs font-medium text-secondary">
                    Площадка
                  </label>
                  <select
                    id="composer-sup-select"
                    value={draftSupplier}
                    onChange={(e) => setDraftSupplier(e.target.value as SupplierId)}
                    className="w-full field-compact"
                  >
                    {SUPPLIER_LIST.map((sup) => (
                      <option key={sup.id} value={sup.id}>{sup.name}</option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col justify-end gap-1 min-w-0">
                  <label htmlFor="composer-prio-select" className="block text-xs font-medium text-secondary">
                    Приоритет
                  </label>
                  <select
                    id="composer-prio-select"
                    value={draftPriority}
                    onChange={(e) => setDraftPriority(e.target.value as SkuPriority)}
                    className="w-full field-compact"
                  >
                    <option value="critical">Критичный</option>
                    <option value="standard">Стандартный</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 items-end">
                <div className="flex flex-col justify-end gap-1 min-w-0">
                  <label htmlFor="composer-qty-input" className="block text-xs font-medium text-secondary">
                    Партия, шт.
                  </label>
                  <input
                    id="composer-qty-input"
                    type="number"
                    min="1"
                    max="5000"
                    step="1"
                    value={draftQtyStr}
                    onChange={(e) => setDraftQtyStr(e.target.value)}
                    className="w-full field-compact tabular-nums"
                  />
                </div>

                <div className="flex flex-col justify-end min-w-0">
                  <button type="submit" className="btn-secondary w-full radius-control">
                    Добавить строку
                  </button>
                </div>
              </div>
            </form>
          </article>
        </div>

        <div className="xl:col-span-6 min-w-0">
          <WarehousePalletShareCard
            state={state}
            summary={summary}
            discreteRampSlots={waveFin.discreteRampSlots}
          />
        </div>
      </div>

      <WarehouseGateScheduleCard
        items={state.items}
        activeSkuId={state.activeSkuId}
        summary={summary}
      />
    </section>
  );
}
