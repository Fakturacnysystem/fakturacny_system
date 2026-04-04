import { describe, expect, it } from "vitest";
import { resolveReplayRunId } from "@/lib/contracts/replay-run-id";
import { mockReplay } from "@/lib/runtime/mock-data";

describe("resolveReplayRunId", () => {
  it("boots runtime-api replay from latest until summary truth arrives", () => {
    expect(resolveReplayRunId("runtime-api")).toBe("latest");
    expect(resolveReplayRunId("runtime-api", null)).toBe("latest");
    expect(resolveReplayRunId("runtime-api", "runtime-unavailable")).toBe("latest");
  });

  it("preserves authoritative runtime run ids once loaded", () => {
    expect(resolveReplayRunId("runtime-api", "run-2026-03-29-live")).toBe(
      "run-2026-03-29-live",
    );
  });

  it("keeps mock replay ids in mock mode", () => {
    expect(resolveReplayRunId("mock")).toBe(mockReplay.runId);
    expect(resolveReplayRunId("mock", "mock-run-override")).toBe("mock-run-override");
  });
});
