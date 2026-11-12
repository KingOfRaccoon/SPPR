import { getSupplier } from './presets';
import {
  CENTRAL_HUB_META,
  OUTBOUND_CONTROL_POINTS,
  OUTBOUND_SPECS
} from './flowNetworkGeo';
import {
  computeEffectiveLeadDays,
  isSkuAtStockoutRisk
} from '../store/replenishmentEngine';
import type {
  InventoryDomainState,
  OrderCapacitySummary,
  OutboundDestinationId,
  SkuItem,
  SupplierId
} from '../types/domain';
import type { GeoPointMeta } from './flowNetworkGeo';

export interface OutboundFlowLineItem {
  skuId: string;
  skuName: string;
  supplierId: SupplierId;
  supplierCity: string;
  requiredQty: number;
  availableAfterOrder: number;
  leadDays: number;
  shortfall: boolean;
}

export interface OutboundFlowArc {
  id: OutboundDestinationId;
  customerName: string;
  city: string;
  contractCode: string;
  vehicleLabel: string;
  dispatchWindowDays: number;
  dispatchWindowLabel: string;
  geo: GeoPointMeta;
  lines: OutboundFlowLineItem[];
  peggedSuppliers: SupplierId[];
  pallets: number;
  weightKg: number;
  valueKrub: number;
  status: 'ready' | 'gate_wait' | 'at_risk';
  statusLabel: string;
  bottleneckNote: string;
  arcPath: string;
  midX: number;
  midY: number;
}

export function quadBezier(
  x0: number,
  y0: number,
  cx: number,
  cy: number,
  x1: number,
  y1: number
): { path: string; midX: number; midY: number } {
  const path = `M ${x0} ${y0} Q ${cx} ${cy} ${x1} ${y1}`;
  const midX = Math.round(0.25 * x0 + 0.5 * cx + 0.25 * x1);
  const midY = Math.round(0.25 * y0 + 0.5 * cy + 0.25 * y1);
  return { path, midX, midY };
}

export function buildOutboundArcs(
  state: InventoryDomainState,
  summary: OrderCapacitySummary
): OutboundFlowArc[] {
  const customSkus = state.items.filter((it) => it.id.startsWith('sku-custom-'));

  return OUTBOUND_SPECS.map((spec) => {
    const [cx, cy] = OUTBOUND_CONTROL_POINTS[spec.id];
    const { path, midX, midY } = quadBezier(
      CENTRAL_HUB_META.x, CENTRAL_HUB_META.y, cx, cy, spec.geo.x, spec.geo.y
    );

    const lines: OutboundFlowLineItem[] = [];
    let palletsAcc = 0;
    let weightAcc = 0;
    let valueAcc = 0;
    const supplierSet = new Set<SupplierId>();

    const effectiveAllocations =
      spec.id === 'out-samara' && customSkus.length > 0
        ? [
            ...spec.allocations,
            ...customSkus.map((cs: SkuItem) => ({
              skuId: cs.id,
              fallbackCategory: cs.category,
              requiredQty: Math.max(20, Math.round(cs.orderQty * 0.5))
            }))
          ]
        : spec.allocations;

    for (const alloc of effectiveAllocations) {
      const matched =
        state.items.find((it) => it.id === alloc.skuId) ||
        state.items.find((it) => it.category === alloc.fallbackCategory) ||
        state.items[0];
      if (!matched) continue;

      const sup = getSupplier(matched.supplierId);
      supplierSet.add(matched.supplierId);
      const leadDays = computeEffectiveLeadDays(matched, state.transitDelayDays, state.backupChannel);
      const availableAfterOrder = matched.currentStock + matched.orderQty;
      const skuRisk = isSkuAtStockoutRisk(matched, state.transitDelayDays, state.backupChannel);
      const lateArrival = matched.currentStock < alloc.requiredQty && leadDays > spec.dispatchWindowDays + 2;
      const shortfall = availableAfterOrder < alloc.requiredQty || skuRisk || lateArrival;

      palletsAcc += alloc.requiredQty / Math.max(1, matched.unitsPerPallet);
      weightAcc += Math.round(alloc.requiredQty * matched.unitWeightKg);
      valueAcc += Number((alloc.requiredQty * matched.unitCostKrub * 1.14).toFixed(1));

      lines.push({
        skuId: matched.id,
        skuName: matched.name,
        supplierId: matched.supplierId,
        supplierCity: sup.city,
        requiredQty: alloc.requiredQty,
        availableAfterOrder,
        leadDays,
        shortfall
      });
    }

    const bottleneckLine = lines.find((l) => l.shortfall);
    let status: 'ready' | 'gate_wait' | 'at_risk' = 'ready';
    let statusLabel = 'Готово к отгрузке';
    let bottleneckNote = 'Комплект обеспечен складским запасом и волной';

    if (bottleneckLine) {
      status = 'at_risk';
      statusLabel = 'Риск недокомплекта';
      bottleneckNote = `Узкое место: ${bottleneckLine.skuName} (${bottleneckLine.supplierCity}, ${bottleneckLine.leadDays} сут.)`;
    } else if (summary.overLimitCount > 0) {
      status = 'gate_wait';
      statusLabel = 'Ждет укладку РЦ';
      bottleneckNote = 'Перегруз приемки РЦ задерживает комплектацию ворот';
    }

    return {
      id: spec.id,
      customerName: spec.customerName,
      city: spec.geo.city,
      contractCode: spec.contractCode,
      vehicleLabel: spec.vehicleLabel,
      dispatchWindowDays: spec.dispatchWindowDays,
      dispatchWindowLabel: spec.dispatchWindowLabel,
      geo: spec.geo,
      lines,
      peggedSuppliers: Array.from(supplierSet),
      pallets: Number(palletsAcc.toFixed(1)),
      weightKg: weightAcc,
      valueKrub: Number(valueAcc.toFixed(1)),
      status,
      statusLabel,
      bottleneckNote,
      arcPath: path,
      midX,
      midY
    };
  });
}
