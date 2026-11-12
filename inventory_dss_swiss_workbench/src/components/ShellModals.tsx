import { useEffect } from 'react';
import { inventoryStore } from '../store/domainStore';
import { UndoIcon } from './Icons';

export { AddSkuModal } from './AddSkuModal';
export { CmdKPalette } from './CmdKPalette';
export { StateFallbackView } from './StateFallbackView';

export function LiveUndoToast({ message, canUndo = false }: { message: string | null; canUndo?: boolean }) {
  const hasUndo = Boolean(canUndo && inventoryStore.canUndo());
  useEffect(() => {
    if (!message) return;
    const duration = hasUndo ? 8000 : 5000;
    const timer = window.setTimeout(() => {
      inventoryStore.dismissToast();
    }, duration);
    return () => window.clearTimeout(timer);
  }, [message, hasUndo]);

  return (
    <div role="status" aria-live="polite" className="fixed bottom-16 md:bottom-4 right-3 z-40">
      {message && (
        <div
          data-ui="surface"
          data-toast-status="true"
          style={{ maxWidth: 'min(520px, calc(100vw - 24px))' }}
          className="surface-card px-3 py-2 flex flex-wrap items-center justify-between gap-2"
        >
          <span className="text-sm font-medium text-primary">{message}</span>
          <div className="inline-flex items-center gap-1.5 shrink-0">
            {hasUndo && (
              <button
                type="button"
                data-ui="btn-secondary"
                data-toast-undo="true"
                onClick={() => inventoryStore.undo()}
                className="btn-secondary radius-control"
              >
                <UndoIcon size={13} />
                <span>Отменить</span>
              </button>
            )}
            <button
              type="button"
              data-ui="btn-ghost"
              data-toast-dismiss="true"
              aria-label="Закрыть уведомление"
              onClick={() => inventoryStore.dismissToast()}
              className="btn-ghost radius-control text-muted"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
