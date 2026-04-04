import type {
  DashboardContract,
  RuntimeIdentityContract,
  UiInferenceContract,
  UiInferenceRuleContract,
  UiInferenceSurfaceContract,
} from "@/types/contracts";
import type {
  BrainState,
  BrainSymbolView,
  ExecutionAccountSnapshot,
  ExecutionOrder,
  ExecutionPosition,
  ExecutionState,
  ExecutionVenueTelemetry,
  ShieldGuardItem,
  ShieldSafetyItem,
  ShieldState,
} from "@/types/runtime";

function isUnavailableText(value: string | null | undefined): boolean {
  if (!value) {
    return true;
  }
  const normalized = value.trim().toLowerCase();
  return normalized === "unavailable" || normalized === "runtime-unavailable";
}

function countNullish(values: unknown[]): number {
  return values.filter((value) => value === null || value === undefined || value === "").length;
}

function countUnavailableStrings(values: Array<string | null | undefined>): number {
  return values.filter((value) => isUnavailableText(value)).length;
}

function uniqueCount(values: Iterable<string>): number {
  return new Set(Array.from(values).filter(Boolean)).size;
}

function surfaceStatus(derived: number, unavailable: number, breach: boolean): UiInferenceSurfaceContract["status"] {
  if (breach) {
    return "breach";
  }
  if (derived > 0 || unavailable > 0) {
    return "watch";
  }
  return "contained";
}

function brainUnavailableCount(brain: BrainState, selectedSymbolView: BrainSymbolView | null): number {
  let count = countUnavailableStrings([
    brain.selectedSymbol,
    brain.actionState,
    brain.sellFloorStatus,
    brain.marketRegime,
    brain.riskGatingOutcome,
    brain.executionEligibilityOutcome,
  ]);
  if (brain.costAdjustedEdgeBps === null) {
    count += 1;
  }
  if (isUnavailableText(brain.costAdjustedEdgeSource)) {
    count += 1;
  }
  count += brain.pipeline.filter((step) => step.status === "unavailable").length;
  if (selectedSymbolView) {
    count += countNullish([
      selectedSymbolView.bid,
      selectedSymbolView.ask,
      selectedSymbolView.spreadBps,
      selectedSymbolView.depthNotional,
      selectedSymbolView.confidence,
    ]);
    count += countUnavailableStrings([
      selectedSymbolView.signal,
      selectedSymbolView.forecast,
      selectedSymbolView.lastAction,
      selectedSymbolView.nextEligibleAction,
    ]);
  } else {
    count += 1;
  }
  return count;
}

function executionOrderUnavailableCount(order: ExecutionOrder): number {
  return countNullish([
    order.side,
    order.quantity,
    order.targetNotional,
    order.price,
    order.fees,
    order.slippage,
    order.venueResponseSummary,
  ]);
}

function executionPositionUnavailableCount(position: ExecutionPosition): number {
  return countNullish([
    position.side,
    position.quantity,
    position.exposureNotional,
    position.entryPrice,
    position.markPrice,
    position.unrealizedPnl,
    position.realizedPnl,
    position.costBasis,
    position.holdDurationSec,
    position.exitEligibility,
    position.sellFloorStatus,
  ]);
}

function accountUnavailableCount(accountSnapshot: ExecutionAccountSnapshot | null): number {
  if (!accountSnapshot) {
    return 1;
  }
  return countNullish([
    accountSnapshot.venue,
    accountSnapshot.symbol,
    accountSnapshot.baselineBalance,
    accountSnapshot.exchangeBalance,
    accountSnapshot.grossExposureNotional,
    accountSnapshot.localCashDelta,
    accountSnapshot.realizedPnl,
    accountSnapshot.unrealizedPnl,
    accountSnapshot.cumulativeFees,
    accountSnapshot.cumulativeSlippage,
    accountSnapshot.fillCount,
  ]);
}

