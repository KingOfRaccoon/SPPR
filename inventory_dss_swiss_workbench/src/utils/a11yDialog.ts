import { useEffect, useRef } from 'react';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]';

export function useDialogFocusTrap(open: boolean) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const prevRenderOpenRef = useRef(false);
  const prevOpenEffectRef = useRef(false);

  // Capture trigger before React commits modal autoFocus into the DOM
  if (open && !prevRenderOpenRef.current && typeof document !== 'undefined') {
    const ae = document.activeElement as HTMLElement | null;
    if (ae && ae !== document.body && !ae.closest('[role="dialog"]')) {
      triggerRef.current = ae;
    }
  }
  prevRenderOpenRef.current = open;

  useEffect(() => {
    if (!open) {
      if (prevOpenEffectRef.current) {
        const prev = triggerRef.current;
        triggerRef.current = null;
        if (prev && document.contains(prev) && !document.querySelector('[role="dialog"]')) {
          prev.focus();
        }
      }
      prevOpenEffectRef.current = false;
      return;
    }

    prevOpenEffectRef.current = true;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const root =
        dialogRef.current || (document.querySelector('[role="dialog"]') as HTMLElement | null);
      if (!root) return;
      const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0
      );
      if (items.length === 0) return;

      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey) {
        if (!active || !root.contains(active) || active === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (!active || !root.contains(active) || active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [open]);

  return dialogRef;
}

export function handleSelectableKeyDown(
  e: {
    key: string;
    target: EventTarget | null;
    currentTarget: EventTarget | null;
    preventDefault: () => void;
  },
  onSelect: () => void
) {
  if (e.target !== e.currentTarget) return;
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onSelect();
  }
}
