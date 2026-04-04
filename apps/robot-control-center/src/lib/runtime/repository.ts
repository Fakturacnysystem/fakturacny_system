import {
  getRuntimeAuthSnapshot,
  type RuntimeAuthSnapshot,
} from "@/lib/auth/runtime-auth";
import {
  buildMockControlResponse,
  buildMockIncidentResponse,
  mockAlerts,
  mockBrain,
  mockDecisions,
  mockExecution,
  mockHealth,
  mockIntegrity,
  mockReplay,
  mockRuntimeSummary,
  mockShield,
  mockSymbols,
} from "@/lib/runtime/mock-data";
import {
  RuntimeApiRequestError,
  runtimeApi,
  runtimeApiAvailable,
  type RuntimeApiListResponse,
  type RuntimeApiSummary,
} from "@/lib/runtime/api";
import {
  buildUnavailableAlerts,
  buildUnavailableBrain,
  buildUnavailableDecisions,
  buildUnavailableExecution,
  buildUnavailableHealth,
  buildUnavailableIntegrity,
  buildUnavailableReplay,
  buildUnavailableRuns,
  buildUnavailableShield,
  buildUnavailableSummary,
  buildUnavailableSymbols,
} from "@/lib/runtime/unavailable-data";
import type {
  AlertRecord,
  BrainState,
  DecisionRecord,
  ExecutionState,
  HealthState,
  IncidentNoteInput,
  IncidentNoteResponse,
  IntegrityState,
  ReplayForensicsState,
  RuntimeControlAction,
  RuntimeControlRequest,
  RuntimeControlResponse,
  RuntimeEnvelope,
  RuntimeListResponse,
  RuntimeRunCatalog,
  RuntimeRunSelectionRequest,
  RuntimeRunSelectionResponse,
  RuntimeSummary,
  ShieldState,
  SymbolSnapshot,
} from "@/types/runtime";

export interface RuntimeRepository {
  readonly source: "runtime-api" | "mock";
  readonly configured: boolean;
  getSummary(): Promise<RuntimeEnvelope<RuntimeSummary>>;
  getRuns(): Promise<RuntimeEnvelope<RuntimeRunCatalog>>;
  getSymbols(): Promise<RuntimeEnvelope<RuntimeListResponse<SymbolSnapshot>>>;
  getDecisions(): Promise<RuntimeEnvelope<RuntimeListResponse<DecisionRecord>>>;
  getAlerts(): Promise<RuntimeEnvelope<RuntimeListResponse<AlertRecord>>>;
  getHealth(): Promise<RuntimeEnvelope<HealthState>>;
  getIntegrity(): Promise<RuntimeEnvelope<IntegrityState>>;
  getBrain(): Promise<RuntimeEnvelope<BrainState>>;
  getShield(): Promise<RuntimeEnvelope<ShieldState>>;
  getExecution(): Promise<RuntimeEnvelope<ExecutionState>>;
  getReplay(runId: string): Promise<RuntimeEnvelope<ReplayForensicsState>>;
  selectRun(payload: RuntimeRunSelectionRequest): Promise<RuntimeRunSelectionResponse>;
  control(
    action: RuntimeControlAction,
    payload: RuntimeControlRequest,
    auth: RuntimeAuthSnapshot,
  ): Promise<RuntimeControlResponse>;
  writeIncidentNote(
    payload: IncidentNoteInput,
    auth: RuntimeAuthSnapshot,
  ): Promise<IncidentNoteResponse>;
}

function wrap<T>(data: T, source: "runtime-api" | "mock", configured: boolean): RuntimeEnvelope<T> {
  return {
    data,
    source,
    configured,
  };
}

function mapSummary(raw: RuntimeApiSummary): RuntimeSummary {
  return {
    providerId: raw.providerId,
    mode: raw.mode,
    runId: raw.runId,
    runSelection: raw.runSelection,
    runtimeIdentity: raw.runtimeIdentity,
    startedAt: raw.startedAt,
    uptimeSec: raw.uptimeSec,
    portfolio: {
      equityEur: raw.equityEur,
      freeCashEur: raw.freeCashEur,
      openPositions: raw.openPositions,
      openOrders: raw.openOrders,
    },
    bridge: {
      avgLatencyMs: raw.avgLatencyMs,
      wsConnected: raw.wsConnected,
      restHealthy: raw.restHealthy,
      health_status: raw.stateKind,
      reasonCode: raw.reasonCode,
      reasonText: raw.reasonText,
      lastUpdatedAt: raw.lastUpdatedAt,
    },
    performance: raw.performance,
  };
}

