import type { RuntimeIdentityContract } from "@/types/contracts";
import type {
  HealthState,
  IntegrityState,
  ReplayForensicsState,
  RuntimeListResponse,
  RuntimeSummary,
  AlertRecord,
  DecisionRecord,
  SymbolSnapshot,
} from "@/types/runtime";

function formatAge(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainderSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainderSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  return `${hours}h ${remainderMinutes}m`;
}

interface RuntimeIdentitySource {
  runtimeIdentity?: RuntimeSummary["runtimeIdentity"];
}

export interface BuildRuntimeIdentityContractInput {
  summary: RuntimeSummary;
  health: HealthState;
  integrity: IntegrityState;
  symbols: RuntimeListResponse<SymbolSnapshot>;
  decisions: RuntimeListResponse<DecisionRecord>;
  alerts: RuntimeListResponse<AlertRecord>;
  replay: ReplayForensicsState;
}

function collectIdentities(input: BuildRuntimeIdentityContractInput) {
  return [
    { name: "summary", identity: input.summary.runtimeIdentity },
    { name: "health", identity: input.health.runtimeIdentity },
    { name: "integrity", identity: input.integrity.runtimeIdentity },
    { name: "symbols", identity: input.symbols.runtimeIdentity },
    { name: "decisions", identity: input.decisions.runtimeIdentity },
    { name: "alerts", identity: input.alerts.runtimeIdentity },
    { name: "replay", identity: input.replay.runtimeIdentity },
  ];
}

export function buildRuntimeIdentityContract(
  input: BuildRuntimeIdentityContractInput,
): RuntimeIdentityContract {
  const baseline = input.summary.runtimeIdentity;
  const identities = collectIdentities(input);
  const issues: string[] = [];

  const missingSources = identities
    .filter((item) => item.identity === undefined)
    .map((item) => item.name);
  if (missingSources.length > 0) {
    issues.push(`runtime_identity_missing:${missingSources.join(",")}`);
  }

  const mismatchedSources = identities
    .filter((item) => item.identity !== undefined)
    .filter((item) => {
      const identity = item.identity!;
      return (
        identity.runId !== baseline.runId
        || identity.runPath !== baseline.runPath
        || identity.runSelectionMode !== baseline.runSelectionMode
        || identity.pinIntegrityStatus !== baseline.pinIntegrityStatus
      );
    })
    .map((item) => item.name);
  if (mismatchedSources.length > 0) {
    issues.push(`runtime_identity_mismatch:${mismatchedSources.join(",")}`);
  }

  const replayAlignmentStatus =
    input.replay.runId === baseline.runId
      ? "aligned"
      : input.replay.runId
        ? "mismatch"
        : "partial";
  if (replayAlignmentStatus === "mismatch") {
    issues.push(`replay_run_mismatch:${input.replay.runId}`);
  }

  if (baseline.runSelectionMode === "latest") {
    issues.push("runtime_tracking_latest");
  }
  if (baseline.pinIntegrityStatus !== "ok" && baseline.runSelectionMode === "pinned") {
    issues.push(`pin_integrity:${baseline.pinIntegrityStatus}`);
  }
  if (baseline.driftStatus !== "locked" && baseline.runSelectionMode === "pinned") {
    issues.push(`runtime_drift:${baseline.driftStatus}`);
  }

  const endpointConsistencyStatus =
    mismatchedSources.length > 0
      ? "mismatch"
      : missingSources.length > 0
        ? "partial"
        : "consistent";

  return {
    runId: baseline.runId,
    selectionMode: baseline.runSelectionMode,
    resolutionSource: baseline.runResolutionSource,
    runPath: baseline.runPath,
    providerId: baseline.providerId,
    mode: baseline.mode,
    stateKind: baseline.stateKind,
    reasonCode: baseline.reasonCode ?? "ok",
    driftStatus: baseline.driftStatus,
    pinIntegrityStatus: baseline.pinIntegrityStatus,
    freshnessStatus: baseline.artifactFreshness.status,
    freshnessAgeLabel: formatAge(baseline.artifactFreshness.ageSeconds),
    lastArtifactUpdateAt: baseline.lastArtifactUpdateAt ?? baseline.artifactFreshness.lastArtifactUpdateAt,
    schemaVersion: String(baseline.schemaVersion ?? "unknown"),
    endpointConsistencyStatus,
    replayAlignmentStatus,
    issues,
  };
}
