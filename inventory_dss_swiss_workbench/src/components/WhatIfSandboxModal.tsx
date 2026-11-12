import React, { useEffect, useState } from 'react';
import { inventoryStore } from '../store/domainStore';
import { computeWhatIfComparison } from '../store/replenishmentEngine';
import { useDialogFocusTrap } from '../utils/a11yDialog';
import type { BackupChannelMode, InventoryDomainState, TransitDelayDays } from '../types/domain';

interface WhatIfSandboxModalProps {
  open: boolean;
  onClose: () => void;
  state: InventoryDomainState;
}

const DELAY_OPTIONS: Array<{ days: TransitDelayDays; label: string }> = [
  { days: 0, label: '0 сут.' },
  { days: 4, label: '+4 сут.' },
  { days: 9, label: '+9 сут.' }
];

const CHANNEL_OPTIONS: Array<{ id: BackupChannelMode; label: string }> = [
  { id: 'direct_rail', label: 'Ж/д' },
  { id: 'regional_hub', label: 'Хаб' },
  { id: 'express_auto', label: 'Авто' }
];

const PALLET_OPTIONS = [36, 42, 48];

export function WhatIfSandboxModal({ open, onClose, state }: WhatIfSandboxModalProps) {
  const defaultStressDelay: TransitDelayDays = state.transitDelayDays === 9 ? 4 : 9;
  const [stressDelay, setStressDelay] = useState<TransitDelayDays>(defaultStressDelay);
  const [stressChannel, setStressChannel] = useState<BackupChannelMode>('regional_hub');
  const [stressMaxPallets, setStressMaxPallets] = useState<number>(42);
  const dialogRef = useDialogFocusTrap(open);

  useEffect(() => {
    if (open) {
      setStressDelay(state.transitDelayDays === 9 ? 4 : 9);
    }
  }, [open, state.transitDelayDays]);

  if (!open) return null;

  const { baseline, stress, verdict } = computeWhatIfComparison(
    state,
    stressDelay,
    stressChannel,
    stressMaxPallets
  );
  const palletDelta = stress.totalPallets - baseline.totalPallets;

  const handleApply = () => {
    inventoryStore.setTransitScenario(stressDelay, stressChannel);
    inventoryStore.updateConstraints({ maxPallets: stressMaxPallets });
    inventoryStore.balanceOrder();
    onClose();
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="whatif-modal-title"
      data-whatif-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-start justify-center pt-10 p-3 bg-canvas/80"
    >
      <div data-ui="surface" className="surface-card p-4 w-full max-w-2xl space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 id="whatif-modal-title" className="text-sm font-semibold text-primary">
            What-If симулятор сценариев
          </h2>
          <button type="button" onClick={onClose} className="btn-ghost radius-control" aria-label="Закрыть симулятор">
            <kbd className="text-xs text-muted tabular-nums">Esc</kbd>
          </button>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <div className="seg-group" role="group" aria-label="Задержка плеча">
            {DELAY_OPTIONS.map((opt) => (
              <button
                key={opt.days}
                type="button"
                aria-pressed={stressDelay === opt.days}
                onClick={() => setStressDelay(opt.days)}
                className="seg-btn tabular-nums"
              >
                {opt.label}
              </button>
            ))}
          </div>
          <div className="seg-group" role="group" aria-label="Логистический канал">
            {CHANNEL_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                aria-pressed={stressChannel === opt.id}
                onClick={() => setStressChannel(opt.id)}
                className="seg-btn"
              >
                {opt.label}
              </button>
            ))}
          </div>
          <div className="seg-group" role="group" aria-label="Потолок паллет РЦ">
            {PALLET_OPTIONS.map((cap) => (
              <button
                key={cap}
                type="button"
                aria-pressed={stressMaxPallets === cap}
                onClick={() => setStressMaxPallets(cap)}
                className="seg-btn tabular-nums"
              >
                {cap} п.
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 tabular-nums">
          <div className="surface-inset p-3 space-y-1.5 text-sm">
            <div className="text-xs font-semibold text-secondary">Текущая волна (база)</div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Паллеты</span>
              <span className="font-semibold text-primary whitespace-nowrap">
                {baseline.totalPallets.toFixed(1)}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Бюджет</span>
              <span className="font-semibold text-primary whitespace-nowrap">
                {baseline.totalBudgetKrub.toFixed(1)} тыс. ₽
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Дефицит SKU</span>
              <span className="font-semibold text-primary whitespace-nowrap">
                {baseline.stockoutRiskCount}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Цена бездействия</span>
              <span
                className={`font-semibold whitespace-nowrap ${
                  baseline.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'
                }`}
              >
                {Math.round(baseline.totalCostOfInactionKrub)} тыс. ₽
              </span>
            </div>
          </div>

          <div className="surface-inset p-3 space-y-1.5 text-sm">
            <div className="text-xs font-semibold text-secondary">Стресс-сценарий (баланс)</div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Паллеты</span>
              <span className="font-semibold text-primary whitespace-nowrap">
                {stress.totalPallets.toFixed(1)}{' '}
                <span className="text-xs text-muted">
                  ({palletDelta >= 0 ? '+' : ''}
                  {palletDelta.toFixed(1)})
                </span>
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Бюджет</span>
              <span className="font-semibold text-primary whitespace-nowrap">
                {stress.totalBudgetKrub.toFixed(1)} тыс. ₽
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Дефицит SKU</span>
              <span
                className={`font-semibold whitespace-nowrap ${
                  stress.stockoutRiskCount > 0 ? 'text-status-danger' : 'text-status-success'
                }`}
              >
                {stress.stockoutRiskCount}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-secondary">Цена бездействия</span>
              <span
                className={`font-semibold whitespace-nowrap ${
                  stress.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'
                }`}
              >
                {Math.round(stress.totalCostOfInactionKrub)} тыс. ₽
              </span>
            </div>
          </div>
        </div>

        <div className="surface-inset px-3 py-2 text-xs text-secondary">{verdict}</div>

        <div className="flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost radius-control">
            Отмена
          </button>
          <button
            type="button"
            data-apply-whatif="true"
            onClick={handleApply}
            className="btn-primary radius-control"
          >
            Применить сценарий к волне
          </button>
        </div>
      </div>
    </div>
  );
}
