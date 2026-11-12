import React, { useEffect, useState } from 'react';
import { inventoryStore } from '../store/domainStore';
import type { SkuItem } from '../types/domain';

interface InlineOrderInputProps {
  item: SkuItem;
  step: number;
}

export function InlineOrderQtyInput({ item, step }: InlineOrderInputProps) {
  const [draft, setDraft] = useState<string>(String(item.orderQty));

  useEffect(() => {
    setDraft(String(item.orderQty));
  }, [item.orderQty]);

  const commit = () => {
    const parsed = Number(draft.replace(',', '.').trim());
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDraft(String(item.orderQty));
      return;
    }
    const clamped = Math.max(10, Math.min(990, Math.round(parsed)));
    setDraft(String(clamped));
    if (clamped !== item.orderQty) {
      inventoryStore.setOrderQty(item.id, clamped);
    }
  };

  return (
    <input
      type="number"
      min={10}
      max={990}
      step={step}
      value={draft}
      data-inline-qty-input={item.id}
      aria-label={`Партия дозаказа ${item.name}, штук`}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={() => inventoryStore.selectSku(item.id)}
      onBlur={commit}
      onClick={(e) => {
        inventoryStore.selectSku(item.id);
        e.stopPropagation();
      }}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === 'Enter') {
          e.preventDefault();
          commit();
          (e.currentTarget as HTMLInputElement).blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setDraft(String(item.orderQty));
          (e.currentTarget as HTMLInputElement).blur();
        }
      }}
      className="field-compact text-right font-semibold tabular-nums"
      style={{ width: '68px', height: '26px', padding: '0 6px' }}
    />
  );
}
