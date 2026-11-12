import React, { useEffect, useState } from 'react';
import {
  CENTRAL_HUB_META,
  InboundFlowArc,
  OutboundFlowArc
} from '../data/flowNetwork';
import {
  resolveNodeFillColor,
  SupplyFlowArcLayers,
  SupplyFlowMapBackdrop
} from './SupplyFlowMapCanvas';
import type {
  FlowLensMode,
  FlowMetricMode,
  MapZoomRegion,
  SelectedMapNodeId,
  SkuItem
} from '../types/domain';

interface SupplyFlowMapProps {
  inbound: InboundFlowArc[];
  outbound: OutboundFlowArc[];
  selectedNodeId: SelectedMapNodeId;
  lens: FlowLensMode;
  metric: FlowMetricMode;
  region: MapZoomRegion;
  effectivePalletLimit: number;
  totalPallets: number;
  peggedSku?: SkuItem;
  onSelectNode: (nodeId: SelectedMapNodeId) => void;
}

const REGION_VIEWBOX: Record<MapZoomRegion, string> = {
  all: '0 0 760 220',
  west_center: '44 14 440 198',
  volga_ural: '216 12 532 200'
};

const SHORT_CITY: Record<string, string> = {
  'Санкт-Петербург': 'Санкт-Петербург',
  'Ярославль': 'Ярославль',
  'Москва (Подольск)': 'РЦ Москва',
  'Тула': 'Тула',
  'Нижний Новгород': 'Н. Новгород',
  'Воронеж': 'Воронеж',
  'Казань': 'Казань',
  'Самара': 'Самара',
  'Екатеринбург': 'Екатеринбург'
};

const MOBILE_HIT_SHIFT: Partial<Record<SelectedMapNodeId, [number, number]>> = {
  'sever-snab': [24, -20],
  'out-tula': [-24, 24],
  'volga-pribor': [-16, -20],
  'out-samara': [16, 20]
};

function renderNodeGlyph(kind: 'supplier' | 'hub' | 'customer', x: number, y: number, fillColor: string) {
  if (kind === 'hub') {
    return (
      <g>
        <rect x={x - 8} y={y - 8} width={16} height={16} rx={2} fill={fillColor} stroke="var(--surface-1)" strokeWidth={1.5} />
        <rect x={x - 3} y={y - 3} width={6} height={6} rx={1} fill="var(--surface-1)" />
      </g>
    );
  }
  if (kind === 'supplier') {
    return (
      <rect x={x - 5.5} y={y - 5.5} width={11} height={11} rx={1.5} fill={fillColor} stroke="var(--surface-1)" strokeWidth={1.4} />
    );
  }
  return <circle cx={x} cy={y} r={6} fill={fillColor} stroke="var(--surface-1)" strokeWidth={1.4} />;
}

