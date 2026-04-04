import type { ReplayContract } from "@/types/contracts";
import type {
  AlertRecord,
  ReplayForensicsState,
} from "@/types/runtime";

export function buildReplayContract(
  replay: ReplayForensicsState,
  alerts: AlertRecord[],
): ReplayContract {
  const criticalAlerts = alerts.filter((alert) => alert.severity === "critical").length;

  return {
    runId: replay.runId,
    stateKind: replay.stateKind,
    lastUpdatedAt: replay.lastUpdatedAt,
    summary: [
      {
        label: "Timeline items",
        value: String(replay.timeline.length),
        tone: "info",
      },
      {
        label: "Incidents",
        value: String(replay.incidents.length),
        tone: replay.incidents.length > 0 ? "warn" : "good",
      },
      {
        label: "Critical alerts",
        value: String(criticalAlerts),
        tone: criticalAlerts > 0 ? "danger" : "good",
      },
      {
        label: "Counterfactuals",
        value: String(replay.counterfactuals.length),
        tone: "info",
      },
    ],
    timeline: replay.timeline,
    incidents: replay.incidents,
    analogMatches: replay.analogMatches,
    counterfactuals: replay.counterfactuals,
    pnlAttribution: replay.pnlAttribution,
    notes: replay.notes,
  };
}
