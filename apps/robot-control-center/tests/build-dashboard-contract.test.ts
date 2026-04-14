import { describe, expect, it } from "vitest";
import { buildDashboardContract } from "@/lib/contracts/build-dashboard-contract";
import {
  mockAlerts,
  mockDecisions,
  mockHealth,
  mockIntegrity,
  mockRuntimeSummary,
  mockSymbols,
} from "@/lib/runtime/mock-data";
import {
  buildUnavailableHealth,
  buildUnavailableIntegrity,
  buildUnavailableSummary,
} from "@/lib/runtime/unavailable-data";

describe("buildDashboardContract", () => {
  it("surfaces mock source, blockers and operator provenance explicitly", () => {
    const contract = buildDashboardContract({
      summary: mockRuntimeSummary,
      health: mockHealth,
      integrity: mockIntegrity,
      symbols: {
        items: mockSymbols,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      },
      decisions: {
        items: mockDecisions,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      },
      alerts: {
        items: mockAlerts,
        stateKind: mockIntegrity.stateKind,
        lastUpdatedAt: mockIntegrity.lastUpdatedAt,
      },
      auth: {
        operatorId: "ops.mh",
        displayName: "Martin Holik",
        role: "operator",
        authSource: "local",
        sessionId: "session-01",
        expiresAt: null,
        status: "active",
        providerStatus: "ready",
        lastError: null,
      },
      source: "mock",
    });

    expect(contract.source).toBe("mock");
    expect(contract.blockers).toContain("runtime_api_missing");
    expect(contract.authSummary.operatorLabel).toBe("Martin Holik");
    expect(contract.metrics[0]?.value).toContain("€");
    expect(contract.runtimeIdentity.selectionMode).toBe("latest");
    expect(contract.runtimeIdentity.driftStatus).toBe("tracking_latest");
  });

  it("keeps runtime bootstrap explicit instead of showing synthetic zero-state as truth", () => {
    const contract = buildDashboardContract({
      summary: buildUnavailableSummary(),
      health: buildUnavailableHealth(),
      integrity: buildUnavailableIntegrity(),
      symbols: {
        items: [],
        stateKind: "unavailable",
        lastUpdatedAt: "1970-01-01T00:00:00.000Z",
      },
      decisions: {
        items: [],
        stateKind: "unavailable",
        lastUpdatedAt: "1970-01-01T00:00:00.000Z",
      },
      alerts: {
        items: [],
        stateKind: "unavailable",
        lastUpdatedAt: "1970-01-01T00:00:00.000Z",
      },
      auth: {
        operatorId: "",
        displayName: "",
        role: "observer",
        authSource: "local",
        sessionId: "session-bootstrap",
        expiresAt: null,
        status: "anonymous",
        providerStatus: "ready",
        lastError: null,
      },
      source: "runtime-api",
    });

    expect(contract.runId).toBe("čaká-sa-na-spoľahlivé-údaje");
    expect(contract.lastUpdatedAt).toBe("");
    expect(contract.metrics[0]?.value).toBe("Čaká sa");
    expect(contract.metrics[2]?.value).toBe("Čaká sa");
    expect(contract.runtimeIdentity.pinIntegrityStatus).toBe("unresolved");
  });
});