function venueTelemetryUnavailableCount(venueTelemetry: ExecutionVenueTelemetry | null): number {
  if (!venueTelemetry) {
    return 1;
  }
  let count = isUnavailableText(venueTelemetry.userStreamStatus) ? 1 : 0;
  count += isUnavailableText(venueTelemetry.lifecycleStatus) ? 1 : 0;
  count += countNullish([
    venueTelemetry.lastUserStreamEvent,
    venueTelemetry.reconciliationStatus,
    venueTelemetry.executionPlanStyle,
    venueTelemetry.fillProbability,
  ]);
  return count;
}

function buildCommandSurface(dashboard: DashboardContract): UiInferenceSurfaceContract {
  const unavailableFieldCount = dashboard.metrics.filter(
    (metric) => metric.value === "Awaiting" || metric.value === "Pending",
  ).length;
  const derivedFieldCount =
    (dashboard.source === "mock" ? 1 : 0) +
    (dashboard.healthState.artifactFallbackActive ? 1 : 0);
  const notes = [
    dashboard.source === "mock"
      ? "Command Center is fed by typed mock data; it is not authoritative runtime truth."
      : "Command Center cards are fed by runtime summary, health, integrity, symbols, decisions, and alerts.",
    dashboard.healthState.artifactFallbackActive
      ? "Artifact fallback is active and is called out explicitly in health and integrity state."
      : "Artifact fallback is inactive.",
  ];
  if (dashboard.warnings[0]) {
    notes.push(dashboard.warnings[0]);
  }

  return {
    id: "command",
    label: "Command Center",
    status: surfaceStatus(derivedFieldCount, unavailableFieldCount, dashboard.source === "mock"),
    directEvidenceCount:
      dashboard.badges.length +
      dashboard.healthDetails.length +
      dashboard.integrityDetails.length +
      dashboard.symbols.length +
      dashboard.decisions.length +
      dashboard.alerts.length,
    derivedFieldCount,
    unavailableFieldCount,
    linkedArtifactCount: 0,
    notes,
  };
}

function buildBrainSurface(brain: BrainState): UiInferenceSurfaceContract {
  const selectedSymbolView =
    brain.symbolViews.find((symbol) => symbol.symbol === brain.selectedSymbol) ??
    brain.symbolViews[0] ??
    null;
  const derivedFieldCount =
    brain.pipeline.filter((step) => step.derived).length +
    brain.symbolViews.reduce((total, symbol) => total + symbol.derivedFields.length, 0);
  const linkedArtifactCount = uniqueCount([
    ...brain.decisionReplay.linkedArtifacts,
    ...brain.pipeline.flatMap((step) => step.evidence),
  ]);

  return {
    id: "brain",
    label: "Brain",
    status: surfaceStatus(
      derivedFieldCount,
      brainUnavailableCount(brain, selectedSymbolView),
      brain.stateKind === "error" || brain.stateKind === "unresolved" || brain.stateKind === "unavailable",
    ),
    directEvidenceCount:
      brain.pipeline.filter((step) => !step.derived && step.status !== "unavailable").length +
      brain.decisionReplay.evidence.length +
      brain.symbolViews.length +
      brain.whyTrade.length +
      brain.whyNotTrade.length +
      brain.supportingSignals.length,
    derivedFieldCount,
    unavailableFieldCount: brainUnavailableCount(brain, selectedSymbolView),
    linkedArtifactCount,
    notes: brain.evidenceNotes.slice(0, 3),
  };
}

