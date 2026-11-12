import React, { useEffect, useRef, useState } from 'react';
import { SCENARIO_PRESETS, SCREEN_DEFINITIONS } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import { useDialogFocusTrap } from '../utils/a11yDialog';
import { SearchCmdIcon } from './Icons';

interface CmdKPaletteProps {
  open: boolean;
  onClose: () => void;
  onOpenCreate: () => void;
  onOpenWhatIf: () => void;
}

export function CmdKPalette({ open, onClose, onOpenCreate, onOpenWhatIf }: CmdKPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useDialogFocusTrap(open);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      searchInputRef.current?.focus();
    }
  }, [open]);

  if (!open) return null;

  const q = query.trim().toLowerCase();
  const actions = [
    {
      id: 'cmd-balance',
      label: 'Сбалансировать заказ по складу',
      hint: 'Уложить паллеты',
      run: () => inventoryStore.balanceOrder()
    },
    {
      id: 'cmd-reconcile-map',
      label: 'Выровнять потоки сети на карте поставок',
      hint: 'Вход и отгрузки',
      run: () => {
        inventoryStore.setScreen('screen-supply-map');
        inventoryStore.reconcileNetworkFlows();
      }
    },
    {
      id: 'cmd-create',
      label: 'Добавить позицию в закупочную ведомость',
      hint: 'Новая строка',
      run: () => onOpenCreate()
    },
    {
      id: 'cmd-whatif',
      label: 'What-If симулятор сценариев (Alt+S)',
      hint: 'Alt+S',
      run: () => onOpenWhatIf()
    },
    ...SCENARIO_PRESETS.map((p) => ({
      id: `cmd-${p.id}`,
      label: `Сценарий: ${p.label}`,
      hint: `${p.constraints.maxPallets} палл.`,
      run: () => inventoryStore.loadPreset(p.id)
    })),
    ...SCREEN_DEFINITIONS.map((s) => ({
      id: `cmd-nav-${s.id}`,
      label: `Раздел: ${s.label}`,
      hint: s.shortcut,
      run: () => inventoryStore.setScreen(s.id)
    }))
  ].filter((item) => !q || item.label.toLowerCase().includes(q));

  const safeIdx = actions.length > 0 ? Math.min(selectedIndex, actions.length - 1) : 0;

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (actions.length > 0) setSelectedIndex((prev) => (prev + 1) % actions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (actions.length > 0) setSelectedIndex((prev) => (prev - 1 + actions.length) % actions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const target = actions[safeIdx];
      if (target) {
        target.run();
        onClose();
      }
    }
  };

  return (
    <div
      ref={dialogRef}
      data-cmdk-palette="true"
      role="dialog"
      aria-modal="true"
      aria-label="Быстрые команды Запас-Навигатор"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-start justify-center pt-14 p-4 bg-canvas/80"
    >
      <div data-ui="surface" className="surface-card p-3 w-full max-w-lg space-y-2">
        <div className="flex items-center gap-2">
          <SearchCmdIcon size={15} className="text-muted" />
          <input
            ref={searchInputRef}
            data-cmdk-input="true"
            id="cmdk-search-input"
            type="search"
            role="combobox"
            aria-expanded="true"
            aria-controls="cmdk-listbox"
            aria-activedescendant={actions.length > 0 ? `cmdk-opt-${actions[safeIdx]?.id}` : undefined}
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
            aria-label="Поиск команды или раздела"
            placeholder="Сценарий, раздел или команда..."
            className="flex-1 field-compact"
          />
          <button type="button" data-ui="btn-ghost" onClick={onClose} className="btn-ghost radius-control">
            <kbd className="text-xs text-muted tabular-nums">Esc</kbd>
          </button>
        </div>
        <div id="cmdk-listbox" role="listbox" aria-label="Доступные команды" className="max-h-64 overflow-y-auto space-y-0.5">
          {actions.length === 0 ? (
            <div className="px-2.5 py-3 text-sm text-muted">
              Команды по запросу не найдены, нажмите Esc для закрытия
            </div>
          ) : (
            actions.map((act, idx) => {
              const isSelected = idx === safeIdx;
              return (
                <button
                  key={act.id}
                  id={`cmdk-opt-${act.id}`}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  onClick={() => {
                    act.run();
                    onClose();
                  }}
                  className={`btn-ghost w-full justify-between radius-control px-2.5 h-8 text-left ${
                    isSelected ? 'surface-inset text-primary' : ''
                  }`}
                >
                  <span className="text-sm font-medium text-primary">{act.label}</span>
                  <kbd className="text-xs text-muted tabular-nums shrink-0">{act.hint}</kbd>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