export function SupplyFlowMap({
  inbound,
  outbound,
  selectedNodeId,
  lens,
  metric,
  region,
  effectivePalletLimit,
  totalPallets,
  peggedSku,
  onSelectNode
}: SupplyFlowMapProps) {
  const [hoveredId, setHoveredId] = useState<SelectedMapNodeId | null>(null);
  const [isCompactViewport, setIsCompactViewport] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  );

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onResize = () => setIsCompactViewport(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const focusId = hoveredId || selectedNodeId;
  const orderedNodes = [
    ...inbound.map((f) => ({
      id: f.id as SelectedMapNodeId,
      label: f.city,
      x: f.geo.x,
      y: f.geo.y,
      kind: 'supplier' as const,
      readoutText: `Вход в РЦ: ${f.supplierName}, ${f.city}, ${f.pallets.toFixed(1)} палл., плечо ${f.leadDays} сут.`
    })),
    {
      id: 'dc-moscow' as SelectedMapNodeId,
      label: CENTRAL_HUB_META.city,
      x: CENTRAL_HUB_META.x,
      y: CENTRAL_HUB_META.y,
      kind: 'hub' as const,
      readoutText: `Центральный РЦ Подольск: приемка ${totalPallets.toFixed(1)} из ${effectivePalletLimit} палл., отгрузка 4 заказчикам`
    },
    ...outbound.map((o) => ({
      id: o.id as SelectedMapNodeId,
      label: o.city,
      x: o.geo.x,
      y: o.geo.y,
      kind: 'customer' as const,
      readoutText: `Отгрузка: ${o.customerName}, окно ${o.dispatchWindowLabel}, ${o.pallets.toFixed(1)} палл., ${o.statusLabel}`
    }))
  ];

  const activeNodeInfo =
    orderedNodes.find((n) => n.id === focusId) || orderedNodes[4] || orderedNodes[0];
  const selectedOutbound = outbound.find((o) => o.id === focusId);

  const handlePointKeyDown = (
    e: React.KeyboardEvent<SVGGElement>,
    idx: number,
    nodeId: SelectedMapNodeId
  ) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelectNode(nodeId);
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      onSelectNode(orderedNodes[(idx + 1) % orderedNodes.length].id);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      onSelectNode(orderedNodes[(idx - 1 + orderedNodes.length) % orderedNodes.length].id);
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="surface-inset p-1.5 radius-control overflow-hidden">
        <svg
          data-chart="supply-flow-map"
          viewBox={REGION_VIEWBOX[region]}
          role="group"
          aria-label="Географическая карта входящих поставок на центральный склад и исходящих отгрузок заказчикам"
          className="w-full h-auto block select-none"
          style={{ maxHeight: '202px' }}
        >
          <SupplyFlowMapBackdrop />
          <SupplyFlowArcLayers
            inbound={inbound}
            outbound={outbound}
            focusId={focusId}
            lens={lens}
            metric={metric}
            peggedSku={peggedSku}
            selectedOutbound={selectedOutbound}
          />

          {orderedNodes.map((node, idx) => {
            const isSelected = selectedNodeId === node.id;
            const inArc = inbound.find((i) => i.id === node.id);
            const outArc = outbound.find((o) => o.id === node.id);
            const geo = inArc?.geo || outArc?.geo || CENTRAL_HUB_META;
            const hasRisk = Boolean(
              (inArc && inArc.atRisk) || (outArc && outArc.status === 'at_risk')
            );
            const fillColor = resolveNodeFillColor(node.kind, hasRisk);
            const hitHalf = isCompactViewport ? 68 : 24;
            const [shiftX, shiftY] = isCompactViewport
              ? MOBILE_HIT_SHIFT[node.id] || [0, 0]
              : [0, 0];

            return (
              <g
                key={node.id}
                data-chart-point={node.id}
                role="button"
                tabIndex={0}
                aria-label={node.readoutText}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                onFocus={() => setHoveredId(node.id)}
                onBlur={() => setHoveredId(null)}
                onClick={() => onSelectNode(node.id)}
                onKeyDown={(e) => handlePointKeyDown(e, idx, node.id)}
                className="cursor-pointer"
              >
                <rect x={node.x + shiftX - hitHalf} y={node.y + shiftY - hitHalf} width={hitHalf * 2} height={hitHalf * 2} fill="transparent" />
                {isSelected && (
                  <circle cx={node.x} cy={node.y} r={node.kind === 'hub' ? 14 : 11} fill="none" stroke="var(--accent-primary)" strokeWidth={1.6} />
                )}
                {renderNodeGlyph(node.kind, node.x, node.y, fillColor)}
                <text
                  x={node.x + geo.labelDx}
                  y={node.y + geo.labelDy}
                  textAnchor={geo.labelAnchor}
                  fontSize={11.5}
                  fontWeight={isSelected ? 700 : 600}
                  fill="var(--text-primary)"
                >
                  {SHORT_CITY[geo.city] || geo.city}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-secondary">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: 1, backgroundColor: 'oklch(0.36 0.068 248)', display: 'inline-block' }} />
            <span>Вход от заводов</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: 1, backgroundColor: 'var(--text-primary)', display: 'inline-block' }} />
            <span>Центральный РЦ</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: 999, backgroundColor: 'var(--status-success-fg)', display: 'inline-block' }} />
            <span>Отгрузка клиенту</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: 999, backgroundColor: 'var(--accent-primary)', display: 'inline-block' }} />
            <span>Риск срока</span>
          </span>
        </div>
        <span className="text-muted">Стрелки ←/→ по узлам</span>
      </div>

      <div data-chart-context="true" className="chart-readout text-sm" role="status" aria-live="polite">
        <span className="font-medium text-primary">{activeNodeInfo.readoutText}</span>
      </div>
    </div>
  );
}
