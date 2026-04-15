import { describe, expect, it } from "vitest";
import { buildRuntimeIdentityContract } from "@/lib/contracts/build-runtime-identity-contract";
import {
  mockAlerts,
  mockDecisions,
  mockHealth,
  mockIntegrity,
  mockReplay,
  mockRuntimeSummary,
  mockSymbols,
} from "@/lib/runtime/mock-data";
import {
  buildUnavailableAlerts,
  buildUnavailableDecisions,
  buildUnavailableHealth,
  buildUnavailableIntegrity,
  buildUnavailableReplay,
  buildUnavailableSummary,
  buildUnavailableSymbols,
} from "@/lib/runtime/unavailable-data";

describe("buildRuntimeIdentityContract", () => {
  it("keeps consistent runtime identity aligned across summary, lists, health, integrity, and replay", () => {
    const contract = buildRuntimeIdentityContract({
      summary: mockRuntimeSummary,
      health: mockHealth,
      integrity: mockIntegrity,
      symbols: {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      decisions: {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      alerts: {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      replay: {
        ...mockReplay,
        runId: mockRuntimeSummary.runId,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
    });

    expect(contract.endpointConsistencyStatus).toBe("consistent");
    expect(contract.replayAlignmentStatus).toBe("aligned");
    expect(contract.issues).toContain("runtime_tracking_latest");
  });

  it("surfaces unresolved pinned run truth instead of pretending latest is valid", () => {
    const summary = buildUnavailableSummary("Pinned run missing.");
    const pinnedIdentity = {
      ...summary.runtimeIdentity,
      runId: "target-live-run",
      runSelectionMode: "pinned" as const,
      runResolutionSource: "explicit_run_id" as const,
      runPath: "",
      providerId: "kraken_spot",
      mode: "live",
      driftStatus: "unresolved" as const,
      pinIntegrityStatus: "unresolved" as const,
      reasonCode: "run_not_found",
    };
    const pinnedSummary = {
      ...summary,
      runId: "target-live-run",
      runSelection: {
        mode: "pinned" as const,
        target: "runs/target-live-run",
        resolvedRunDir: "",
      },
      runtimeIdentity: pinnedIdentity,
    };

    const contract = buildRuntimeIdentityContract({
      summary: pinnedSummary,
      health: { ...buildUnavailableHealth("Pinned run missing."), runtimeIdentity: pinnedIdentity },
      integrity: { ...buildUnavailableIntegrity("Pinned run missing."), runtimeIdentity: pinnedIdentity },
      symbols: { ...buildUnavailableSymbols("Pinned run missing."), runtimeIdentity: pinnedIdentity },
      decisions: { ...buildUnavailableDecisions("Pinned run missing."), runtimeIdentity: pinnedIdentity },
      alerts: { ...buildUnavailableAlerts("Pinned run missing."), runtimeIdentity: pinnedIdentity },
      replay: { ...buildUnavailableReplay("Pinned run missing."), runId: "target-live-run", runtimeIdentity: pinnedIdentity },
    });

    expect(contract.selectionMode).toBe("pinned");
    expect(contract.pinIntegrityStatus).toBe("unresolved");
    expect(contract.driftStatus).toBe("unresolved");
    expect(contract.endpointConsistencyStatus).toBe("consistent");
    expect(contract.issues).toContain("pin_integrity:unresolved");
    expect(contract.issues).toContain("runtime_drift:unresolved");
  });

  it("flags replay mismatch loudly when replay evidence points at a different run", () => {
    const contract = buildRuntimeIdentityContract({
      summary: mockRuntimeSummary,
      health: mockHealth,
      integrity: mockIntegrity,
      symbols: {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      decisions: {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      alerts: {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
        runtimeIdentity: mockRuntimeSummary.runtimeIdentity,
      },
      replay: {
        ...mockReplay,
        runId: "another-run",
        runtimeIdentity: {
          ...mockRuntimeSummary.runtimeIdentity,
          runId: "another-run",
          runPath: "/mock/runs/another-run",
        },
      },
    });

    expect(contract.endpointConsistencyStatus).toBe("mismatch");
    expect(contract.replayAlignmentStatus).toBe("mismatch");
    expect(contract.issues).toContain("runtime_identity_mismatch:replay");
    expect(contract.issues).toContain("replay_run_mismatch:another-run");
  });
});
