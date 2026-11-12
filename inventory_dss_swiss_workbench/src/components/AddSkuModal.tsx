import React, { useEffect, useRef, useState } from 'react';
import { SUPPLIER_LIST } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { useDialogFocusTrap } from '../utils/a11yDialog';
import type { SkuPriority, SupplierId } from '../types/domain';

interface AddSkuModalProps {
  open: boolean;
  onClose: () => void;
}

export function AddSkuModal({ open, onClose }: AddSkuModalProps) {
  const [name, setName] = useState('');
  const [titleError, setTitleError] = useState('');
  const [category, setCategory] = useState('Автоматика');
  const [qtyStr, setQtyStr] = useState('40');
  const [costStr, setCostStr] = useState('6.8');
  const [bufferStr, setBufferStr] = useState('8');
  const [supplierId, setSupplierId] = useState<SupplierId>('balt-komplekt');
  const [priority, setPriority] = useState<SkuPriority>('critical');
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useDialogFocusTrap(open);

  useEffect(() => {
    setTitleError('');
    if (open) {
      titleInputRef.current?.focus();
    }
  }, [open]);

  if (!open) return null;

  const handleClose = () => {
    setTitleError('');
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = name.trim();
    if (!clean) {
      setTitleError('Укажите наименование номенклатуры');
      titleInputRef.current?.focus();
      return;
    }
    const parsedQty = Number(String(qtyStr).replace(',', '.'));
    const parsedCost = Number(String(costStr).replace(',', '.'));
    const parsedBuf = Number(String(bufferStr).replace(',', '.'));

    inventoryStore.addCustomSku({
      name: clean,
      category,
      orderQty: Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty : 40,
      unitCostKrub: Number.isFinite(parsedCost) && parsedCost > 0 ? parsedCost : 6.8,
      safetyDays: Number.isFinite(parsedBuf) && parsedBuf > 0 ? parsedBuf : 8,
      supplierId,
      priority
    });
    setName('');
    handleClose();
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Добавить позицию в закупочную ведомость"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-canvas/80"
    >
      <div data-ui="surface" className="surface-card p-4 w-full max-w-md space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-primary">Новая позиция к заказу</h2>
          <button
            type="button"
            data-ui="btn-ghost"
            onClick={handleClose}
            aria-label="Закрыть окно добавления позиции"
            className="btn-ghost radius-control"
          >
            Закрыть
          </button>
        </div>

        <form noValidate data-mutation-form="true" onSubmit={handleSubmit} className="space-y-2.5">
          <div className="space-y-1">
            <label htmlFor="sku-name-input" className="block text-xs font-medium text-secondary">
              Наименование комплектующих
            </label>
            <input
              ref={titleInputRef}
              id="sku-name-input"
              type="text"
              autoFocus
              value={name}
              aria-invalid={titleError ? 'true' : undefined}
              aria-describedby={titleError ? 'inv-modal-title-err' : undefined}
              onChange={(e) => {
                setName(e.target.value);
                if (titleError) setTitleError('');
              }}
              placeholder="Например: Модули плавного пуска конвейера"
              className="w-full field-compact"
            />
            {titleError ? (
              <p id="inv-modal-title-err" role="alert" className="text-xs text-status-danger mt-0.5">
                {titleError}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
            <div className="sm:col-span-7 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-category-select" className="block text-xs font-medium text-secondary">
                Товарная группа
              </label>
              <select
                id="sku-category-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full field-compact"
              >
                <option value="Автоматика">Автоматика</option>
                <option value="Измерения">Измерения</option>
                <option value="Коммутация">Коммутация</option>
                <option value="Монтаж">Монтаж</option>
              </select>
            </div>

            <div className="sm:col-span-5 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-qty-input" className="block text-xs font-medium text-secondary">
                Партия, шт.
              </label>
              <input
                id="sku-qty-input"
                type="number"
                min="1"
                max="5000"
                step="1"
                required
                value={qtyStr}
                onChange={(e) => setQtyStr(e.target.value)}
                className="w-full field-compact tabular-nums"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
            <div className="sm:col-span-7 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-supplier-select" className="block text-xs font-medium text-secondary">
                Поставщик
              </label>
              <select
                id="sku-supplier-select"
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value as SupplierId)}
                className="w-full field-compact"
              >
                {SUPPLIER_LIST.map((sup) => (
                  <option key={sup.id} value={sup.id}>
                    {sup.name}, {sup.leadDays}д
                  </option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-5 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-cost-input" className="block text-xs font-medium text-secondary">
                Цена, тыс. ₽
              </label>
              <input
                id="sku-cost-input"
                type="number"
                min="0.1"
                max="2500"
                step="0.01"
                required
                value={costStr}
                onChange={(e) => setCostStr(e.target.value)}
                className="w-full field-compact tabular-nums"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
            <div className="sm:col-span-7 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-priority-select" className="block text-xs font-medium text-secondary">
                Приоритет защиты
              </label>
              <select
                id="sku-priority-select"
                value={priority}
                onChange={(e) => setPriority(e.target.value as SkuPriority)}
                className="w-full field-compact"
              >
                <option value="critical">Критичный</option>
                <option value="standard">Стандартный</option>
              </select>
            </div>

            <div className="sm:col-span-5 flex flex-col justify-end gap-1 min-w-0">
              <label htmlFor="sku-buffer-input" className="block text-xs font-medium text-secondary">
                Буфер, сут.
              </label>
              <input
                id="sku-buffer-input"
                type="number"
                min="4"
                max="24"
                step="1"
                required
                value={bufferStr}
                onChange={(e) => setBufferStr(e.target.value)}
                className="w-full field-compact tabular-nums"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
            <button type="button" data-ui="btn-ghost" onClick={handleClose} className="btn-ghost radius-control">
              Отмена
            </button>
            <button type="submit" data-ui="btn-primary" data-form-submit="true" className="btn-primary radius-control">
              Включить в заказ
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
