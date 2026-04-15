import { describe, expect, it } from "vitest";
import { evaluateMacosReleaseReadiness } from "@/lib/release/macos-release";

describe("evaluateMacosReleaseReadiness", () => {
  it("reports blocked state when Apple signing inputs are missing", () => {
    const readiness = evaluateMacosReleaseReadiness({
      bundleId: "com.example.rcc",
    });

    expect(readiness.status).toBe("blocked");
    expect(readiness.missingInputs).toContain("Apple Team ID");
  });

  it("reports ready only when the full signing contract is present", () => {
    const readiness = evaluateMacosReleaseReadiness({
      bundleId: "com.example.rcc",
      appleTeamId: "TEAMID1234",
      signingIdentity: "Developer ID Application: Example",
      notarizationAppleId: "ops@example.com",
      notarizationAppPassword: "app-password",
      notarizationProviderShortName: "EXAMPLE",
    });

    expect(readiness.status).toBe("ready");
    expect(readiness.missingInputs).toHaveLength(0);
  });
});
