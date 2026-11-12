import type { CapacityGauge } from './capacityHorizonModel';

export function CapacityHorizonGauges({ gauges }: { gauges: CapacityGauge[] }) {
  return (
    <div className="xl:col-span-4 min-w-0">
      <div className="surface-inset p-3 space-y-2.5 tabular-nums">
        {gauges.map((g) => {
          const fillPct = Math.max(4, Math.min(100, Math.round(g.ratio * 84)));
          return (
            <div key={g.id} className="space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-1 text-sm">
                <span className="text-secondary font-medium">{g.label}</span>
                <span className={g.over ? 'font-semibold text-status-danger' : 'font-semibold text-primary'}>
                  {g.valueText}
                </span>
              </div>
              <div className="w-full h-2 bg-surface-2 radius-control overflow-hidden">
                <div
                  style={{ width: `${fillPct}%` }}
                  className={`h-full ${g.over ? 'bg-status-danger' : 'bg-accent-primary'}`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