function mapList<T>(raw: RuntimeApiListResponse<T>): RuntimeListResponse<T> {
  return {
    items: raw.items,
    stateKind: raw.stateKind,
    lastUpdatedAt: raw.lastUpdatedAt,
    reasonCode: raw.reasonCode,
    reasonText: raw.reasonText,
    runtimeIdentity: raw.runtimeIdentity,
  };
}

function rejectUnauthorized(action: string): RuntimeControlResponse {
  return {
    accepted: false,
    rejected: true,
    status: "rejected",
    reasonCode: "operator_identity_required",
    operatorMessage: `Cannot ${action} without an authenticated operator session.`,
    effectiveState: "unchanged",
    ts: new Date().toISOString(),
  };
}

function rejectIncidentNote(): IncidentNoteResponse {
  return {
    accepted: false,
    operatorMessage: "Incident note blocked because operator identity is missing or expired.",
    ts: new Date().toISOString(),
  };
}

class MockRuntimeRepository implements RuntimeRepository {
  readonly source = "mock";
  readonly configured = false;

  async getSummary() {
    return wrap(mockRuntimeSummary, this.source, this.configured);
  }

  async getRuns() {
    return wrap(
      {
        items: [
          {
            runId: mockRuntimeSummary.runId,
            runPath: mockRuntimeSummary.runtimeIdentity.runPath,
            providerId: mockRuntimeSummary.providerId,
            mode: mockRuntimeSummary.mode,
            stateKind: mockRuntimeSummary.runtimeIdentity.stateKind,
            reasonCode: mockRuntimeSummary.runtimeIdentity.reasonCode,
            startedAt: mockRuntimeSummary.startedAt,
            lastArtifactUpdateAt: mockRuntimeSummary.runtimeIdentity.lastArtifactUpdateAt ?? mockRuntimeSummary.bridge.lastUpdatedAt,
            artifactFreshnessStatus: mockRuntimeSummary.runtimeIdentity.artifactFreshness.status,
            equity: mockRuntimeSummary.portfolio.equityEur,
            current: true,
            latest: true,
          },
        ],
        selectionMode: mockRuntimeSummary.runtimeIdentity.runSelectionMode,
        selectionTarget: mockRuntimeSummary.runSelection.target,
        resolvedRunId: mockRuntimeSummary.runId,
        resolvedRunPath: mockRuntimeSummary.runtimeIdentity.runPath,
        latestRunId: mockRuntimeSummary.runId,
        latestRunPath: mockRuntimeSummary.runtimeIdentity.runPath,
        unresolvedSelection: false,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
        lastUpdatedAt: mockRuntimeSummary.bridge.lastUpdatedAt,
      },
      this.source,
      this.configured,
    );
  }

