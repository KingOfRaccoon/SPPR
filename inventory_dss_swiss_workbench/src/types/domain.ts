export type ScreenId =
  | 'screen-replenishment-notebook'
  | 'screen-supply-map'
  | 'screen-warehouse-limits'
  | 'screen-supplier-choice'
  | 'screen-delivery-buffer'
  | 'screen-order-export';

export type OutboundDestinationId =
  | 'out-tula'
  | 'out-nn'
  | 'out-voronezh'
  | 'out-samara';

export type SelectedMapNodeId =
  | SupplierId
  | 'dc-moscow'
  | OutboundDestinationId;

export type FlowLensMode = 'all' | 'inbound' | 'outbound' | 'at_risk' | 'sku_peg';

export type FlowMetricMode = 'pallets' | 'weight' | 'budget';

export type MapZoomRegion = 'all' | 'west_center' | 'volga_ural';

export type ScenarioPresetId =
  | 'preset-seasonal-peak'
  | 'preset-port-delay'
  | 'preset-tight-warehouse';

export type SupplierId =
  | 'ural-privod'
  | 'balt-komplekt'
  | 'volga-pribor'
  | 'sever-snab';

export type BackupChannelMode =
  | 'direct_rail'
  | 'regional_hub'
  | 'express_auto';

export type TransitDelayDays = 0 | 4 | 9;

export type ViewState = 'Ideal' | 'Empty' | 'Loading' | 'Error';

export type SkuPriority = 'critical' | 'standard';

export interface SupplierOption {
  id: SupplierId;
  name: string;
  city: string;
  leadDays: number;
  reliabilityPct: number;
  priceFactor: number;
  minBatchQty: number;
  termsNote: string;
}

export interface BackupChannelInfo {
  id: BackupChannelMode;
  label: string;
  leadDeltaDays: number;
  costSurchargePct: number;
  note: string;
}

export interface SkuItem {
  id: string;
  name: string;
  category: string;
  currentStock: number;
  dailyDemand: number;
  reorderPoint: number;
  safetyDays: number;
  orderQty: number;
  unitCostKrub: number;
  unitWeightKg: number;
  unitsPerPallet: number;
  supplierId: SupplierId;
  priority: SkuPriority;
  manualOverride?: boolean;
}

export interface WarehouseConstraints {
  maxPallets: number;
  reserveGatePallets: number;
  maxWeightKg: number;
  maxBudgetKrub: number;
}

export interface OrderCapacitySummary {
  totalPallets: number;
  effectivePalletLimit: number;
  totalWeightKg: number;
  totalBudgetKrub: number;
  stockoutRiskCount: number;
  overLimitCount: number;
  avgReliabilityPct: number;
  avgLeadDays: number;
  isFeasible: boolean;
}

export interface BalanceSnapshotMetrics {
  totalPallets: number;
  totalWeightKg: number;
  totalBudgetKrub: number;
  stockoutRiskCount: number;
  overLimitCount: number;
}

export interface BalanceLineDiff {
  skuId: string;
  skuName: string;
  beforeQty: number;
  afterQty: number;
  deltaPallets: number;
  reason: string;
  riskAvoidedKrub?: number;
}

export interface StochasticBufferMetrics {
  serviceLevelPct: number;
  zScore: number;
  sigmaLeadDays: number;
  sigmaDemand: number;
  stochasticSafetyUnits: number;
  stochasticSafetyDays: number;
  stochasticRop: number;
  staticSafetyUnits: number;
  deltaUnits: number;
}

export interface CostOfInactionInfo {
  riskKrub: number;
  stockoutProbPct: number;
  shortfallUnits: number;
  downtimeKrub: number;
  expressDeltaKrub: number;
  otifPenaltyKrub: number;
}

export interface WaveFinancialSummary {
  totalCostOfInactionKrub: number;
  atRiskSkuCount: number;
  workingCapitalKrub: number;
  discreteRampSlots: number;
  floatPallets: number;
  estAnnualWcSavingsKrub: number;
  tcoWaveKrub: number;
}

export interface WhatIfScenarioBranch {
  totalPallets: number;
  totalWeightKg: number;
  totalBudgetKrub: number;
  stockoutRiskCount: number;
  overLimitCount: number;
  totalCostOfInactionKrub: number;
  atRiskSkuCount: number;
  isFeasible: boolean;
}

export interface WhatIfComparisonResult {
  baseline: WhatIfScenarioBranch;
  stress: WhatIfScenarioBranch;
  verdict: string;
}

export interface SupplierNegotiationImpact {
  currentSupplierId: SupplierId;
  candidateSupplierId: SupplierId;
  lineCostDeltaKrub: number;
  sigmaBufferDeltaUnits: number;
  riskDeltaKrub: number;
  netImpactKrub: number;
  verdict: string;
}

export interface LastBalanceDiff {
  appliedAt: string;
  before: BalanceSnapshotMetrics;
  after: BalanceSnapshotMetrics;
  adjustedLinesCount: number;
  lineDiffs?: BalanceLineDiff[];
}

export interface AuditHistoryEntry {
  id: string;
  timeLabel: string;
  summary: string;
  detail: string;
}

export interface ScenarioPreset {
  id: ScenarioPresetId;
  label: string;
  summary: string;
  waveLabel: string;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  constraints: WarehouseConstraints;
  items: SkuItem[];
}

export interface InventoryDomainState {
  activeScreenId: ScreenId;
  activePresetId: ScenarioPresetId;
  activeSkuId: string;
  selectedSupplierId: SupplierId;
  selectedMapNodeId?: SelectedMapNodeId;
  mapLens?: FlowLensMode;
  waveLabel: string;
  transitDelayDays: TransitDelayDays;
  backupChannel: BackupChannelMode;
  constraints: WarehouseConstraints;
  items: SkuItem[];
  lastBalanceDiff: LastBalanceDiff | null;
  exportFormat: 'csv' | 'memo';
  exportNotice: string;
  history: AuditHistoryEntry[];
  toastMessage: string | null;
  toastCanUndo?: boolean;
}
