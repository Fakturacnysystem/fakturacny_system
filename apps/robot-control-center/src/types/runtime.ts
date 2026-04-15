export type RuntimeStateKind =
  | "healthy"
  | "stale"
  | "degraded"
  | "partial"
  | "unresolved"
  | "unavailable"
  | "error";

export type RuntimeTone = "good" | "warn" | "danger" | "info";

export interface RuntimeArtifactFreshness {
  status: "fresh" | "stale" | "unavailable";
  ageSeconds: number;
  thresholdSeconds: number;
  lastArtifactUpdateAt: string;
}

export interface RuntimeIdentity {
  runId: string;
  runSelectionMode: "pinned" | "latest";
  runResolutionSource: "explicit_run_dir" | "explicit_run_id" | "default_latest";
  runPath: string;
  providerId: string;
  mode: string;
  stateKind: RuntimeStateKind;
  reasonCode?: string;
  driftStatus: "locked" | "tracking_latest" | "mismatch" | "unresolved";
  artifactFreshness: RuntimeArtifactFreshness;
  startedAt?: string;
  lastArtifactUpdateAt?: string;
  pinIntegrityStatus: "ok" | "not_pinned" | "mismatch" | "unresolved";
  schemaVersion?: string | number | null;
}

export interface RuntimeSummary {
  providerId: string;
  mode: string;
  runId: string;
  runSelection: {
    mode: "pinned" | "latest";
    target: string;
    resolvedRunDir: string;
  };
  runtimeIdentity: RuntimeIdentity;
  startedAt: string;
  uptimeSec: number;
  portfolio: {
    equityEur: number;
    freeCashEur: number;
    openPositions: number;
    openOrders: number;
  };
  bridge: {
    avgLatencyMs: number;
    wsConnected: boolean;
    restHealthy: boolean;
    health_status: RuntimeStateKind;
    reasonCode?: string;
    reasonText?: string;
    lastUpdatedAt: string;
  };
  performance?: {
    capitalUtilizationPct?: number | null;
    netExpectancyBps?: number | null;
    fillRate?: number | null;
    makerRatio?: number | null;
    targetGap?: Record<string, unknown>;
  };
}

export interface SymbolSnapshot {
  symbol: string;
  venue: string;
  bid: number;
  ask: number;
  spreadBps: number;
  latencyMs: number;
  qualityScore: number;
  stale: boolean;
  ts: string;
}

export interface DecisionRecord {
  id: string;
  symbol: string;
  ts: string;
  intent: string;
  confidence: number;
  expectedEdgeBps: number;
  blockers: string[];
  topReasons: string[];
  riskVerdict: "allow" | "watch" | "block";
  lastAction: string;
}

export interface AlertRecord {
  id: string;
  severity: "info" | "warn" | "critical";
  module: string;
  message: string;
  ts: string;
}

export interface HealthDetail {
  label: string;
  value: string;
  severity: RuntimeTone;
}

export interface HealthState {
  status: "good" | "warn" | "danger";
  bridgeHealthy: boolean;
  backendHealthy: boolean;
  artifactFallbackActive: boolean;
  lastUpdatedAt: string;
  warnings: string[];
  details: HealthDetail[];
  runtimeIdentity?: RuntimeIdentity;
}

export interface IntegrityState {
  doctrineStatus: string;
  capabilityConfidence: string;
  blockers: string[];
  unlockActions: string[];
  warnings: string[];
  degradationState: string;
  details: HealthDetail[];
  lastUpdatedAt: string;
  stateKind: RuntimeStateKind;
  runtimeIdentity?: RuntimeIdentity;
}

export interface ReplayLineItem {
  label: string;
  detail: string;
  ts: string;
  severity?: RuntimeTone;
}

export interface ReplayForensicsState {
  runId: string;
  timeline: ReplayLineItem[];
  incidents: ReplayLineItem[];
  analogMatches: ReplayLineItem[];
  counterfactuals: ReplayLineItem[];
  pnlAttribution: ReplayLineItem[];
  notes: ReplayLineItem[];
  stateKind: RuntimeStateKind;
  lastUpdatedAt: string;
  runtimeIdentity?: RuntimeIdentity;
}

export interface BrainPipelineStep {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail" | "unavailable";
  reasonCodes: string[];
  latencyMs: number | null;
  timestamp: string;
  inputSummary: string;
  outputSummary: string;
  evidence: string[];
  derived: boolean;
}

export interface BrainSymbolView {
  symbol: string;
  venue: string;
  bid: number | null;
  ask: number | null;
  spreadBps: number | null;
  depthNotional: number | null;
  signal: string | null;
  forecast: string | null;
  confidence: number | null;
  currentBlockReason: string | null;
  lastAction: string | null;
  nextEligibleAction: string | null;
  derivedFields: string[];
  ts: string;
}

