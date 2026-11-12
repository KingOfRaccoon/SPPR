import React, { useState } from 'react';
import { computeSawtoothProjection, SawtoothProjection } from '../store/replenishmentEngine';
import type {
  BackupChannelMode,
  SkuItem,
  TransitDelayDays
} from '../types/domain';

interface SawtoothProjectionChartProps {
  item: SkuItem;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  compact?: boolean;
}

type MilestoneKey = 'start' | 'arrival' | 'end';

function formatSawtoothStatus(proj: SawtoothProjection, hasGapRisk: boolean): string {
  if (proj.stockoutGapDays > 0) {
    return `Разрыв ${proj.stockoutGapDays} сут. до Д+${proj.leadDays}`;
  }
  if (hasGapRisk) {
    return `Пробой буфера SS (${proj.preArrivalStock} < ${proj.safetyUnits} шт.)`;
  }
  return `Защищено: пик ${proj.arrivalPeakStock} шт. в Д+${proj.leadDays}`;
}

export function SawtoothProjectionChart({
  item,
  transitDelayDays,
  backupChannel,
  compact = false
}: SawtoothProjectionChartProps) {
  const [focusKey, setFocusKey] = useState<MilestoneKey>('arrival');

  const proj = computeSawtoothProjection(item, transitDelayDays, backupChannel, 21);

  const plotLeft = 40;
  const plotRight = 352;
  const plotTop = 14;
  const plotBottom = 82;
  const plotW = plotRight - plotLeft;
  const plotH = plotBottom - plotTop;

  const toX = (day: number): number =>
    Number((plotLeft + (day / proj.horizonDays) * plotW).toFixed(1));
  const toY = (stock: number): number =>
    Number(
      (plotBottom - (Math.min(proj.maxStock, Math.max(0, stock)) / proj.maxStock) * plotH).toFixed(1)
    );

  const ySafety = toY(proj.safetyUnits);
  const xArrival = toX(proj.leadDays);
  const yPreArrival = toY(proj.preArrivalStock);
  const yPeak = toY(proj.arrivalPeakStock);
  const yStart = toY(item.currentStock);
  const yEnd = toY(proj.endStock);

  const polylinePoints = proj.vertices.map((v) => `${toX(v.day)},${toY(v.stock)}`).join(' ');
  const areaPoints = `${plotLeft},${plotBottom} ${polylinePoints} ${plotRight},${plotBottom}`;
  const arrivalLabelX = Math.max(118, Math.min(256, xArrival));
  const hasGapRisk = proj.stockoutGapDays > 0 || proj.preArrivalStock < proj.safetyUnits;

  const milestones: Array<{
    key: MilestoneKey;
    cx: number;
    cy: number;
    hitX: number;
    label: string;
    readout: string;
  }> = [
    {
      key: 'start',
      cx: plotLeft,
      cy: yStart,
      hitX: plotLeft + 14,
      label: `Старт Д0: остаток ${item.currentStock} шт., расход ${item.dailyDemand} шт./сут.`,
      readout: `Д0 старт: ${item.currentStock} шт., расход ${item.dailyDemand} шт./сут.`
    },
    {
      key: 'arrival',
      cx: xArrival,
      cy: yPeak,
      hitX: Math.max(plotLeft + 92, Math.min(plotRight - 92, xArrival)),
      label: `Приход Д+${proj.leadDays}: до разгрузки ${proj.preArrivalStock} шт., скачок +${item.orderQty} до ${proj.arrivalPeakStock} шт.`,
      readout:
        proj.stockoutGapDays > 0
          ? `Д+${proj.leadDays} приход: провал ${proj.stockoutGapDays} сут., затем ${proj.arrivalPeakStock} шт.`
          : `Д+${proj.leadDays} приход: минимум ${proj.preArrivalStock} шт., пик ${proj.arrivalPeakStock} шт.`
    },
    {
      key: 'end',
      cx: plotRight,
      cy: yEnd,
      hitX: plotRight - 14,
      label: `Горизонт Д+${proj.horizonDays}: прогноз остатка ${proj.endStock} шт. при буфере ${proj.safetyUnits} шт.`,
      readout: `Д+${proj.horizonDays} прогноз: ${proj.endStock} шт. (буфер SS ${proj.safetyUnits} шт.)`
    }
  ];

  const activeMilestone = milestones.find((m) => m.key === focusKey) || milestones[1];

  const handleKey = (e: React.KeyboardEvent<SVGGElement>, idx: number) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusKey(milestones[(idx + 1) % milestones.length].key);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusKey(milestones[(idx - 1 + milestones.length) % milestones.length].key);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setFocusKey(milestones[idx].key);
    }
  };

  return (
    <div className="space-y-1.5 tabular-nums" data-sawtooth-widget="true">
      <div className="flex flex-wrap items-center justify-between gap-1.5 text-xs">
        <span className="font-medium text-secondary">Прогноз остатка 21 сут. (пила запаса)</span>
        <span
          data-chart-context="true"
          className={`font-semibold ${hasGapRisk ? 'text-status-danger' : 'text-status-success'}`}
        >
          {formatSawtoothStatus(proj, hasGapRisk)}
        </span>
      </div>

      <div className="surface-inset p-1.5 radius-control">
        <svg
          data-chart="sawtooth-projection"
          viewBox="0 0 360 104"
          role="group"
          aria-label={`Пилообразный прогноз остатка ${item.name} на 21 сутки`}
          className="w-full h-auto block select-none"
          style={{ maxHeight: compact ? '80px' : '104px' }}
        >
          <g aria-hidden="true">
            <rect
              x={plotLeft}
              y={ySafety}
              width={plotW}
              height={Math.max(2, plotBottom - ySafety)}
              fill={hasGapRisk ? 'var(--status-danger-bg)' : 'var(--surface-2)'}
              opacity={hasGapRisk ? 0.68 : 0.75}
            />
            <line x1={plotLeft} y1={plotTop} x2={plotRight} y2={plotTop} stroke="var(--border-subtle)" strokeWidth={0.85} />
            <line
              x1={plotLeft}
              y1={ySafety}
              x2={plotRight}
              y2={ySafety}
              stroke={hasGapRisk ? 'var(--accent-primary)' : 'var(--text-muted)'}
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <line x1={plotLeft} y1={plotBottom} x2={plotRight} y2={plotBottom} stroke="var(--border-subtle)" strokeWidth={1} />
            <polygon points={areaPoints} fill="oklch(0.36 0.068 248)" opacity={0.09} />
            <polyline
              points={polylinePoints}
              fill="none"
              stroke="oklch(0.36 0.068 248)"
              strokeWidth={1.9}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <line
              x1={xArrival}
              y1={yPreArrival}
              x2={xArrival}
              y2={yPeak}
              stroke="var(--accent-primary)"
              strokeWidth={2.4}
              strokeLinecap="round"
            />
            <text x={4} y={18} fontSize={11} fill="var(--text-muted)">{proj.maxStock}</text>
            <text x={4} y={82} fontSize={11} fill="var(--text-muted)">0</text>
            <text x={plotLeft} y={99} textAnchor="start" fontSize={11} fill="var(--text-muted)">Д0</text>
            <text x={arrivalLabelX} y={99} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)">
              Приход Д+{proj.leadDays}
            </text>
            <text x={plotRight} y={99} textAnchor="end" fontSize={11} fill="var(--text-muted)">
              Д+{proj.horizonDays}
            </text>
          </g>

          {milestones.map((ms, idx) => {
            const isSelected = ms.key === activeMilestone.key;
            return (
              <g
                key={ms.key}
                data-chart-point={`sawtooth-${ms.key}`}
                role="button"
                tabIndex={0}
                aria-label={ms.label}
                onMouseEnter={() => setFocusKey(ms.key)}
                onFocus={() => setFocusKey(ms.key)}
                onClick={() => setFocusKey(ms.key)}
                onKeyDown={(e) => handleKey(e, idx)}
                className="cursor-pointer"
              >
                <rect x={ms.hitX - 36} y={6} width={72} height={90} fill="transparent" />
                {isSelected && (
                  <circle cx={ms.cx} cy={ms.cy} r={6.5} fill="none" stroke="var(--accent-primary)" strokeWidth={1.4} />
                )}
                <circle
                  cx={ms.cx}
                  cy={ms.cy}
                  r={3.6}
                  fill={ms.key === 'arrival' ? 'var(--accent-primary)' : 'oklch(0.36 0.068 248)'}
                  stroke="var(--surface-1)"
                  strokeWidth={1.2}
                />
              </g>
            );
          })}
        </svg>
      </div>

      <div className="chart-readout text-xs" aria-live="polite">
        <span className="font-medium text-primary">{activeMilestone.readout}</span>
        <span className="text-muted">Буфер SS: {proj.safetyUnits} шт.</span>
      </div>
    </div>
  );
}
