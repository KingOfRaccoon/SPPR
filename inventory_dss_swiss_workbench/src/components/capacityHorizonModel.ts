import {
  computeEffectiveLeadDays,
  computeOrderSummary
} from '../store/replenishmentEngine';
import type { InventoryDomainState, OrderCapacitySummary } from '../types/domain';

export const HORIZON_DAYS = [1, 4, 7, 10, 14] as const;

export interface HorizonPoint {
  day: number;
  dayLabel: string;
  cx: number;
  totalPallets: number;
  dryPallets: number;
  coldPallets: number;
  quarantinePallets: number;
  freeGateReserve: number;
  dockLoadPct: number;
  linkedSkuId: string;
}

export interface CapacityGauge {
  id: string;
  label: string;
  valueText: string;
  ratio: number;
  over: boolean;
}

export function resolvePointBarColor(isSelected: boolean, overGate: boolean): string {
  if (isSelected) return 'var(--accent-primary)';
  if (overGate) return 'var(--status-danger-fg)';
  return 'var(--border-strong)';
}

export function buildHorizonPoints(
  state: InventoryDomainState,
  summary: OrderCapacitySummary
): HorizonPoint[] {
  return HORIZON_DAYS.map((day, idx) => {
    let dryRaw = 0;
    let coldRaw = 0;
    let quarantineRaw = 0;
    let inboundArrivingPallets = 0;

    for (const item of state.items) {
      const lead = computeEffectiveLeadDays(item, state.transitDelayDays, state.backupChannel);
      const shelfUnits = Math.max(0, item.currentStock - item.dailyDemand * (day - 1) * 0.62);
      const orderLanded =
        day >= lead ? item.orderQty : item.orderQty * Math.min(0.86, day / Math.max(2, lead + 1));
      const postArrivalDrain = day > lead ? item.dailyDemand * (day - lead) * 0.52 : 0;
      const units = Math.max(6, shelfUnits + orderLanded - postArrivalDrain);
      const itemPallets = units / Math.max(1, item.unitsPerPallet);

      const isArrivalWindow = Math.abs(day - lead) <= 2;
      if (isArrivalWindow) {
        inboundArrivingPallets += (item.orderQty / Math.max(1, item.unitsPerPallet)) * 0.45;
      }

      const qShare = isArrivalWindow ? 0.18 : 0.09;
      quarantineRaw += itemPallets * qShare;
      if (item.category === 'Измерения' || item.category === 'Автоматика') {
        coldRaw += itemPallets * (1 - qShare) * 0.72;
        dryRaw += itemPallets * (1 - qShare) * 0.28;
      } else {
        dryRaw += itemPallets * (1 - qShare) * 0.88;
        coldRaw += itemPallets * (1 - qShare) * 0.12;
      }
    }

    const rawSum = Math.max(1, dryRaw + coldRaw + quarantineRaw);
    const waveAnchor = day === 4 || day === 7 ? Math.max(rawSum, summary.totalPallets) : rawSum;
    const scale = waveAnchor / rawSum;

    const dryPallets = Number((dryRaw * scale).toFixed(1));
    const coldPallets = Number((coldRaw * scale).toFixed(1));
    const quarantinePallets = Number(Math.max(0.8, quarantineRaw * scale).toFixed(1));
    const totalPallets = Number((dryPallets + coldPallets + quarantinePallets).toFixed(1));
    const freeGateReserve = Number(
      Math.max(0, state.constraints.maxPallets - totalPallets).toFixed(1)
    );
    const dockLoadPct = Math.min(
      116,
      Math.max(
        42,
        Math.round(
          (totalPallets / Math.max(1, summary.effectivePalletLimit)) * 82 +
            inboundArrivingPallets * 1.4
        )
      )
    );
    const linkedItem = state.items[idx % Math.max(1, state.items.length)];

    return {
      day,
      dayLabel: `Д+${day}`,
      cx: 98 + idx * 112,
      totalPallets,
      dryPallets,
      coldPallets,
      quarantinePallets,
      freeGateReserve,
      dockLoadPct,
      linkedSkuId: linkedItem ? linkedItem.id : 'sku-power-ctrl'
    };
  });
}

export function buildCapacityGauges(
  state: InventoryDomainState,
  summary: OrderCapacitySummary
): CapacityGauge[] {
  return [
    {
      id: 'g-pallet',
      label: 'Паллеты приемки',
      valueText: `${summary.totalPallets.toFixed(1)} / ${summary.effectivePalletLimit}`,
      ratio: summary.totalPallets / Math.max(1, summary.effectivePalletLimit),
      over: summary.totalPallets > summary.effectivePalletLimit + 0.05
    },
    {
      id: 'g-weight',
      label: 'Тоннаж рампы',
      valueText: `${(summary.totalWeightKg / 1000).toFixed(1)} / ${(state.constraints.maxWeightKg / 1000).toFixed(1)} т`,
      ratio: summary.totalWeightKg / Math.max(1, state.constraints.maxWeightKg),
      over: summary.totalWeightKg > state.constraints.maxWeightKg
    },
    {
      id: 'g-budget',
      label: 'Бюджет волны',
      valueText: `${Math.round(summary.totalBudgetKrub)} / ${state.constraints.maxBudgetKrub} тыс.`,
      ratio: summary.totalBudgetKrub / Math.max(1, state.constraints.maxBudgetKrub),
      over: summary.totalBudgetKrub > state.constraints.maxBudgetKrub + 0.05
    }
  ];
}

export function computeActiveSkuTelemetry(state: InventoryDomainState) {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const activeSku = state.items.find((i) => i.id === state.activeSkuId) || state.items[0];
  const activeLead = activeSku
    ? computeEffectiveLeadDays(activeSku, state.transitDelayDays, state.backupChannel)
    : 6;
  const activeCoverDays = activeSku
    ? Number(((activeSku.currentStock + activeSku.orderQty) / Math.max(1, activeSku.dailyDemand)).toFixed(1))
    : 0;
  return { summary, activeSku, activeLead, activeCoverDays };
}
