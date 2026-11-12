import { useState } from 'react';
import { BACKUP_CHANNELS } from '../data/presets';
import { computeSupplyNetwork } from '../data/flowNetwork';
import { inventoryStore } from '../store/domainStore';
import { computeOrderSummary } from '../store/replenishmentEngine';
import { useAnimatedNumber } from '../hooks/useAnimatedNumber';
import { SupplyFlowMap } from '../components/SupplyFlowMap';
import { FlowCorridorInspector } from '../components/FlowCorridorInspector';
import { SupplyCorridorLedger } from '../components/SupplyCorridorLedger';
import type {
  FlowLensMode,
  FlowMetricMode,
  InventoryDomainState,
  MapZoomRegion,
  SelectedMapNodeId
} from '../types/domain';

interface ScreenSupplyMapProps {
  state: InventoryDomainState;
}

const LENS_OPTIONS: Array<{ id: FlowLensMode; label: string }> = [
  { id: 'all', label: 'Все потоки' },
  { id: 'inbound', label: 'Вход в РЦ' },
  { id: 'outbound', label: 'Клиентам' },
  { id: 'at_risk', label: 'Под риском' },
  { id: 'sku_peg', label: 'Трасса позиции' }
];

const METRIC_OPTIONS: Array<{ id: FlowMetricMode; label: string }> = [
  { id: 'pallets', label: 'Паллеты' },
  { id: 'weight', label: 'Тоннаж' },
  { id: 'budget', label: 'Бюджет' }
];

const REGION_OPTIONS: Array<{ id: MapZoomRegion; label: string }> = [
  { id: 'all', label: 'Вся сеть' },
  { id: 'west_center', label: 'Центр и СЗ' },
  { id: 'volga_ural', label: 'Волга и Урал' }
];

export function ScreenSupplyMap({ state }: ScreenSupplyMapProps) {
  const [metric, setMetric] = useState<FlowMetricMode>('pallets');
  const [region, setRegion] = useState<MapZoomRegion>('all');

  const lens: FlowLensMode = state.mapLens || 'all';
  const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const net = computeSupplyNetwork(state);
  const selectedNodeId: SelectedMapNodeId = state.selectedMapNodeId || 'dc-moscow';

  const animInboundPallets = useAnimatedNumber(net.inboundPallets, 220);
  const animOutboundPallets = useAnimatedNumber(net.outboundPallets, 220);
  const animOtifPct = useAnimatedNumber(net.otifNetworkPct, 220);

  const selectedInbound = net.inbound.find((f) => f.id === selectedNodeId);
  const selectedOutbound = net.outbound.find((o) => o.id === selectedNodeId);
  const channelInfo = BACKUP_CHANNELS[state.backupChannel];
  const dependentCustomers = selectedInbound
    ? net.outbound.filter((o) => o.peggedSuppliers.includes(selectedInbound.id))
    : [];

  return (
    <section
      data-screen-view="screen-supply-map"
      data-shell="supply-flow-map"
      data-active-entity={state.activeSkuId}
      className="app-rail-stage px-3 sm:px-4 lg:px-5 py-3 space-y-3"
    >
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
        <div className="xl:col-span-8 min-w-0">
          <article data-card="swiss-supply-flow-map" className="surface-card p-3.5 h-full flex flex-col gap-2">
            <div className="flex flex-wrap items-start justify-between gap-2 min-w-0">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-primary">
                  Карта входящих поставок и клиентских отгрузок
                </h1>
                <p className="text-sm text-secondary tabular-nums">
                  Канал: {channelInfo.label}, сдвиг +{state.transitDelayDays} сут.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <div className="seg-group" role="group" aria-label="Метрика толщины потоков">
                  {METRIC_OPTIONS.map((m) => (
                    <button key={m.id} type="button" aria-pressed={metric === m.id} onClick={() => setMetric(m.id)} className="seg-btn">
                      {m.label}
                    </button>
                  ))}
                </div>
                <div className="seg-group" role="group" aria-label="Масштаб региона карты">
                  {REGION_OPTIONS.map((r) => (
                    <button key={r.id} type="button" aria-pressed={region === r.id} onClick={() => setRegion(r.id)} className="seg-btn">
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="surface-inset px-3 py-2 grid grid-cols-2 sm:grid-cols-4 gap-3 items-end tabular-nums">
              <div>
                <div className="text-xs text-secondary">Вход в РЦ</div>
                <div data-hero-metric="true" className="hero-metric font-semibold text-primary tabular-nums">
                  {animInboundPallets.toFixed(1)} палл.
                </div>
              </div>
              <div>
                <div className="text-xs text-secondary">Вывоз клиентам</div>
                <div className="text-base font-semibold text-primary tabular-nums">
                  {animOutboundPallets.toFixed(1)} палл.
                </div>
              </div>
              <div>
                <div className="text-xs text-secondary">Надежность сети</div>
                <div className="text-base font-semibold text-primary tabular-nums">
                  {animOtifPct.toFixed(1)}% OTIF
                </div>
              </div>
              <div>
                <div className="text-xs text-secondary">Узкие плечи</div>
                <div className={`text-base font-semibold tabular-nums ${net.riskCorridorsCount > 0 ? 'text-status-danger' : 'text-status-success'}`}>
                  {net.riskCorridorsCount} напр.
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="seg-group flex-wrap" role="group" aria-label="Линза потоков поставок">
                {LENS_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    data-map-lens={opt.id}
                    aria-pressed={lens === opt.id}
                    onClick={() => inventoryStore.setMapLens(opt.id)}
                    className="seg-btn"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5 min-w-0" style={{ flex: '1 1 256px' }}>
                <label htmlFor="map-peg-sku-select" className="hidden sm:inline text-xs text-muted shrink-0">
                  SKU:
                </label>
                <select
                  id="map-peg-sku-select"
                  aria-label="Позиция для трассировки потоков"
                  value={activeSku.id}
                  onChange={(e) => {
                    inventoryStore.selectSku(e.target.value);
                    inventoryStore.setMapLens('sku_peg');
                  }}
                  className="w-full field-compact"
                >
                  {state.items.map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.name.length > 22 ? `${it.name.slice(0, 21).trimEnd()}…` : it.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <SupplyFlowMap
              inbound={net.inbound}
              outbound={net.outbound}
              selectedNodeId={selectedNodeId}
              lens={lens}
              metric={metric}
              region={region}
              effectivePalletLimit={summary.effectivePalletLimit}
              totalPallets={summary.totalPallets}
              peggedSku={activeSku}
              onSelectNode={(id) => inventoryStore.selectMapNode(id)}
            />
          </article>
        </div>

        <div className="xl:col-span-4 min-w-0">
          <FlowCorridorInspector
            state={state}
            summary={summary}
            lens={lens}
            activeSku={activeSku}
            selectedNodeId={selectedNodeId}
            selectedInbound={selectedInbound}
            selectedOutbound={selectedOutbound}
            outbound={net.outbound}
            dependentCustomers={dependentCustomers}
            outboundPallets={net.outboundPallets}
            outboundValueKrub={net.outboundValueKrub}
          />
        </div>
      </div>

      <SupplyCorridorLedger
        inbound={net.inbound}
        outbound={net.outbound}
        selectedNodeId={selectedNodeId}
      />
    </section>
  );
}
