import { mockReplay } from "@/lib/runtime/mock-data";
import type { RuntimeDataSource } from "@/types/runtime";

export function resolveReplayRunId(
  source: RuntimeDataSource,
  summaryRunId?: string | null,
): string {
  if (source === "mock") {
    return summaryRunId || mockReplay.runId;
  }

  if (!summaryRunId || summaryRunId === "runtime-unavailable") {
    return "latest";
  }

  return summaryRunId;
}
