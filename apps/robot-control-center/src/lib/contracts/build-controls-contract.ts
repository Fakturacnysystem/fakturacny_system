import type { ControlsContract } from "@/types/contracts";
import type {
  HealthState,
  IntegrityState,
  RuntimeControlResponse,
} from "@/types/runtime";
import type { RuntimeAuthSnapshot } from "@/lib/auth/runtime-auth";

export interface BuildControlsContractInput {
  auth: RuntimeAuthSnapshot;
  health: HealthState;
  integrity: IntegrityState;
  lastResponse: RuntimeControlResponse | null;
}

export function buildControlsContract({
  auth,
  health,
  integrity,
  lastResponse,
}: BuildControlsContractInput): ControlsContract {
  const hasActiveOperator = auth.status === "active" && Boolean(auth.operatorId);
  const resumeBlockedByRuntime = health.status === "danger" || integrity.blockers.length > 0;

  return {
    statusLine: hasActiveOperator
      ? `Operator ${auth.displayName || auth.operatorId} is bound to session ${auth.sessionId}.`
      : "No active operator identity. All destructive commands are blocked.",
    provenanceLine: `auth=${auth.authSource} status=${auth.status} provider=${auth.providerStatus}`,
    canWriteIncidentNotes: hasActiveOperator,
    actions: [
      {
        action: "pause",
        label: "Pause",
        enabled: hasActiveOperator,
        tone: "warn",
        disabledReason: hasActiveOperator ? undefined : "Authenticated operator required.",
      },
      {
        action: "resume",
        label: "Resume",
        enabled: hasActiveOperator && !resumeBlockedByRuntime,
        tone: "good",
        disabledReason: !hasActiveOperator
          ? "Authenticated operator required."
          : "Health and integrity must be clear before resuming.",
      },
      {
        action: "freeze",
        label: "Freeze",
        enabled: hasActiveOperator,
        tone: "warn",
        disabledReason: hasActiveOperator ? undefined : "Authenticated operator required.",
      },
      {
        action: "flatten",
        label: "Emergency Flatten",
        enabled: hasActiveOperator,
        tone: "danger",
        disabledReason: hasActiveOperator ? undefined : "Authenticated operator required.",
      },
    ],
    lastResponse,
  };
}
