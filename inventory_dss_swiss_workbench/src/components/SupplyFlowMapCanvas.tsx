import type { InboundFlowArc, OutboundFlowArc } from '../data/flowNetwork';
import {
  computeStrokeWidth,
  formatFlowValue,
  resolveArcOpacity,
  resolveInboundColor,
  resolveOutboundColor
} from './SupplyFlowMapBackdrop';
import type {
  FlowLensMode,
  FlowMetricMode,
  SelectedMapNodeId,
  SkuItem
} from '../types/domain';

export { resolveNodeFillColor, SupplyFlowMapBackdrop } from './SupplyFlowMapBackdrop';

interface SupplyFlowArcLayersProps {
  inbound: InboundFlowArc[];
  outbound: OutboundFlowArc[];
  focusId: SelectedMapNodeId;
  lens: FlowLensMode;
  metric: FlowMetricMode;
  peggedSku?: SkuItem;
  selectedOutbound?: OutboundFlowArc;
}

export function SupplyFlowArcLayers({
  inbound,
  outbound,
  focusId,
  lens,
  metric,
  peggedSku,
  selectedOutbound
}: SupplyFlowArcLayersProps) {
  return (
    <>
      <g aria-hidden="true">
        {inbound.map((arc) => {
          const isEmpty = arc.skuCount === 0;
          const isPeggedToCustomer = Boolean(selectedOutbound && selectedOutbound.peggedSuppliers.includes(arc.id));
          const isSkuInboundMatch = Boolean(lens === 'sku_peg' && peggedSku && arc.id === peggedSku.supplierId);
          const isSelected =
            lens === 'sku_peg'
              ? isSkuInboundMatch
              : focusId === arc.id || focusId === 'dc-moscow' || isPeggedToCustomer;

          let dimmed = false;
          if (lens === 'outbound') dimmed = !isPeggedToCustomer;
          if (lens === 'at_risk' && !arc.atRisk) dimmed = true;
          if (lens === 'sku_peg') dimmed = !isSkuInboundMatch;

          const strokeColor = resolveInboundColor(isEmpty, arc.atRisk);
          const width = isEmpty ? 1.2 : computeStrokeWidth(arc.pallets, arc.weightKg, arc.budgetKrub, metric);
          const badgeVal =
            isSkuInboundMatch && peggedSku
              ? `+${peggedSku.orderQty} шт.`
              : formatFlowValue(arc.pallets, arc.weightKg, arc.budgetKrub, metric);

          return (
            <g key={`in-${arc.id}`} opacity={resolveArcOpacity(dimmed, isSelected, 0.78)}>
              <path
                d={arc.arcPath}
                fill="none"
                stroke={strokeColor}
                strokeWidth={isSelected && !isEmpty ? width + 0.7 : width}
                strokeDasharray={isEmpty ? '3 4' : undefined}
                strokeLinecap="round"
              />
              {!isEmpty && (
                <g transform={`translate(${arc.midX}, ${arc.midY})`}>
                  <rect x={-27} y={-8.5} width={54} height={17} rx={2} fill="var(--surface-1)" stroke={strokeColor} strokeWidth={0.9} />
                  <text x={0} y={3.5} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)">{badgeVal}</text>
                </g>
              )}
            </g>
          );
        })}
      </g>

      <g aria-hidden="true">
        {outbound.map((arc) => {
          const isPeggedToSupplier = arc.peggedSuppliers.includes(focusId as InboundFlowArc['id']);
          const matchedSkuLine = lens === 'sku_peg' && peggedSku ? arc.lines.find((ln) => ln.skuId === peggedSku.id) : undefined;
          const isSelected =
            lens === 'sku_peg'
              ? Boolean(matchedSkuLine)
              : focusId === arc.id || focusId === 'dc-moscow' || isPeggedToSupplier;

          let dimmed = false;
          if (lens === 'inbound') dimmed = !isPeggedToSupplier;
          if (lens === 'at_risk' && arc.status === 'ready') dimmed = true;
          if (lens === 'sku_peg') dimmed = !matchedSkuLine;

          const strokeColor = resolveOutboundColor(arc.status);
          const width = computeStrokeWidth(arc.pallets, arc.weightKg, arc.valueKrub, metric);
          const badgeVal = matchedSkuLine
            ? `-${matchedSkuLine.requiredQty} шт.`
            : formatFlowValue(arc.pallets, arc.weightKg, arc.valueKrub, metric);

          return (
            <g key={`out-${arc.id}`} opacity={resolveArcOpacity(dimmed, isSelected, 0.82)}>
              <path d={arc.arcPath} fill="none" stroke={strokeColor} strokeWidth={isSelected ? width + 0.6 : width} strokeDasharray="7 3.5" strokeLinecap="round" />
              <g transform={`translate(${arc.midX}, ${arc.midY})`}>
                <rect x={-27} y={-8.5} width={54} height={17} rx={2} fill="var(--surface-1)" stroke={strokeColor} strokeWidth={0.9} />
                <text x={0} y={3.5} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)">{badgeVal}</text>
              </g>
            </g>
          );
        })}
      </g>
    </>
  );
}
