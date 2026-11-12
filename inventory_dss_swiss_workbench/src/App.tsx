import React, { useCallback, useEffect, useState } from 'react';
import { SCREEN_DEFINITIONS } from './data/presets';
import { inventoryStore, useInventoryStore } from './store/domainStore';
import { computeOrderSummary } from './store/replenishmentEngine';
import { useGlobalWorkbenchShortcuts } from './hooks/useGlobalWorkbenchShortcuts';
import {
  AddSkuModal,
  CmdKPalette,
  LiveUndoToast,
  StateFallbackView
} from './components/ShellModals';
import { WhatIfSandboxModal } from './components/WhatIfSandboxModal';
import {
  CsvExportIcon,
  LedgerGridIcon,
  RouteMapIcon,
  SearchCmdIcon,
  ShieldClockIcon,
  SupplierTruckIcon,
  WarehouseBoxIcon
} from './components/Icons';
import { ScreenReplenishmentNotebook } from './screens/ScreenReplenishmentNotebook';
import { ScreenSupplyMap } from './screens/ScreenSupplyMap';
import { ScreenWarehouseLimits } from './screens/ScreenWarehouseLimits';
import { ScreenSupplierChoice } from './screens/ScreenSupplierChoice';
import { ScreenDeliveryBuffer } from './screens/ScreenDeliveryBuffer';
import { ScreenOrderExport } from './screens/ScreenOrderExport';
import type { ScreenId, ViewState } from './types/domain';

declare global {
  interface Window {
    __PIPELINE_SET_VIEW_STATE__?: (nextState: ViewState) => void;
  }
}

function renderNavIcon(screenId: ScreenId) {
  switch (screenId) {
    case 'screen-replenishment-notebook':
      return <LedgerGridIcon size={14} />;
    case 'screen-supply-map':
      return <RouteMapIcon size={14} />;
    case 'screen-warehouse-limits':
      return <WarehouseBoxIcon size={14} />;
    case 'screen-supplier-choice':
      return <SupplierTruckIcon size={14} />;
    case 'screen-delivery-buffer':
      return <ShieldClockIcon size={14} />;
    case 'screen-order-export':
      return <CsvExportIcon size={14} />;
  }
}

