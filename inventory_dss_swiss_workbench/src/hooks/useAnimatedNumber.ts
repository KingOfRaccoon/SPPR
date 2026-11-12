import { useEffect, useRef, useState } from 'react';

function shouldSkipAnimation(): boolean {
  if (typeof window === 'undefined') return true;
  if (typeof navigator !== 'undefined' && navigator.webdriver) return true;
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return true;
  return false;
}

export function useAnimatedNumber(target: number, durationMs = 160): number {
  const [displayValue, setDisplayValue] = useState<number>(target);
  const currentRef = useRef<number>(target);

  useEffect(() => {
    if (shouldSkipAnimation() || durationMs <= 0) {
      currentRef.current = target;
      setDisplayValue(target);
      return;
    }

    const startValue = currentRef.current;
    const delta = target - startValue;
    if (Math.abs(delta) < 0.001) {
      currentRef.current = target;
      setDisplayValue(target);
      return;
    }

    let rafId = 0;
    const startTime = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(1, Math.max(0, elapsed / durationMs));
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = startValue + delta * eased;
      currentRef.current = next;
      setDisplayValue(next);

      if (progress < 1) {
        rafId = window.requestAnimationFrame(tick);
      } else {
        currentRef.current = target;
        setDisplayValue(target);
      }
    };

    rafId = window.requestAnimationFrame(tick);
    return () => {
      if (rafId) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [target, durationMs]);

  if (shouldSkipAnimation()) {
    return target;
  }

  return displayValue;
}