export interface BrainState {
  runId: string;
  selectedSymbol: string;
  actionState: string;
  whyTrade: string[];
  whyNotTrade: string[];
  blockingReasons: string[];
  supportingSignals: string[];
  costAdjustedEdgeBps: number | null;
  costAdjustedEdgeSource: string | null;
  sellFloorStatus: string;
  marketRegime: string;
  riskGatingOutcome: string;
  executionEligibilityOutcome: string;
  pipeline: BrainPipelineStep[];
  symbolViews: BrainSymbolView[];
  decisionReplay: {
    finalVerdict: string;
    timeline: ReplayLineItem[];
    evidence: ReplayLineItem[];
    linkedArtifacts: string[];
  };
  opportunityRanking?: {
    selectedPlaybook?: string | null;
    selectedScore?: number | null;
    backlogPressure?: number | null;
    falseNegativeRate?: number | null;
    falsePositiveRate?: number | null;
    topCandidates?: Array<{
      symbol: string;
      playbook: string;
      score: number;
      netEdgeBps?: number | null;
      qualityOfEdge?: number | null;
      executionPreference?: string | null;
    }>;
  };
  evidenceNotes: string[];
  stateKind: RuntimeStateKind;
  lastUpdatedAt: string;
  runtimeIdentity?: RuntimeIdentity;
}

export interface ShieldSafetyItem {
  label: string;
  status: "trusted" | "caution" | "unsafe" | "unavailable";
  detail: string;
  evidence: string[];
  ts: string;
}

export interface ShieldGuardItem {
  name: string;
  configuredThreshold: string;
  observedValue: string;
  status: "ok" | "warn" | "block" | "unavailable";
  impact: string;
  evidence: string[];
  lastTriggeredAt?: string | null;
  derived: boolean;
}

export interface ShieldAppliedControlState {
  action: string;
  controlSurface: string;
  mode: string | null;
  degradationApplied: boolean | null;
  forcedRiskMode: string | null;
  sizeMultiplier: number | null;
  reasons: string[];
  flattenedStatus: string | null;
  killPath: string | null;
  steps: number | null;
  ts: string;
}

export interface ShieldQueuedCommand {
  action: string;
  reasonCode: string;
  reasonText: string | null;
  operatorId: string | null;
  effectiveState: string;
  auditReference: string | null;
  ts: string;
}

export interface ShieldUserStreamState {
  status: "connected" | "partial" | "disconnected" | "unavailable";
  detail: string;
  subscribedChannels: string[];
  lastEventType: string | null;
  lastEventAt: string | null;
  evidence: string[];
}

export interface ShieldState {
  runId: string;
  trustVerdict: "trusted" | "caution" | "unsafe";
  trustReasons: string[];
  runtimeSafety: ShieldSafetyItem[];
  appliedControl: ShieldAppliedControlState | null;
  queuedCommand: ShieldQueuedCommand | null;
  userStream: ShieldUserStreamState;
  guardMatrix: ShieldGuardItem[];
  performanceControl?: {
    promotionScore?: number | null;
    promotionStatus?: string | null;
    rollbackTriggered?: boolean | null;
    recoveryMode?: string | null;
    liveDegradationStatus?: string | null;
    selfThrottlingActive?: boolean | null;
    privateStreamHealth?: string | null;
    authorityBoundary?: string | null;
    rollbackRisk?: string | null;
    targetPlausibility?: string | null;
    targetGapNetBps?: number | null;
    readinessStatus?: string | null;
  };
  truthNotes: string[];
  linkedArtifacts: string[];
  stateKind: RuntimeStateKind;
  lastUpdatedAt: string;
  runtimeIdentity?: RuntimeIdentity;
}

export interface ExecutionSummaryMetric {
  label: string;
  value: number | null;
  unit: string;
  detail: string;
  derived: boolean;
}

export interface ExecutionOrder {
  id: string;
  symbol: string;
  side: string | null;
  quantity: number | null;
  targetNotional: number | null;
  price: number | null;
  fees: number | null;
  slippage: number | null;
  status: string;
  venueResponseSummary: string | null;
  rejectionReason: string | null;
  decisionTs: string | null;
  submittedTs: string | null;
  acknowledgedTs: string | null;
  filledTs: string | null;
  canceledTs: string | null;
  rejectedTs: string | null;
  transitions: ReplayLineItem[];
  derivedFields: string[];
}