  async getSymbols() {
    return wrap(
      {
        items: mockSymbols,
        stateKind: mockRuntimeSummary.bridge.health_status,
        lastUpdatedAt: mockRuntimeSummary.bridge.lastUpdatedAt,
        reasonCode: mockRuntimeSummary.bridge.reasonCode,
        reasonText: mockRuntimeSummary.bridge.reasonText,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      this.source,
      this.configured,
    );
  }

  async getDecisions() {
    return wrap(
      {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      this.source,
      this.configured,
    );
  }

  async getAlerts() {
    return wrap(
      {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      this.source,
      this.configured,
    );
  }

  async getHealth() {
    return wrap(mockHealth, this.source, this.configured);
  }

  async getIntegrity() {
    return wrap(mockIntegrity, this.source, this.configured);
  }

  async getBrain() {
    return wrap(mockBrain, this.source, this.configured);
  }

  async getShield() {
    return wrap(mockShield, this.source, this.configured);
  }

  async getExecution() {
    return wrap(mockExecution, this.source, this.configured);
  }

  async getReplay() {
    return wrap(mockReplay, this.source, this.configured);
  }

  async selectRun(payload: RuntimeRunSelectionRequest) {
    const runId = payload.mode === "latest" ? mockRuntimeSummary.runId : (payload.runId ?? mockRuntimeSummary.runId);
    const response: RuntimeRunSelectionResponse = {
      accepted: true,
      selectionMode: payload.mode,
      selectionTarget: payload.mode === "latest" ? "runs/latest" : `runs/${runId}`,
      runId,
      runPath: payload.mode === "latest" ? mockRuntimeSummary.runtimeIdentity.runPath : `/mock/runs/${runId}`,
      runtimeIdentity: {
        ...mockRuntimeSummary.runtimeIdentity,
        runId,
        runSelectionMode: payload.mode,
        driftStatus: payload.mode === "latest" ? "tracking_latest" : "locked",
        pinIntegrityStatus: payload.mode === "latest" ? "not_pinned" : "ok",
      },
      operatorMessage: payload.mode === "latest" ? "Mock runtime is tracking latest." : `Mock runtime pinned to ${runId}.`,
      ts: new Date().toISOString(),
    };
    return response;
  }

  async control(
    action: RuntimeControlAction,
    _payload: RuntimeControlRequest,
    auth: RuntimeAuthSnapshot,
  ) {
    if (!auth.operatorId || auth.status !== "active") {
      return rejectUnauthorized(action);
    }
    return buildMockControlResponse(action, auth.operatorId);
  }

  async writeIncidentNote(payload: IncidentNoteInput, auth: RuntimeAuthSnapshot) {
    if (!auth.operatorId || auth.status !== "active") {
      return rejectIncidentNote();
    }
    return buildMockIncidentResponse(payload);
  }
}

class HttpRuntimeRepository implements RuntimeRepository {
  readonly source = "runtime-api";
  readonly configured = true;

  async getSummary() {
    try {
      return wrap(mapSummary(await runtimeApi.summary()), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableSummary(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getRuns() {
    try {
      return wrap(await runtimeApi.runs(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableRuns(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getSymbols() {
    try {
      return wrap(mapList(await runtimeApi.symbols()), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableSymbols(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getDecisions() {
    try {
      return wrap(mapList(await runtimeApi.decisions()), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableDecisions(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getAlerts() {
    try {
      return wrap(mapList(await runtimeApi.alerts()), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableAlerts(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getHealth() {
    try {
      return wrap(await runtimeApi.health(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableHealth(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getIntegrity() {
    try {
      return wrap(await runtimeApi.integrity(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableIntegrity(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getBrain() {
    try {
      return wrap(await runtimeApi.brain(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableBrain(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getShield() {
    try {
      return wrap(await runtimeApi.shield(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableShield(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getExecution() {
    try {
      return wrap(await runtimeApi.execution(), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableExecution(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async getReplay(runId: string) {
    try {
      return wrap(await runtimeApi.replay(runId), this.source, this.configured);
    } catch (error) {
      const unresolved = unresolvedIdentityFromError(error);
      if (unresolved) {
        return wrap(buildUnavailableReplay(unresolved.detail, unresolved.identity), this.source, this.configured);
      }
      throw error;
    }
  }

  async selectRun(payload: RuntimeRunSelectionRequest) {
    return runtimeApi.selectRun(payload);
  }

  async control(
    action: RuntimeControlAction,
    payload: RuntimeControlRequest,
    auth: RuntimeAuthSnapshot,
  ) {
    if (!auth.operatorId || auth.status !== "active") {
      return rejectUnauthorized(action);
    }
    return runtimeApi.control(action, payload);
  }

  async writeIncidentNote(payload: IncidentNoteInput, auth: RuntimeAuthSnapshot) {
    if (!auth.operatorId || auth.status !== "active") {
      return rejectIncidentNote();
    }
    return runtimeApi.writeIncidentNote(payload);
  }
}

const runtimeRepository: RuntimeRepository = runtimeApiAvailable()
  ? new HttpRuntimeRepository()
  : new MockRuntimeRepository();

export function getRuntimeRepository(): RuntimeRepository {
  return runtimeRepository;
}

export function getRuntimeRepositoryProvenance() {
  return {
    source: runtimeRepository.source,
    configured: runtimeRepository.configured,
    auth: getRuntimeAuthSnapshot(),
  };
}

function unresolvedIdentityFromError(error: unknown): { detail: string; identity?: RuntimeSummary["runtimeIdentity"] } | null {
  if (!(error instanceof RuntimeApiRequestError)) {
    return null;
  }
  const payload = error.payload;
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const maybePayload = payload as {
    error?: unknown;
    detail?: unknown;
    runtimeIdentity?: RuntimeSummary["runtimeIdentity"];
  };
  if (maybePayload.error !== "run_not_found") {
    return null;
  }
  return {
    detail: String(maybePayload.detail ?? error.message),
    identity: maybePayload.runtimeIdentity,
  };
}
