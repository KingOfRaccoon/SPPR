import { useState } from 'react';
import { CapacityHorizonGauges } from './CapacityHorizonGauges';
import {
  buildCapacityGauges,
  buildHorizonPoints,
  computeActiveSkuTelemetry,
  resolvePointBarColor
} from './capacityHorizonModel';
import type { InventoryDomainState } from '../types/domain';

interface CapacityHorizonChartProps {
  state: InventoryDomainState;
  onSelectSku: (skuId: string) => void;
}

export function CapacityHorizonChart({ state, onSelectSku }: CapacityHorizonChartProps) {
  const [activeIdx, setActiveIdx] = useState<number>(1);
  const { summary, activeSku, activeLead, activeCoverDays } = computeActiveSkuTelemetry(state);
  const points = buildHorizonPoints(state, summary);
  const gauges = buildCapacityGauges(state, summary);

  const safeIdx = Math.max(0, Math.min(points.length - 1, activeIdx));
  const activePt = points[safeIdx] || points[0];

  const maxPalletScale = Math.max(60, state.constraints.maxPallets + 10);
  const plotTop = 22;
  const plotBottom = 132;
  const plotHeight = plotBottom - plotTop;

  const mapY = (pallets: number) => {
    const clamped = Math.max(0, Math.min(maxPalletScale, pallets));
    return Math.round(plotBottom - (clamped / maxPalletScale) * plotHeight);
  };

  const limitY = mapY(summary.effectivePalletLimit);
  const ceilingY = mapY(state.constraints.maxPallets);
  const linePath = points
    .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.cx} ${mapY(pt.totalPallets)}`)
    .join(' ');

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span data-chart-context="true" className="text-secondary font-medium tabular-nums">
          {activeSku
            ? `${activeSku.name}: покрытие ${activeCoverDays} сут., плечо ${activeLead} сут., окно ${activePt.dayLabel}`
            : `Горизонт загрузки РЦ ${activePt.dayLabel}`}
        </span>
        <span className="hidden md:inline text-xs text-muted tabular-nums">
          Зоны хранения Д+1..Д+14, порог ворот {summary.effectivePalletLimit} палл.
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-2.5 items-center">
        <div className="xl:col-span-8 min-w-0">
          <svg
            data-chart="true"
            width="600"
            height="168"
            viewBox="0 0 600 168"
            style={{ width: '100%', height: 'auto', maxHeight: '138px' }}
            className="w-full block"
            role="img"
            aria-label="Горизонт загрузки паллетомест Д+1..Д+14 по зонам хранения и резерву ворот"
          >
            <rect
              x="46"
              y={plotTop}
              width="548"
              height={Math.max(6, limitY - plotTop)}
              fill="var(--status-warning-bg)"
              fillOpacity="0.62"
            />
            <line x1="46" y1={plotTop} x2="594" y2={plotTop} stroke="var(--border-subtle)" strokeWidth="1" />
            <line x1="46" y1="77" x2="594" y2="77" stroke="var(--border-subtle)" strokeWidth="1" />
            <line x1="46" y1={plotBottom} x2="594" y2={plotBottom} stroke="var(--border-subtle)" strokeWidth="1" />
            <text x="4" y="26" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-sans)">{maxPalletScale}п</text>
            <text x="4" y="81" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-sans)">{Math.round(maxPalletScale / 2)}п</text>
            <text x="4" y="135" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-sans)">0п</text>
            <line x1="46" y1={ceilingY} x2="594" y2={ceilingY} stroke="var(--border-strong)" strokeWidth="1" strokeOpacity="0.35" />
            <line x1="46" y1={limitY} x2="594" y2={limitY} stroke="var(--status-warning-fg)" strokeWidth="1.25" strokeDasharray="4 4" />
            <text x="590" y={Math.max(14, limitY - 4)} textAnchor="end" fill="var(--status-warning-fg)" fontSize="11" fontFamily="var(--font-sans)" fontWeight="600">
              Порог ворот {summary.effectivePalletLimit} палл
            </text>
            <line data-chart-crosshair="true" x1={activePt.cx} y1={plotTop} x2={activePt.cx} y2={plotBottom} stroke="var(--accent-primary)" strokeWidth="1.25" strokeDasharray="3 3" />
            <path d={linePath} fill="none" stroke="var(--text-primary)" strokeWidth="1.4" strokeOpacity="0.45" />

            {points.map((pt, idx) => {
              const isSelected = idx === safeIdx;
              const overGate = pt.totalPallets > summary.effectivePalletLimit + 0.05;
              const totalTop = mapY(pt.totalPallets);
              const totalH = Math.max(6, plotBottom - totalTop);
              const dryH = Math.max(3, Math.round((pt.dryPallets / Math.max(0.1, pt.totalPallets)) * totalH));
              const coldH = Math.max(2, Math.round((pt.coldPallets / Math.max(0.1, pt.totalPallets)) * totalH));
              const quarH = Math.max(2, totalH - dryH - coldH);

              return (
                <g
                  key={pt.dayLabel}
                  data-chart-point={pt.dayLabel}
                  data-chart-node={pt.linkedSkuId}
                  data-canvas-node={pt.linkedSkuId}
                  tabIndex={0}
                  role="button"
                  aria-label={`Горизонт ${pt.dayLabel}: занято ${pt.totalPallets} паллет, резерв ворот ${pt.freeGateReserve} паллет`}
                  onMouseEnter={() => setActiveIdx(idx)}
                  onFocus={() => setActiveIdx(idx)}
                  onClick={() => { setActiveIdx(idx); onSelectSku(pt.linkedSkuId); }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setActiveIdx(idx);
                      onSelectSku(pt.linkedSkuId);
                    }
                  }}
                  className="cursor-pointer"
                >
                  <rect x={pt.cx - 52} y="14" width="104" height="142" fill="transparent" />
                  <rect x={pt.cx - 15} y={plotBottom - dryH} width="30" height={dryH} rx="1" fill={resolvePointBarColor(isSelected, overGate)} fillOpacity={isSelected ? '0.92' : '0.68'} />
                  <rect x={pt.cx - 15} y={plotBottom - dryH - coldH} width="30" height={coldH} fill={isSelected ? 'var(--accent-primary)' : 'var(--text-secondary)'} fillOpacity={isSelected ? '0.62' : '0.42'} />
                  <rect x={pt.cx - 15} y={totalTop} width="30" height={quarH} rx="1" fill="var(--status-warning-fg)" fillOpacity={isSelected ? '0.82' : '0.52'} />
                  <circle cx={pt.cx} cy={totalTop} r={isSelected ? 3.5 : 2.5} fill={isSelected ? 'var(--accent-primary)' : 'var(--surface-1)'} stroke={isSelected ? 'var(--surface-1)' : 'var(--text-primary)'} strokeWidth="1.25" />
                  <text x={pt.cx} y={Math.max(14, totalTop - 6)} textAnchor="middle" fill={isSelected ? 'var(--accent-primary)' : 'var(--text-primary)'} fontSize="11" fontFamily="var(--font-sans)" fontWeight="600">
                    {pt.totalPallets.toFixed(1)}
                  </text>
                  <text x={pt.cx} y="151" textAnchor="middle" fill={isSelected ? 'var(--text-primary)' : 'var(--text-secondary)'} fontSize="11" fontFamily="var(--font-sans)" fontWeight={isSelected ? '700' : '500'}>
                    {pt.dayLabel}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        <CapacityHorizonGauges gauges={gauges} />
      </div>

      <div data-chart-readout="true" className="chart-readout text-sm">
        <span className="font-semibold text-primary">Горизонт: {activePt.dayLabel}</span>
        <span>Сухой: <strong className="text-primary">{activePt.dryPallets.toFixed(1)} палл.</strong></span>
        <span>Холод: <strong className="text-primary">{activePt.coldPallets.toFixed(1)} палл.</strong></span>
        <span>Карантин: <strong className="text-primary">{activePt.quarantinePallets.toFixed(1)} палл.</strong></span>
        <span>Резерв ворот: <strong className="text-primary">{activePt.freeGateReserve.toFixed(1)} палл.</strong></span>
        <span>Доки РЦ: <strong className="text-primary">{activePt.dockLoadPct}%</strong></span>
      </div>
    </div>
  );
}
