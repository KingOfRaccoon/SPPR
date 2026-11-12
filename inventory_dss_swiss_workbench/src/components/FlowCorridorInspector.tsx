import { BACKUP_CHANNELS } from '../data/presets';
import type { InboundFlowArc, OutboundFlowArc } from '../data/flowNetwork';
import { inventoryStore } from '../store/domainStore';
import { RouteMapIcon } from './Icons';
import {
  CentralHubPanel,
  InboundCorridorPanel,
  OutboundCorridorPanel,
  resolveHeaderTitle,
  SkuPeggingPanel
} from './FlowCorridorSubpanels';
import type {
  BackupChannelMode,
  FlowLensMode,
  InventoryDomainState,
  OrderCapacitySummary,
  SelectedMapNodeId,
  SkuItem
} from '../types/domain';

interface FlowCorridorInspectorProps {
  state: InventoryDomainState;
  summary: OrderCapacitySummary;
  lens: FlowLensMode;
  activeSku: SkuItem;
  selectedNodeId: SelectedMapNodeId;
  selectedInbound?: InboundFlowArc;
  selectedOutbound?: OutboundFlowArc;
  outbound: OutboundFlowArc[];
  dependentCustomers: OutboundFlowArc[];
  outboundPallets: number;
  outboundValueKrub: number;
}

export function FlowCorridorInspector({
  state,
  summary,
  lens,
  activeSku,
  selectedNodeId,
  selectedInbound,
  selectedOutbound,
  outbound,
  dependentCustomers,
  outboundPallets,
  outboundValueKrub
}: FlowCorridorInspectorProps) {
  const renderInspectorBody = () => {
    if (lens === 'sku_peg') {
      return <SkuPeggingPanel state={state} activeSku={activeSku} outbound={outbound} />;
    }
    if (selectedInbound) {
      return (
        <InboundCorridorPanel
          selectedInbound={selectedInbound}
          dependentCustomers={dependentCustomers}
        />
      );
    }
    if (selectedOutbound) {
      return <OutboundCorridorPanel selectedOutbound={selectedOutbound} />;
    }
    return (
      <CentralHubPanel
        state={state}
        summary={summary}
        outbound={outbound}
        outboundPallets={outboundPallets}
        outboundValueKrub={outboundValueKrub}
      />
    );
  };

  return (
    <article
      data-card="flow-corridor-inspector"
      className="surface-card p-3.5 h-full flex flex-col justify-between gap-2.5"
    >
      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <RouteMapIcon size={15} className="text-accent-primary" />
            <span className="text-xs font-medium text-secondary">
              {resolveHeaderTitle(lens, selectedInbound, selectedOutbound)}
            </span>
          </div>
          {lens === 'sku_peg' ? (
            <button
              type="button"
              data-ui="btn-ghost"
              onClick={() => inventoryStore.setMapLens('all')}
              className="btn-ghost radius-control text-xs"
            >
              Все потоки
            </button>
          ) : (
            selectedNodeId !== 'dc-moscow' && (
              <button
                type="button"
                data-ui="btn-ghost"
                onClick={() => inventoryStore.selectMapNode('dc-moscow')}
                className="btn-ghost radius-control text-xs"
              >
                Сводка РЦ
              </button>
            )
          )}
        </div>

        {renderInspectorBody()}
      </div>

      <div className="space-y-2 pt-0.5">
        <div className="space-y-1">
          <label htmlFor="map-channel-select" className="block text-xs font-medium text-secondary">
            Канал подвоза до РЦ
          </label>
          <select
            id="map-channel-select"
            value={state.backupChannel}
            onChange={(e) =>
              inventoryStore.setTransitScenario(
                state.transitDelayDays,
                e.target.value as BackupChannelMode
              )
            }
            className="w-full field-compact"
          >
            {Object.values(BACKUP_CHANNELS).map((ch) => (
              <option key={ch.id} value={ch.id}>
                {ch.label} ({ch.leadDeltaDays === 0 ? 'база' : `${ch.leadDeltaDays}д`})
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          data-primary-action="true"
          onClick={() => inventoryStore.reconcileNetworkFlows()}
          className="btn-primary w-full radius-control"
        >
          Выровнять потоки сети
        </button>
      </div>
    </article>
  );
}
