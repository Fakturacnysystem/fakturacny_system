import type {
  AlertRecord,
  BrainState,
  DecisionRecord,
  ExecutionState,
  HealthState,
  IntegrityState,
  ReplayForensicsState,
  RuntimeListResponse,
  RuntimeRunCatalog,
  RuntimeIdentity,
  RuntimeSummary,
  ShieldState,
  SymbolSnapshot,
} from "@/types/runtime";

export const RUNTIME_UNAVAILABLE_TIMESTAMP = "1970-01-01T00:00:00.000Z";

function unresolvedIdentity(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeIdentity {
  if (identity) {
    return identity;
  }
  return {
    runId: "runtime-unavailable",
    runSelectionMode: "latest",
    runResolutionSource: "default_latest",
    runPath: "",
    providerId: "unavailable",
    mode: "runtime-api",
    stateKind: "unavailable",
    reasonCode: "runtime_api_unavailable",
    driftStatus: "unresolved",
    artifactFreshness: {
      status: "unavailable",
      ageSeconds: 0,
      thresholdSeconds: 0,
      lastArtifactUpdateAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    },
    startedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    lastArtifactUpdateAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    pinIntegrityStatus: "unresolved",
    schemaVersion: null,
  };
}

export function buildUnavailableSummary(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeSummary {
  const runtimeIdentity = unresolvedIdentity(reasonText, identity);
  return {
    providerId: "unavailable",
    mode: "runtime-api",
    runId: runtimeIdentity.runId,
    runSelection: {
      mode: runtimeIdentity.runSelectionMode,
      target: runtimeIdentity.runPath || "runs/latest",
      resolvedRunDir: runtimeIdentity.runPath,
    },
    runtimeIdentity,
    startedAt: runtimeIdentity.startedAt ?? RUNTIME_UNAVAILABLE_TIMESTAMP,
    uptimeSec: 0,
    portfolio: {
      equityEur: 0,
      freeCashEur: 0,
      openPositions: 0,
      openOrders: 0,
    },
    bridge: {
      avgLatencyMs: 0,
      wsConnected: false,
      restHealthy: false,
      health_status: runtimeIdentity.stateKind,
      reasonCode: runtimeIdentity.reasonCode ?? "runtime_api_unavailable",
      reasonText:
        reasonText ??
        "Runtime API is configured, but no authoritative payload has loaded yet. Mock fallback is intentionally disabled in this mode.",
      lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    },
  };
}

export function buildUnavailableList<T>(
  reasonText?: string,
  identity?: RuntimeIdentity | null,
): RuntimeListResponse<T> {
  return {
    items: [],
    stateKind: (identity?.stateKind ?? "unavailable"),
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    reasonCode: identity?.reasonCode ?? "runtime_api_unavailable",
    reasonText:
      reasonText ??
      "Runtime API is configured, but the resource has not produced an authoritative payload.",
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableHealth(reasonText?: string, identity?: RuntimeIdentity | null): HealthState {
  return {
    status: identity?.stateKind === "unresolved" ? "warn" : "danger",
    bridgeHealthy: false,
    backendHealthy: false,
    artifactFallbackActive: false,
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    warnings: [
      reasonText ??
        "Runtime API is configured, but health state is unavailable. RCC is refusing to silently substitute mock health.",
    ],
    details: [
      {
        label: "Runtime API",
        value: "unavailable",
        severity: "danger",
      },
    ],
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableIntegrity(reasonText?: string, identity?: RuntimeIdentity | null): IntegrityState {
  return {
    doctrineStatus: "unknown",
    capabilityConfidence: "unknown",
    blockers: [identity?.reasonCode ?? "runtime_api_unavailable"],
    unlockActions: ["restore authoritative runtime API connectivity"],
    warnings: [
      reasonText ??
        "Integrity payload unavailable; do not trust control surfaces until runtime API recovers.",
    ],
    degradationState: "runtime_api_unavailable",
    details: [
      {
        label: "Runtime API",
        value: "unavailable",
        severity: "danger",
      },
    ],
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    stateKind: identity?.stateKind ?? "unavailable",
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableReplay(reasonText?: string, identity?: RuntimeIdentity | null): ReplayForensicsState {
  return {
    runId: identity?.runId ?? "runtime-unavailable",
    timeline: [],
    incidents: [],
    analogMatches: [],
    counterfactuals: [],
    pnlAttribution: [],
    notes: [
      {
        label: "Runtime API",
        detail:
          reasonText ??
          "Replay payload unavailable; forensic review requires runtime API recovery.",
        ts: RUNTIME_UNAVAILABLE_TIMESTAMP,
        severity: "danger",
      },
    ],
    stateKind: identity?.stateKind ?? "unavailable",
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableBrain(reasonText?: string, identity?: RuntimeIdentity | null): BrainState {
  return {
    runId: identity?.runId ?? "runtime-unavailable",
    selectedSymbol: "unavailable",
    actionState: "unavailable",
    whyTrade: [],
    whyNotTrade: [
      reasonText ??
        "Brain evidence is unavailable; RCC refuses to invent decision logic when runtime artifacts are missing.",
    ],
    blockingReasons: [identity?.reasonCode ?? "runtime_api_unavailable"],
    supportingSignals: [],
    costAdjustedEdgeBps: null,
    costAdjustedEdgeSource: null,
    sellFloorStatus: "unavailable",
    marketRegime: "unavailable",
    riskGatingOutcome: "unavailable",
    executionEligibilityOutcome: "unavailable",
    pipeline: [],
    symbolViews: [],
    decisionReplay: {
      finalVerdict: "unavailable",
      timeline: [],
      evidence: [],
      linkedArtifacts: [],
    },
    evidenceNotes: [
      reasonText ??
        "Brain payload unavailable; no decision pipeline or explainability surface can be trusted.",
    ],
    stateKind: identity?.stateKind ?? "unavailable",
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableShield(reasonText?: string, identity?: RuntimeIdentity | null): ShieldState {
  return {
    runId: identity?.runId ?? "runtime-unavailable",
    trustVerdict: "unsafe",
    trustReasons: [identity?.reasonCode ?? "runtime_api_unavailable"],
    runtimeSafety: [
      {
        label: "Runtime API",
        status: "unsafe",
        detail: reasonText ?? "Shield payload unavailable.",
        evidence: [],
        ts: RUNTIME_UNAVAILABLE_TIMESTAMP,
      },
    ],
    appliedControl: null,
    queuedCommand: null,
    userStream: {
      status: "unavailable",
      detail: reasonText ?? "Shield payload unavailable.",
      subscribedChannels: [],
      lastEventType: null,
      lastEventAt: null,
      evidence: [],
    },
    guardMatrix: [],
    truthNotes: [
      reasonText ??
        "Shield payload unavailable; operator safety posture cannot be proven.",
    ],
    linkedArtifacts: [],
    stateKind: identity?.stateKind ?? "unavailable",
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableExecution(reasonText?: string, identity?: RuntimeIdentity | null): ExecutionState {
  return {
    runId: identity?.runId ?? "runtime-unavailable",
    summary: [],
    orders: [],
    positions: [],
    accountSnapshot: null,
    venueTelemetry: null,
    timeline: [],
    dataNotes: [
      reasonText ??
        "Execution payload unavailable; order, fill, and position telemetry cannot be trusted.",
    ],
    linkedArtifacts: [],
    stateKind: identity?.stateKind ?? "unavailable",
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
  };
}

export function buildUnavailableSymbols(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeListResponse<SymbolSnapshot> {
  return buildUnavailableList<SymbolSnapshot>(reasonText, identity);
}

export function buildUnavailableDecisions(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeListResponse<DecisionRecord> {
  return buildUnavailableList<DecisionRecord>(reasonText, identity);
}

export function buildUnavailableAlerts(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeListResponse<AlertRecord> {
  return buildUnavailableList<AlertRecord>(reasonText, identity);
}

export function buildUnavailableRuns(reasonText?: string, identity?: RuntimeIdentity | null): RuntimeRunCatalog {
  return {
    items: [],
    selectionMode: identity?.runSelectionMode ?? "latest",
    selectionTarget: identity?.runPath || "runs/latest",
    resolvedRunId: null,
    resolvedRunPath: null,
    latestRunId: null,
    latestRunPath: null,
    unresolvedSelection: identity?.stateKind === "unresolved",
    runtimeIdentity: unresolvedIdentity(reasonText, identity),
    lastUpdatedAt: RUNTIME_UNAVAILABLE_TIMESTAMP,
  };
}
