import { describe, expect, it } from "vitest";
import { buildDashboardContract } from "@/lib/contracts/build-dashboard-contract";
import { buildRuntimeIdentityContract } from "@/lib/contracts/build-runtime-identity-contract";
import { buildUiInferenceContract } from "@/lib/contracts/build-ui-inference-contract";
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
import type { RuntimeAuthSnapshot, RuntimeAuthStatus } from "@/lib/auth/runtime-auth";

function auth(status: RuntimeAuthStatus = "active"): RuntimeAuthSnapshot {
  return {
    operatorId: status === "active" ? "ops.mh" : "",
    displayName: status === "active" ? "Martin Holik" : "",
    role: status === "active" ? "operator" : "observer",
    authSource: "local",
    sessionId: status === "active" ? "session-1" : "",
    expiresAt: null,
    status,
    providerStatus: "ready",
    lastError: null,
  };
}

describe("buildUiInferenceContract", () => {
  it("flags explicit mock mode as a breach instead of hiding it behind a healthy-looking surface", () => {
    const dashboard = buildDashboardContract({
      summary: mockRuntimeSummary,
      health: mockHealth,
      integrity: mockIntegrity,
      symbols: {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      decisions: {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      alerts: {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      auth: auth(),
      source: "mock",
    });
    const runtimeIdentity = buildRuntimeIdentityContract({
      summary: mockRuntimeSummary,
      health: mockHealth,
      integrity: mockIntegrity,
      symbols: {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      decisions: {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      alerts: {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockIntegrity.runtimeIdentity,
      },
      replay: mockReplay,
    });

    const oversight = buildUiInferenceContract({
      dashboard,
      runtimeIdentity,
      brain: mockBrain,
      shield: mockShield,
      execution: mockExecution,
    });

    expect(oversight.status).toBe("breach");
    expect(oversight.rules.find((rule) => rule.label === "Runtime source explicit")?.status).toBe("fail");
    expect(oversight.derivedFieldCount).toBeGreaterThan(0);
    expect(oversight.unavailableFieldCount).toBeGreaterThan(0);
    expect(oversight.surfaces.find((surface) => surface.id === "execution")?.derivedFieldCount).toBeGreaterThan(0);
  });

  it("treats unresolved pinned run selection as a breach with explicit run-lock failure", () => {
    const unresolvedIdentity = {
      ...mockRuntimeSummary.runtimeIdentity,
      runId: "missing-live-run",
      runSelectionMode: "pinned" as const,
      runResolutionSource: "explicit_run_id" as const,
      runPath: "",
      stateKind: "unresolved" as const,
      reasonCode: "run_not_found",
      driftStatus: "unresolved" as const,
      pinIntegrityStatus: "unresolved" as const,
      artifactFreshness: {
        ...mockRuntimeSummary.runtimeIdentity.artifactFreshness,
        status: "unavailable" as const,
        ageSeconds: 0,
        thresholdSeconds: 0,
      },
      lastArtifactUpdateAt: "1970-01-01T00:00:00.000Z",
    };

    const summary = buildUnavailableSummary("run_not_found", unresolvedIdentity);
    const health = buildUnavailableHealth("run_not_found", unresolvedIdentity);
    const integrity = buildUnavailableIntegrity("run_not_found", unresolvedIdentity);
    const symbols = buildUnavailableSymbols("run_not_found", unresolvedIdentity);
    const decisions = buildUnavailableDecisions("run_not_found", unresolvedIdentity);
    const alerts = buildUnavailableAlerts("run_not_found", unresolvedIdentity);
    const replay = buildUnavailableReplay("run_not_found", unresolvedIdentity);
    const dashboard = buildDashboardContract({
      summary,
      health,
      integrity,
      symbols,
      decisions,
      alerts,
      auth: auth("anonymous"),
      source: "runtime-api",
    });
    const runtimeIdentity = buildRuntimeIdentityContract({
      summary,
      health,
      integrity,
      symbols,
      decisions,
      alerts,
      replay,
    });

    const oversight = buildUiInferenceContract({
      dashboard,
      runtimeIdentity,
      brain: buildUnavailableBrain("run_not_found", unresolvedIdentity),
      shield: buildUnavailableShield("run_not_found", unresolvedIdentity),
      execution: buildUnavailableExecution("run_not_found", unresolvedIdentity),
    });

    expect(oversight.status).toBe("breach");
    expect(oversight.rules.find((rule) => rule.label === "Run identity lock")?.status).toBe("fail");
    expect(oversight.notes.some((note) => note.includes("Pinned run missing-live-run is unresolved"))).toBe(true);
  });
});
