import type { OutboundFlowArc } from '../data/flowNetwork';
import type { FlowMetricMode } from '../types/domain';

const MERIDIANS = [112, 266, 420, 562, 696] as const;
const MERIDIAN_LABELS = ['30°В', '38°В', '44°В', '50°В', '60°В'] as const;
const PARALLELS = [44, 120, 192] as const;
const PARALLEL_LABELS = ['60°С', '55°С', '52°С'] as const;

export function formatFlowValue(
  pallets: number,
  weightKg: number,
  moneyKrub: number,
  metric: FlowMetricMode
): string {
  if (metric === 'weight') return `${(weightKg / 1000).toFixed(1)} т`;
  if (metric === 'budget') return `${Math.round(moneyKrub)} тыс.`;
  return `${pallets.toFixed(1)} п.`;
}

export function computeStrokeWidth(
  pallets: number,
  weightKg: number,
  moneyKrub: number,
  metric: FlowMetricMode
): number {
  let ratio = pallets / 22;
  if (metric === 'weight') ratio = weightKg / 6500;
  else if (metric === 'budget') ratio = moneyKrub / 1600;
  return Number(Math.max(1.6, Math.min(5.6, 1.6 + ratio * 3.8)).toFixed(2));
}

export function resolveInboundColor(isEmpty: boolean, atRisk: boolean): string {
  if (isEmpty) return 'var(--border-subtle)';
  if (atRisk) return 'var(--accent-primary)';
  return 'oklch(0.36 0.068 248)';
}

export function resolveOutboundColor(status: OutboundFlowArc['status']): string {
  if (status === 'at_risk') return 'var(--accent-primary)';
  if (status === 'gate_wait') return 'var(--status-warning-fg)';
  return 'var(--status-success-fg)';
}

export function resolveArcOpacity(dimmed: boolean, isSelected: boolean, idleOpacity: number): number {
  if (dimmed) return 0.16;
  if (isSelected) return 1;
  return idleOpacity;
}

export function resolveNodeFillColor(
  kind: 'supplier' | 'hub' | 'customer',
  hasRisk: boolean
): string {
  if (kind === 'hub') return 'var(--text-primary)';
  if (hasRisk) return 'var(--accent-primary)';
  if (kind === 'supplier') return 'oklch(0.36 0.068 248)';
  return 'var(--status-success-fg)';
}

export function SupplyFlowMapBackdrop() {
  return (
    <g aria-hidden="true">
      <path
        d="M 56 28 L 218 22 L 386 26 L 590 30 L 736 50 L 742 138 L 634 198 L 468 208 L 254 210 L 146 188 L 78 126 L 48 64 Z"
        fill="var(--surface-1)"
        stroke="var(--border-subtle)"
        strokeWidth={1}
      />

      {MERIDIANS.map((gx, i) => (
        <g key={`mer-${gx}`}>
          <line x1={gx} y1={10} x2={gx} y2={212} stroke="var(--border-subtle)" strokeWidth={0.75} strokeDasharray="2 4" />
          <text x={gx + 4} y={18} fontSize={11} fill="var(--text-muted)">{MERIDIAN_LABELS[i]}</text>
        </g>
      ))}
      {PARALLELS.map((gy, i) => (
        <g key={`par-${gy}`}>
          <line x1={18} y1={gy} x2={744} y2={gy} stroke="var(--border-subtle)" strokeWidth={0.75} strokeDasharray="2 4" />
          <text x={20} y={gy - 5} fontSize={11} fill="var(--text-muted)">{PARALLEL_LABELS[i]}</text>
        </g>
      ))}

      <path d="M 218 72 Q 278 54 322 58 T 420 128 Q 486 118 536 110 Q 556 146 562 176 L 538 204" fill="none" stroke="oklch(0.84 0.028 240)" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M 536 110 Q 608 92 654 74" fill="none" stroke="oklch(0.84 0.028 240)" strokeWidth={1.1} strokeLinecap="round" />
      <path d="M 668 34 L 662 150" fill="none" stroke="var(--border-subtle)" strokeWidth={1.1} strokeDasharray="3 3" />

      <g transform="translate(64, 198)">
        <line x1={0} y1={8} x2={72} y2={8} stroke="var(--text-muted)" strokeWidth={1.2} />
        <line x1={0} y1={4} x2={0} y2={11} stroke="var(--text-muted)" strokeWidth={1.2} />
        <line x1={72} y1={4} x2={72} y2={11} stroke="var(--text-muted)" strokeWidth={1.2} />
        <text x={12} y={2} fontSize={11} fill="var(--text-muted)">500 км</text>
      </g>
    </g>
  );
}