export default function App() {
  const state = useInventoryStore();
  const [viewState, setViewState] = useState<ViewState>('Ideal');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [whatIfOpen, setWhatIfOpen] = useState(false);

  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const palletsOk = summary.totalPallets <= summary.effectivePalletLimit + 0.05;
  const budgetOk = summary.totalBudgetKrub <= state.constraints.maxBudgetKrub + 0.05;

  useEffect(() => {
    const activeScr = SCREEN_DEFINITIONS.find((s) => s.id === state.activeScreenId);
    if (activeScr) {
      document.title = `${activeScr.label}: Запас-Навигатор`;
    }
  }, [state.activeScreenId]);

  useEffect(() => {
    window.__PIPELINE_SET_VIEW_STATE__ = (next: ViewState) => {
      if (next === 'Ideal' || next === 'Empty' || next === 'Loading' || next === 'Error') {
        setViewState(next);
      }
    };
    return () => {
      delete window.__PIPELINE_SET_VIEW_STATE__;
    };
  }, []);

  const handleToggleCmdk = useCallback(() => setCmdkOpen((prev) => !prev), []);
  const handleToggleWhatIf = useCallback(() => setWhatIfOpen((prev) => !prev), []);
  const handleCloseAllModals = useCallback(() => {
    setCmdkOpen(false);
    setAddModalOpen(false);
    setWhatIfOpen(false);
  }, []);

  useGlobalWorkbenchShortcuts({
    onToggleCmdk: handleToggleCmdk,
    onToggleWhatIf: handleToggleWhatIf,
    onCloseAllModals: handleCloseAllModals,
    onSetViewState: setViewState
  });

  return (
    <div
      data-active-entity={state.activeSkuId}
      className="min-h-screen bg-canvas text-primary font-sans app-shell-rail"
    >
      <a href="#main-content" className="skip-link">
        Перейти к рабочей области
      </a>
      <header data-ui="topbar" className="app-rail-header">
        <div className="flex items-center gap-2 min-w-0 shrink-0">
          <LedgerGridIcon size={16} className="text-accent-primary shrink-0" />
          <span className="text-sm font-semibold tracking-tight text-primary whitespace-nowrap">
            Запас-Навигатор
          </span>
          <span data-breadcrumb="true" className="sr-only">
            Запас-Навигатор / Снабжение
          </span>
        </div>

        <button
          type="button"
          data-ui="btn-ghost"
          onClick={() => setCmdkOpen(true)}
          aria-label="Быстрый поиск команд и разделов"
          className="btn-ghost radius-control shrink-0"
        >
          <SearchCmdIcon size={14} />
          <kbd className="text-xs text-muted tabular-nums">⌘K</kbd>
        </button>
      </header>

      <nav
        data-ui="screen-nav"
        data-nav-count={SCREEN_DEFINITIONS.length}
        aria-label="Разделы рабочей тетради закупок"
        className="app-screen-nav app-rail-nav"
      >
        {SCREEN_DEFINITIONS.map((scr) => {
          const isActive = state.activeScreenId === scr.id;
          return (
            <button
              key={scr.id}
              type="button"
              data-ui="nav-tab"
              data-screen-trigger={scr.id}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => {
                setViewState('Ideal');
                inventoryStore.setScreen(scr.id);
              }}
              className="app-nav-tab"
            >
              {renderNavIcon(scr.id)}
              <span className="hidden lg:inline">{scr.label}</span>
              <span className="lg:hidden">{scr.shortLabel}</span>
            </button>
          );
        })}

        <div className="app-rail-telemetry text-xs tabular-nums">
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted">Ворота РЦ</span>
            <span className="font-semibold text-primary">Смена А · 1–4</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted">Паллеты</span>
            <span
              className={
                palletsOk ? 'font-semibold text-status-success' : 'font-semibold text-status-danger'
              }
            >
              {summary.totalPallets.toFixed(1)}/{summary.effectivePalletLimit} палл.
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted">Бюджет</span>
            <span
              className={budgetOk ? 'font-semibold text-primary' : 'font-semibold text-status-danger'}
            >
              {Math.round(summary.totalBudgetKrub)}/{state.constraints.maxBudgetKrub} тыс. ₽
            </span>
          </div>
          <button
            type="button"
            data-ui="btn-secondary"
            data-open-whatif="true"
            onClick={() => setWhatIfOpen(true)}
            aria-label="Открыть симулятор What-If сценариев"
            className="btn-secondary w-full radius-control justify-between"
          >
            <span>What-If</span>
            <kbd className="text-xs text-muted tabular-nums">Alt+S</kbd>
          </button>
        </div>
      </nav>

      <main id="main-content" tabIndex={-1} className="app-main-shell app-rail-main">
        {viewState !== 'Ideal' ? (
          <StateFallbackView
            state={state}
            summary={summary}
            viewState={viewState}
            onRecoverToIdeal={() => setViewState('Ideal')}
          />
        ) : (
          <>
            {state.activeScreenId === 'screen-replenishment-notebook' && (
              <ScreenReplenishmentNotebook
                state={state}
                onOpenAddModal={() => setAddModalOpen(true)}
              />
            )}
            {state.activeScreenId === 'screen-supply-map' && <ScreenSupplyMap state={state} />}
            {state.activeScreenId === 'screen-warehouse-limits' && (
              <ScreenWarehouseLimits state={state} />
            )}
            {state.activeScreenId === 'screen-supplier-choice' && (
              <ScreenSupplierChoice state={state} />
            )}
            {state.activeScreenId === 'screen-delivery-buffer' && (
              <ScreenDeliveryBuffer state={state} />
            )}
            {state.activeScreenId === 'screen-order-export' && <ScreenOrderExport state={state} />}
          </>
        )}
      </main>

      <AddSkuModal open={addModalOpen} onClose={() => setAddModalOpen(false)} />
      <CmdKPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        onOpenCreate={() => setAddModalOpen(true)}
        onOpenWhatIf={() => {
          setCmdkOpen(false);
          setWhatIfOpen(true);
        }}
      />
      <LiveUndoToast message={state.toastMessage} canUndo={Boolean(state.toastCanUndo)} />
      <WhatIfSandboxModal open={whatIfOpen} onClose={() => setWhatIfOpen(false)} state={state} />
    </div>
  );
}