export interface ExecutionPosition {
  symbol: string;
  side: string | null;
  quantity: number | null;
  exposureNotional: number | null;
  entryPrice: number | null;
  markPrice: number | null;
  unrealizedPnl: number | null;
  realizedPnl: number | null;
  costBasis: number | null;
  holdDurationSec: number | null;
  exitEligibility: string | null;
  sellFloorStatus: string | null;
  derivedFields: string[];
  ts: string;
}

export interface ExecutionAccountSnapshot {
  venue: string | null;
  symbol: string | null;
  baselineBalance: number | null;
  exchangeBalance: number | null;
  grossExposureNotional: number | null;
  localCashDelta: number | null;
  realizedPnl: number | null;
  unrealizedPnl: number | null;
  cumulativeFees: number | null;
  cumulativeSlippage: number | null;
  fillCount: number | null;
  ts: string;
  derivedFields: string[];
}

export interface ExecutionVenueTelemetry {
  userStreamStatus: string;
  lastUserStreamEvent: string | null;
  subscribedChannels: string[];
  lifecycleStatus: string;
  lifecycleUpgradeEligible: boolean | null;
  lifecycleGapReasons: string[];
  lastLifecycleReason: string | null;
  reconciliationStatus: string | null;
  executionPlanStyle: string | null;
  fillProbability: number | null;
  ts: string;
  evidence: string[];
}

export interface ExecutionState {
  runId: string;
  summary: ExecutionSummaryMetric[];
  orders: ExecutionOrder[];
  positions: ExecutionPosition[];
  accountSnapshot: ExecutionAccountSnapshot | null;
  venueTelemetry: ExecutionVenueTelemetry | null;
  alphaTelemetry?: {
    privateStreamHealth?: Record<string, unknown>;
    orderRejectTaxonomy?: Record<string, unknown>;
    makerFirstEffectiveness?: Record<string, unknown>;
    executionQualityBucket?: Record<string, unknown>;
    entryTimingOptimizer?: Record<string, unknown>;
    adaptiveCadence?: Record<string, unknown>;
    liveDegradation?: Record<string, unknown>;
    selfThrottling?: Record<string, unknown>;
  };
  timeline: ReplayLineItem[];
  dataNotes: string[];
  linkedArtifacts: string[];
  stateKind: RuntimeStateKind;
  lastUpdatedAt: string;
  runtimeIdentity?: RuntimeIdentity;
}

export interface RuntimeListResponse<T> {
  items: T[];
  stateKind: RuntimeStateKind | string;
  lastUpdatedAt: string;
  reasonCode?: string;
  reasonText?: string;
  runtimeIdentity?: RuntimeIdentity;
}

export type RuntimeControlAction = "pause" | "resume" | "freeze" | "flatten";

export interface RuntimeRunOption {
  runId: string;
  runPath: string;
  providerId: string;
  mode: string;
  stateKind: RuntimeStateKind | string;
  reasonCode?: string;
  startedAt?: string | null;
  lastArtifactUpdateAt?: string | null;
  artifactFreshnessStatus?: "fresh" | "stale" | "unavailable";
  equity?: number | null;
  current: boolean;
  latest: boolean;
}

export interface RuntimeRunCatalog {
  items: RuntimeRunOption[];
  selectionMode: "pinned" | "latest";
  selectionTarget: string;
  resolvedRunId: string | null;
  resolvedRunPath: string | null;
  latestRunId: string | null;
  latestRunPath: string | null;
  unresolvedSelection: boolean;
  runtimeIdentity?: RuntimeIdentity | null;
  lastUpdatedAt: string;
}

export interface RuntimeRunSelectionRequest {
  mode: "pinned" | "latest";
  runId?: string;
  runPath?: string;
}

export interface RuntimeRunSelectionResponse {
  accepted: boolean;
  selectionMode: "pinned" | "latest";
  selectionTarget: string;
  runId: string | null;
  runPath: string | null;
  runtimeIdentity: RuntimeIdentity;
  operatorMessage: string;
  ts: string;
}

export interface RuntimeControlRequest {
  reasonCode?: string;
  reasonText?: string;
}

export interface RuntimeControlResponse {
  accepted: boolean;
  rejected: boolean;
  status: string;
  reasonCode?: string;
  operatorMessage: string;
  auditReference?: string;
  effectiveState: string;
  operatorId?: string;
  ts: string;
}

export interface IncidentNoteInput {
  runId: string;
  operatorId: string;
  note: string;
  severity?: string;
  tags?: string[];
}

export interface IncidentNoteResponse {
  accepted: boolean;
  noteId?: string;
  auditReference?: string;
  operatorMessage: string;
  ts: string;
}

export type RuntimeDataSource = "runtime-api" | "mock";

export interface RuntimeEnvelope<T> {
  data: T;
  source: RuntimeDataSource;
  configured: boolean;
}
