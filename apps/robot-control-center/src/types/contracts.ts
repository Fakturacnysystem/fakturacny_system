import type {
  AlertRecord,
  BrainState,
  DecisionRecord,
  ExecutionState,
  HealthDetail,
  ReplayLineItem,
  RuntimeControlAction,
  RuntimeControlResponse,
  RuntimeDataSource,
  ShieldState,
  SymbolSnapshot,
} from "@/types/runtime";

export interface ContractBadge {
  label: string;
  value: string;
  tone: "good" | "warn" | "danger" | "info";
}

export interface MetricCard {
  label: string;
  value: string;
  hint: string;
  tone: "good" | "warn" | "danger" | "info";
}

export interface DashboardContract {
  title: string;
  subtitle: string;
  source: RuntimeDataSource;
  runId: string;
  mode: string;
  lastUpdatedAt: string;
  runtimeIdentity: {
    runId: string;
    selectionMode: "pinned" | "latest";
    resolutionSource: string;
    runPath: string;
    providerId: string;
    mode: string;
    stateKind: string;
    reasonCode: string;
    driftStatus: string;
    pinIntegrityStatus: string;
    freshnessStatus: string;
    freshnessAgeLabel: string;
    lastArtifactUpdateAt: string;
    schemaVersion: string;
  };
  healthState: {
    status: string;
    bridgeHealthy: boolean;
    backendHealthy: boolean;
    artifactFallbackActive: boolean;
  };
  integrityState: {
    doctrineStatus: string;
    capabilityConfidence: string;
    degradationState: string;
    unlockActions: string[];
    stateKind: string;
  };
  badges: ContractBadge[];
  metrics: MetricCard[];
  warnings: string[];
  blockers: string[];
  authSummary: {
    status: string;
    operatorLabel: string;
    role: string;
    sessionId: string;
    authSource: string;
  };
  healthDetails: HealthDetail[];
  integrityDetails: HealthDetail[];
  symbols: SymbolSnapshot[];
  decisions: DecisionRecord[];
  alerts: AlertRecord[];
}

export interface RuntimeIdentityContract {
  runId: string;
  selectionMode: "pinned" | "latest";
  resolutionSource: string;
  runPath: string;
  providerId: string;
  mode: string;
  stateKind: string;
  reasonCode: string;
  driftStatus: string;
  pinIntegrityStatus: string;
  freshnessStatus: string;
  freshnessAgeLabel: string;
  lastArtifactUpdateAt: string;
  schemaVersion: string;
  endpointConsistencyStatus: "consistent" | "partial" | "mismatch";
  replayAlignmentStatus: "aligned" | "partial" | "mismatch";
  issues: string[];
}

export interface UiInferenceSurfaceContract {
  id: "command" | "brain" | "shield" | "execution";
  label: string;
  status: "contained" | "watch" | "breach";
  directEvidenceCount: number;
  derivedFieldCount: number;
  unavailableFieldCount: number;
  linkedArtifactCount: number;
  notes: string[];
}

export interface UiInferenceRuleContract {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface UiInferenceContract {
  status: "contained" | "watch" | "breach";
  source: RuntimeDataSource;
  derivedFieldCount: number;
  unavailableFieldCount: number;
  linkedArtifactCount: number;
  surfaces: UiInferenceSurfaceContract[];
  rules: UiInferenceRuleContract[];
  notes: string[];
}

export interface ControlButtonContract {
  action: RuntimeControlAction;
  label: string;
  enabled: boolean;
  tone: "good" | "warn" | "danger" | "info";
  disabledReason?: string;
}

export interface ControlsContract {
  statusLine: string;
  provenanceLine: string;
  canWriteIncidentNotes: boolean;
  actions: ControlButtonContract[];
  lastResponse?: RuntimeControlResponse | null;
}

export interface ReplayContract {
  runId: string;
  stateKind: string;
  lastUpdatedAt: string;
  summary: ContractBadge[];
  timeline: ReplayLineItem[];
  incidents: ReplayLineItem[];
  analogMatches: ReplayLineItem[];
  counterfactuals: ReplayLineItem[];
  pnlAttribution: ReplayLineItem[];
  notes: ReplayLineItem[];
}

export interface RunbookProcedure {
  title: string;
  whenToUse: string[];
  steps: string[];
}

export interface RunbookSeverity {
  severity: string;
  examples: string[];
}

export interface RunbookContract {
  severities: RunbookSeverity[];
  procedures: RunbookProcedure[];
  replayChecklist: string[];
}

export interface ReleaseChecklistItem {
  label: string;
  satisfied: boolean;
  detail: string;
}

export interface ReleaseContract {
  status: "ready" | "blocked";
  bundleId: string;
  checklist: ReleaseChecklistItem[];
  missingInputs: string[];
  exactCommands: string[];
}

export interface RobotControlCenterContract {
  dashboard: DashboardContract;
  runtimeIdentity: RuntimeIdentityContract;
  uiInference: UiInferenceContract;
  controls: ControlsContract;
  replay: ReplayContract;
  brain: BrainState;
  shield: ShieldState;
  execution: ExecutionState;
  runbook: RunbookContract;
  release: ReleaseContract;
}