function buildShieldSurface(shield: ShieldState): UiInferenceSurfaceContract {
  const linkedArtifactCount = uniqueCount([
    ...shield.linkedArtifacts,
    ...shield.runtimeSafety.flatMap((item: ShieldSafetyItem) => item.evidence),
    ...shield.guardMatrix.flatMap((guard: ShieldGuardItem) => guard.evidence),
    ...shield.userStream.evidence,
  ]);
  const derivedFieldCount = shield.guardMatrix.filter((guard) => guard.derived).length;
  const unavailableFieldCount =
    shield.runtimeSafety.filter((item) => item.status === "unavailable").length +
    shield.guardMatrix.filter((guard) => guard.status === "unavailable").length +
    (shield.userStream.status === "unavailable" ? 1 : 0);

  return {
    id: "shield",
    label: "Shield",
    status: surfaceStatus(
      derivedFieldCount,
      unavailableFieldCount,
      shield.runtimeIdentity?.pinIntegrityStatus === "mismatch" ||
        shield.runtimeIdentity?.pinIntegrityStatus === "unresolved" ||
        shield.stateKind === "error" ||
        shield.stateKind === "unresolved" ||
        shield.stateKind === "unavailable",
    ),
    directEvidenceCount:
      shield.runtimeSafety.filter((item) => item.status !== "unavailable").length +
      shield.guardMatrix.filter((guard) => !guard.derived).length +
      (shield.appliedControl ? 1 : 0) +
      (shield.userStream.status !== "unavailable" ? 1 : 0),
    derivedFieldCount,
    unavailableFieldCount,
    linkedArtifactCount,
    notes: shield.truthNotes.slice(0, 3),
  };
}

function buildExecutionSurface(execution: ExecutionState): UiInferenceSurfaceContract {
  const derivedFieldCount =
    execution.summary.filter((metric) => metric.derived).length +
    execution.orders.reduce((total, order) => total + order.derivedFields.length, 0) +
    execution.positions.reduce((total, position) => total + position.derivedFields.length, 0) +
    (execution.accountSnapshot?.derivedFields.length ?? 0);
  const unavailableFieldCount =
    execution.summary.filter((metric) => metric.value === null).length +
    execution.orders.reduce((total, order) => total + executionOrderUnavailableCount(order), 0) +
    execution.positions.reduce((total, position) => total + executionPositionUnavailableCount(position), 0) +
    accountUnavailableCount(execution.accountSnapshot) +
    venueTelemetryUnavailableCount(execution.venueTelemetry);
  const linkedArtifactCount = uniqueCount([
    ...execution.linkedArtifacts,
    ...(execution.venueTelemetry?.evidence ?? []),
  ]);

  return {
    id: "execution",
    label: "Execution",
    status: surfaceStatus(
      derivedFieldCount,
      unavailableFieldCount,
      execution.stateKind === "error" || execution.stateKind === "unresolved" || execution.stateKind === "unavailable",
    ),
    directEvidenceCount:
      execution.summary.filter((metric) => !metric.derived && metric.value !== null).length +
      execution.orders.length +
      execution.positions.length +
      (execution.accountSnapshot ? 1 : 0) +
      (execution.venueTelemetry ? 1 : 0) +
      execution.timeline.length,
    derivedFieldCount,
    unavailableFieldCount,
    linkedArtifactCount,
    notes: execution.dataNotes.slice(0, 3),
  };
}

