import { BACKUP_CHANNELS, SUPPLIER_LIST } from './presets';
import {
  CENTRAL_HUB_META,
  INBOUND_CONTROL_POINTS,
  OUTBOUND_SPECS,
  SUPPLIER_GEO
} from './flowNetworkGeo';
import {
  buildOutboundArcs,
  quadBezier
} from './flowNetworkOutbound';
import {
  computeItemCostKrub,
  computeItemPallets,
  computeItemWeightKg,
  computeOrderSummary,
  isSkuAtStockoutRisk
} from '../store/replenishmentEngine';
import type {
  InventoryDomainState,
  SkuItem,
  SupplierId
} from '../types/domain';
import type { GeoPointMeta } from './flowNetworkGeo';
import type { OutboundFlowArc, OutboundFlowLineItem } from './flowNetworkOutbound';

export { CENTRAL_HUB_META, SUPPLIER_GEO, OUTBOUND_SPECS };
export type { GeoPointMeta, OutboundCustomerSpec } from './flowNetworkGeo';
export type { OutboundFlowArc, OutboundFlowLineItem };

export interface InboundFlowArc {
  id: SupplierId;
  supplierName: string;
  city: string;
  geo: GeoPointMeta;
  items: SkuItem[];
  skuCount: number;
  totalUnits: number;
  pallets: number;
  weightKg: number;
  budgetKrub: number;
  leadDays: number;
  reliabilityPct: number;
  atRisk: boolean;
  riskReason: string;
  arcPath: string;
  midX: number;
  midY: number;
}

function resolveInboundRiskReason(riskySkus: SkuItem[], leadDays: number, assignedCount: number): string {
  if (riskySkus.length > 0) return `Дефицит буфера: ${riskySkus[0].name}`;
  if (leadDays > 12) return `Длинное плечо ${leadDays} сут. по каналу`;
  if (assignedCount === 0) return 'Резервная площадка без активных строк';
  return 'Поставка в графике ворот РЦ';
}

export function computeSupplyNetwork(state: InventoryDomainState): {
  inbound: InboundFlowArc[];
  outbound: OutboundFlowArc[];
  inboundPallets: number;
  outboundPallets: number;
  outboundValueKrub: number;
  readyCustomersCount: number;
  riskCorridorsCount: number;
  otifNetworkPct: number;
} {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const ch = BACKUP_CHANNELS[state.backupChannel];

  const inbound: InboundFlowArc[] = SUPPLIER_LIST.map((sup) => {
    const geo = SUPPLIER_GEO[sup.id];
    const [cx, cy] = INBOUND_CONTROL_POINTS[sup.id];
    const { path, midX, midY } = quadBezier(
      geo.x, geo.y, cx, cy, CENTRAL_HUB_META.x, CENTRAL_HUB_META.y
    );
    const assigned = state.items.filter((it) => it.supplierId === sup.id);
    const totalUnits = assigned.reduce((s, it) => s + it.orderQty, 0);
    const pallets = Number(assigned.reduce((s, it) => s + computeItemPallets(it), 0).toFixed(1));
    const weightKg = assigned.reduce((s, it) => s + computeItemWeightKg(it), 0);
    const budgetKrub = Number(
      assigned.reduce((s, it) => s + computeItemCostKrub(it, state.backupChannel), 0).toFixed(1)
    );
    const leadDays = Math.max(2, sup.leadDays + state.transitDelayDays + ch.leadDeltaDays);
    const riskySkus = assigned.filter((it) =>
      isSkuAtStockoutRisk(it, state.transitDelayDays, state.backupChannel)
    );
    const atRisk = riskySkus.length > 0 || (assigned.length > 0 && leadDays > 12);

    return {
      id: sup.id,
      supplierName: sup.name,
      city: sup.city,
      geo,
      items: assigned,
      skuCount: assigned.length,
      totalUnits,
      pallets,
      weightKg,
      budgetKrub,
      leadDays,
      reliabilityPct: sup.reliabilityPct,
      atRisk,
      riskReason: resolveInboundRiskReason(riskySkus, leadDays, assigned.length),
      arcPath: path,
      midX,
      midY
    };
  });

  const outbound = buildOutboundArcs(state, summary);
  const inboundPallets = Number(inbound.reduce((s, f) => s + f.pallets, 0).toFixed(1));
  const outboundPallets = Number(outbound.reduce((s, f) => s + f.pallets, 0).toFixed(1));
  const outboundValueKrub = Number(outbound.reduce((s, f) => s + f.valueKrub, 0).toFixed(1));
  const readyCustomersCount = outbound.filter((o) => o.status === 'ready').length;
  const riskCorridorsCount =
    inbound.filter((i) => i.atRisk).length + outbound.filter((o) => o.status === 'at_risk').length;
  const otifNetworkPct = Number(
    Math.min(
      99.6,
      Math.max(
        74.0,
        summary.avgReliabilityPct - riskCorridorsCount * 2.4 - (summary.overLimitCount > 0 ? 1.8 : 0)
      )
    ).toFixed(1)
  );

  return {
    inbound,
    outbound,
    inboundPallets,
    outboundPallets,
    outboundValueKrub,
    readyCustomersCount,
    riskCorridorsCount,
    otifNetworkPct
  };
}
