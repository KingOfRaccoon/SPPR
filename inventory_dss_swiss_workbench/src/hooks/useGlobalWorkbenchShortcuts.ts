import { useEffect } from 'react';
import { SCREEN_DEFINITIONS } from '../data/presets';
import { inventoryStore } from '../store/domainStore';
import type { ViewState } from '../types/domain';

interface ShortcutHandlers {
  onToggleCmdk: () => void;
  onToggleWhatIf: () => void;
  onCloseAllModals: () => void;
  onSetViewState: (state: ViewState) => void;
}

export function useGlobalWorkbenchShortcuts({
  onToggleCmdk,
  onToggleWhatIf,
  onCloseAllModals,
  onSetViewState
}: ShortcutHandlers): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isEditableField = Boolean(
        target &&
          (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' ||
            target.isContentEditable)
      );

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onToggleCmdk();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        if (isEditableField) return;
        e.preventDefault();
        inventoryStore.undo();
        return;
      }
      if (e.altKey && !e.metaKey && !e.ctrlKey && !isEditableField) {
        if (e.code === 'KeyS' || e.key.toLowerCase() === 's') {
          e.preventDefault();
          onToggleWhatIf();
          return;
        }
        if (e.code === 'KeyB' || e.key.toLowerCase() === 'b') {
          e.preventDefault();
          inventoryStore.balanceOrder();
          return;
        }
        const codeDigit = e.code?.startsWith('Digit') ? Number(e.code.slice(5)) - 1 : -1;
        const digitIdx = codeDigit >= 0 ? codeDigit : Number(e.key) - 1;
        if (digitIdx >= 0 && digitIdx < SCREEN_DEFINITIONS.length) {
          e.preventDefault();
          onSetViewState('Ideal');
          inventoryStore.setScreen(SCREEN_DEFINITIONS[digitIdx].id);
          return;
        }
      }
      if (e.key === 'Escape') {
        onCloseAllModals();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onToggleCmdk, onToggleWhatIf, onCloseAllModals, onSetViewState]);
}
