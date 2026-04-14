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
        label: "Položky časovej osi",
        value: String(replay.timeline.length),
        tone: "info",
      },
      {
        label: "Incidenty",
        value: String(replay.incidents.length),
        tone: replay.incidents.length > 0 ? "warn" : "good",
      },
      {
        label: "Kritické upozornenia",
        value: String(criticalAlerts),
        tone: criticalAlerts > 0 ? "danger" : "good",
      },
      {
        label: "Alternatívne scenáre",
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
