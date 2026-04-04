"use client";

import {
  getRuntimeAuthSnapshot,
  useRuntimeAuthStore,
} from "@/lib/auth/runtime-auth";
import { buildControlsContract } from "@/lib/contracts/build-controls-contract";
import { buildDashboardContract } from "@/lib/contracts/build-dashboard-contract";
import { buildReplayContract } from "@/lib/contracts/build-replay-contract";
import { buildRuntimeIdentityContract } from "@/lib/contracts/build-runtime-identity-contract";
import { buildUiInferenceContract } from "@/lib/contracts/build-ui-inference-contract";
import { resolveReplayRunId } from "@/lib/contracts/replay-run-id";
import { getPublicMacosReleaseReadiness } from "@/lib/release/macos-release";
import { runbookCatalog } from "@/lib/runbook/catalog";
import {
  useIncidentNoteWriter,
  useRuntimeAlerts,
  useRuntimeBrain,
  useRuntimeControls,
  useRuntimeDecisions,
  useRuntimeExecution,
  useRuntimeHealth,
  useRuntimeIntegrity,
  useRuntimeReplay,
  useRuntimeRunSelection,
  useRuntimeRuns,
  useRuntimeShield,
  useRuntimeSummary,
  useRuntimeSymbols,
} from "@/lib/runtime/use-runtime-queries";
import {
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
  buildUnavailableAlerts,
  buildUnavailableBrain,
  buildUnavailableDecisions,
  buildUnavailableExecution,
  buildUnavailableHealth,
  buildUnavailableIntegrity,
  buildUnavailableReplay,
  buildUnavailableShield,
  buildUnavailableSummary,
  buildUnavailableSymbols,
} from "@/lib/runtime/unavailable-data";
import type { IncidentNoteInput, RuntimeControlAction } from "@/types/runtime";

export function useScreenContracts() {
  const summaryQuery = useRuntimeSummary();
  const runsQuery = useRuntimeRuns();
  const symbolsQuery = useRuntimeSymbols();
  const decisionsQuery = useRuntimeDecisions();
  const alertsQuery = useRuntimeAlerts();
  const healthQuery = useRuntimeHealth();
  const integrityQuery = useRuntimeIntegrity();
  const brainQuery = useRuntimeBrain();
  const shieldQuery = useRuntimeShield();
  const executionQuery = useRuntimeExecution();
  const runtimeControls = useRuntimeControls();
  const runSelection = useRuntimeRunSelection();
  const incidentWriter = useIncidentNoteWriter();

  const authStore = useRuntimeAuthStore();
  const auth = getRuntimeAuthSnapshot();
  const useMockFallback = summaryQuery.source === "mock";
  const sharedUnavailableReason = errorsFromQueries(
    summaryQuery.error,
    runsQuery.error,
    symbolsQuery.error,
    decisionsQuery.error,
    alertsQuery.error,
    healthQuery.error,
    integrityQuery.error,
    brainQuery.error,
    shieldQuery.error,
    executionQuery.error,
  );

  const summary = summaryQuery.data ?? (useMockFallback ? mockRuntimeSummary : buildUnavailableSummary(sharedUnavailableReason));
  const symbols = symbolsQuery.data ?? (useMockFallback
    ? {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      }
    : buildUnavailableSymbols(sharedUnavailableReason));
  const decisions = decisionsQuery.data ?? (useMockFallback
    ? {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      }
    : buildUnavailableDecisions(sharedUnavailableReason));
  const alerts = alertsQuery.data ?? (useMockFallback
    ? {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      }
    : buildUnavailableAlerts(sharedUnavailableReason));
  const health = healthQuery.data ?? (useMockFallback ? mockHealth : buildUnavailableHealth(sharedUnavailableReason));
  const integrity = integrityQuery.data ?? (useMockFallback ? mockIntegrity : buildUnavailableIntegrity(sharedUnavailableReason));
  const brain = brainQuery.data ?? (useMockFallback ? mockBrain : buildUnavailableBrain(sharedUnavailableReason));
  const shield = shieldQuery.data ?? (useMockFallback ? mockShield : buildUnavailableShield(sharedUnavailableReason));
  const execution = executionQuery.data ?? (useMockFallback ? mockExecution : buildUnavailableExecution(sharedUnavailableReason));

  const replayRunId = resolveReplayRunId(summaryQuery.source, summaryQuery.data?.runId);
  const replayQuery = useRuntimeReplay(replayRunId);
  const replay = replayQuery.data ?? (useMockFallback
    ? mockReplay
    : buildUnavailableReplay(replayQuery.error ?? sharedUnavailableReason));

  const dashboardContract = buildDashboardContract({
    summary,
    health,
    integrity,
    symbols,
    decisions,
    alerts,
    auth,
    source: summaryQuery.source,
  });
  const runtimeIdentityContract = buildRuntimeIdentityContract({
    summary,
    health,
    integrity,
    symbols,
    decisions,
    alerts,
    replay,
  });

  const contract = {
    dashboard: dashboardContract,
    runtimeIdentity: runtimeIdentityContract,
    uiInference: buildUiInferenceContract({
      dashboard: dashboardContract,
      runtimeIdentity: runtimeIdentityContract,
      brain,
      shield,
      execution,
    }),
    controls: buildControlsContract({
      auth,
      health,
      integrity,
      lastResponse: runtimeControls.lastResponse,
    }),
    replay: buildReplayContract(replay, alerts.items),
    brain,
    shield,
    execution,
    runbook: runbookCatalog,
    release: getPublicMacosReleaseReadiness(),
  };

  const errors = [
    summaryQuery.error,
    runsQuery.error,
    symbolsQuery.error,
    decisionsQuery.error,
    alertsQuery.error,
    healthQuery.error,
    integrityQuery.error,
    brainQuery.error,
    shieldQuery.error,
    executionQuery.error,
    replayQuery.error,
    runtimeControls.error,
    runSelection.error,
    incidentWriter.error,
  ].filter(Boolean) as string[];

  return {
    contract,
    errors,
    queries: {
      summary: summaryQuery,
      runs: runsQuery,
      symbols: symbolsQuery,
      decisions: decisionsQuery,
      alerts: alertsQuery,
      health: healthQuery,
      integrity: integrityQuery,
      brain: brainQuery,
      shield: shieldQuery,
      execution: executionQuery,
      replay: replayQuery,
    },
    actions: {
      setIdentity: authStore.setIdentity,
      clearIdentity: authStore.clearIdentity,
      selectRun: (payload: { mode: "pinned" | "latest"; runId?: string; runPath?: string }) =>
        runSelection.submit(payload),
      invokeControl: (action: RuntimeControlAction, reasonText: string) =>
        runtimeControls.invoke(action, {
          reasonCode: `operator_${action}`,
          reasonText,
        }),
      submitIncidentNote: (payload: IncidentNoteInput) => incidentWriter.submit(payload),
    },
    runtimeControls,
    runSelection,
    incidentWriter,
  };
}

function errorsFromQueries(...values: Array<string | null>): string | undefined {
  const first = values.find(Boolean);
  return first ?? undefined;
}