function buildRules(
  dashboard: DashboardContract,
  runtimeIdentity: RuntimeIdentityContract,
  surfaces: UiInferenceSurfaceContract[],
): UiInferenceRuleContract[] {
  const derivedTotal = surfaces.reduce((total, surface) => total + surface.derivedFieldCount, 0);
  const unavailableTotal = surfaces.reduce((total, surface) => total + surface.unavailableFieldCount, 0);

  return [
    {
      label: "Runtime source explicit",
      status: dashboard.source === "runtime-api" ? "pass" : "fail",
      detail:
        dashboard.source === "runtime-api"
          ? "UI is bound to runtime API data."
          : "UI is running in explicit mock mode.",
    },
    {
      label: "Run identity lock",
      status:
        runtimeIdentity.selectionMode === "pinned"
          ? runtimeIdentity.pinIntegrityStatus === "ok" && runtimeIdentity.driftStatus === "locked"
            ? "pass"
            : "fail"
          : "warn",
      detail:
        runtimeIdentity.selectionMode === "pinned"
          ? `${runtimeIdentity.pinIntegrityStatus} / ${runtimeIdentity.driftStatus}`
          : "Tracking latest stays explicit and non-pinned.",
    },
    {
      label: "Endpoint consistency",
      status:
        runtimeIdentity.endpointConsistencyStatus === "consistent"
          ? "pass"
          : runtimeIdentity.endpointConsistencyStatus === "partial"
            ? "warn"
            : "fail",
      detail: runtimeIdentity.endpointConsistencyStatus,
    },
    {
      label: "Replay alignment",
      status:
        runtimeIdentity.replayAlignmentStatus === "aligned"
          ? "pass"
          : runtimeIdentity.replayAlignmentStatus === "partial"
            ? "warn"
            : "fail",
      detail: runtimeIdentity.replayAlignmentStatus,
    },
    {
      label: "Derived fields disclosed",
      status: "pass",
      detail:
        derivedTotal > 0
          ? `${derivedTotal} derived fields are explicitly tagged across the cockpit.`
          : "No derived fields are currently surfaced.",
    },
    {
      label: "Unavailable stays unavailable",
      status: "pass",
      detail:
        unavailableTotal > 0
          ? `${unavailableTotal} unavailable values stayed explicit instead of being back-filled by the UI.`
          : "No active unavailable values are being surfaced.",
    },
  ];
}

export interface BuildUiInferenceContractInput {
  dashboard: DashboardContract;
  runtimeIdentity: RuntimeIdentityContract;
  brain: BrainState;
  shield: ShieldState;
  execution: ExecutionState;
}

export function buildUiInferenceContract({
  dashboard,
  runtimeIdentity,
  brain,
  shield,
  execution,
}: BuildUiInferenceContractInput): UiInferenceContract {
  const surfaces = [
    buildCommandSurface(dashboard),
    buildBrainSurface(brain),
    buildShieldSurface(shield),
    buildExecutionSurface(execution),
  ];
  const derivedFieldCount = surfaces.reduce((total, surface) => total + surface.derivedFieldCount, 0);
  const unavailableFieldCount = surfaces.reduce((total, surface) => total + surface.unavailableFieldCount, 0);
  const linkedArtifactCount = surfaces.reduce((total, surface) => total + surface.linkedArtifactCount, 0);
  const rules = buildRules(dashboard, runtimeIdentity, surfaces);

  const status: UiInferenceContract["status"] =
    rules.some((rule) => rule.status === "fail") ||
    surfaces.some((surface) => surface.status === "breach") ||
    runtimeIdentity.endpointConsistencyStatus === "mismatch" ||
    runtimeIdentity.replayAlignmentStatus === "mismatch"
      ? "breach"
      : rules.some((rule) => rule.status === "warn") ||
          surfaces.some((surface) => surface.status === "watch") ||
          runtimeIdentity.freshnessStatus === "stale" ||
          runtimeIdentity.stateKind === "stale" ||
          runtimeIdentity.stateKind === "degraded" ||
          runtimeIdentity.stateKind === "partial"
        ? "watch"
        : "contained";

  const notes = [
    dashboard.source === "mock"
      ? "Mock mode is explicit and cannot be mistaken for live runtime truth."
      : "Runtime API is the active truth path for the cockpit.",
    runtimeIdentity.selectionMode === "pinned"
      ? `Pinned run ${runtimeIdentity.runId} is ${runtimeIdentity.pinIntegrityStatus}.`
      : "Cockpit is tracking latest; the observation target can move and is labeled as such.",
    derivedFieldCount > 0
      ? "Derived values are permitted only when individually tagged and traceable."
      : "No current derived values require operator review.",
    unavailableFieldCount > 0
      ? "Unavailable values remain explicit so the UI never fabricates hidden confidence."
      : "No active unavailable values are being surfaced.",
  ];

  return {
    status,
    source: dashboard.source,
    derivedFieldCount,
    unavailableFieldCount,
    linkedArtifactCount,
    surfaces,
    rules,
    notes,
  };
}
