import { describe, expect, it } from "vitest";
import { buildControlsContract } from "@/lib/contracts/build-controls-contract";
import { mockHealth, mockIntegrity } from "@/lib/runtime/mock-data";

describe("buildControlsContract", () => {
  it("blocks all destructive actions when operator session is missing", () => {
    const contract = buildControlsContract({
      auth: {
        operatorId: "",
        displayName: "",
        role: "observer",
        authSource: "local",
        sessionId: "session-01",
        expiresAt: null,
        status: "anonymous",
        providerStatus: "ready",
        lastError: null,
      },
      health: mockHealth,
      integrity: mockIntegrity,
      lastResponse: null,
    });

    expect(contract.actions.every((action) => !action.enabled)).toBe(true);
    expect(contract.canWriteIncidentNotes).toBe(false);
  });

  it("keeps resume blocked when integrity blockers remain", () => {
    const contract = buildControlsContract({
      auth: {
        operatorId: "ops.mh",
        displayName: "Martin Holik",
        role: "operator",
        authSource: "local",
        sessionId: "session-02",
        expiresAt: null,
        status: "active",
        providerStatus: "ready",
        lastError: null,
      },
      health: mockHealth,
      integrity: mockIntegrity,
      lastResponse: null,
    });

    const resume = contract.actions.find((action) => action.action === "resume");
    expect(resume?.enabled).toBe(false);
  });
});
