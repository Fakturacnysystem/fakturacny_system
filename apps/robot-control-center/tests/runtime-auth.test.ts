import { describe, expect, it } from "vitest";
import {
  buildAuthorizationHeader,
  deriveRuntimeAuthStatus,
  type RuntimeAuthSnapshot,
} from "@/lib/auth/runtime-auth";

function snapshot(overrides: Partial<RuntimeAuthSnapshot>): RuntimeAuthSnapshot {
  return {
    operatorId: "",
    displayName: "",
    role: "observer",
    authSource: "local",
    sessionId: "session-01",
    expiresAt: null,
    status: "anonymous",
    providerStatus: "ready",
    lastError: null,
    ...overrides,
  };
}

describe("runtime auth helpers", () => {
  it("marks expired sessions even if store status still says active", () => {
    const expired = snapshot({
      operatorId: "ops.mh",
      status: "active",
      expiresAt: "2020-01-01T00:00:00.000Z",
    });

    expect(deriveRuntimeAuthStatus(expired)).toBe("expired");
    expect(buildAuthorizationHeader(expired)).toBeNull();
  });

  it("builds operator header only for active sessions", () => {
    const active = snapshot({
      operatorId: "ops.mh",
      status: "active",
      expiresAt: "2099-01-01T00:00:00.000Z",
    });

    expect(buildAuthorizationHeader(active)).toBe("Operator ops.mh:session-01");
  });

  it("refuses to build an operator header without a session id", () => {
    const missingSession = snapshot({
      operatorId: "ops.mh",
      status: "active",
      sessionId: "",
      expiresAt: "2099-01-01T00:00:00.000Z",
    });

    expect(buildAuthorizationHeader(missingSession)).toBeNull();
  });
});
