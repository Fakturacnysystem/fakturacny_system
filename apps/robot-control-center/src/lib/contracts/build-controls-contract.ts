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
      ? `Používateľ ${auth.displayName || auth.operatorId} je prihlásený v relácii ${auth.sessionId}.`
      : "Nikto nie je prihlásený. Nebezpečné príkazy sú preto zablokované.",
    provenanceLine: `auth=${auth.authSource} status=${auth.status} provider=${auth.providerStatus}`,
    canWriteIncidentNotes: hasActiveOperator,
    actions: [
      {
        action: "pause",
        label: "Pozastaviť",
        enabled: hasActiveOperator,
        tone: "warn",
        disabledReason: hasActiveOperator ? undefined : "Treba sa najprv prihlásiť ako operátor.",
      },
      {
        action: "resume",
        label: "Pokračovať",
        enabled: hasActiveOperator && !resumeBlockedByRuntime,
        tone: "good",
        disabledReason: !hasActiveOperator
          ? "Treba sa najprv prihlásiť ako operátor."
          : "Pred pokračovaním musí byť stav systému bez blokujúcich problémov.",
      },
      {
        action: "freeze",
        label: "Zmraziť",
        enabled: hasActiveOperator,
        tone: "warn",
        disabledReason: hasActiveOperator ? undefined : "Treba sa najprv prihlásiť ako operátor.",
      },
      {
        action: "flatten",
        label: "Núdzovo zavrieť",
        enabled: hasActiveOperator,
        tone: "danger",
        disabledReason: hasActiveOperator ? undefined : "Treba sa najprv prihlásiť ako operátor.",
      },
    ],
    lastResponse,
  };
}
