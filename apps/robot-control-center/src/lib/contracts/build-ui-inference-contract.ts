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
      ? "Hlavný panel berie údaje z mockov, nie zo skutočného runtime."
      : "Hlavný panel berie údaje zo súhrnu runtime, zdravia systému, integrity, symbolov, rozhodnutí a upozornení.",
    dashboard.healthState.artifactFallbackActive
      ? "Náhradná obnova z artefaktov je zapnutá a panel to priznáva v stave systému."
      : "Náhradná obnova z artefaktov nie je zapnutá.",
  ];
  if (dashboard.warnings[0]) {
    notes.push(dashboard.warnings[0]);
  }

  return {
    id: "command",
    label: "Hlavný panel",
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
    label: "Rozhodovanie",
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
    label: "Bezpečnosť",
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
    label: "Obchody",
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
      label: "Zdroj dát je jasný",
      status: dashboard.source === "runtime-api" ? "pass" : "fail",
      detail:
        dashboard.source === "runtime-api"
          ? "Aplikácia je napojená na runtime API."
          : "Aplikácia beží v priznanom mock režime.",
    },
    {
      label: "Výber behu je zamknutý",
      status:
        runtimeIdentity.selectionMode === "pinned"
          ? runtimeIdentity.pinIntegrityStatus === "ok" && runtimeIdentity.driftStatus === "locked"
            ? "pass"
            : "fail"
          : "warn",
      detail:
        runtimeIdentity.selectionMode === "pinned"
          ? `${runtimeIdentity.pinIntegrityStatus} / ${runtimeIdentity.driftStatus}`
          : "Sleduje sa najnovší beh, nie pevne vybraný.",
    },
    {
      label: "Všetky časti ukazujú to isté",
      status:
        runtimeIdentity.endpointConsistencyStatus === "consistent"
          ? "pass"
          : runtimeIdentity.endpointConsistencyStatus === "partial"
            ? "warn"
            : "fail",
      detail: runtimeIdentity.endpointConsistencyStatus,
    },
    {
      label: "História sedí s aktuálnym behom",
      status:
        runtimeIdentity.replayAlignmentStatus === "aligned"
          ? "pass"
          : runtimeIdentity.replayAlignmentStatus === "partial"
            ? "warn"
            : "fail",
      detail: runtimeIdentity.replayAlignmentStatus,
    },
    {
      label: "Odvodené polia sú priznané",
      status: "pass",
      detail:
        derivedTotal > 0
          ? `${derivedTotal} odvodených polí je v aplikácii jasne označených.`
          : "Momentálne sa nezobrazujú žiadne odvodené polia.",
    },
    {
      label: "Chýbajúce údaje sa nevymýšľajú",
      status: "pass",
      detail:
        unavailableTotal > 0
          ? `${unavailableTotal} chýbajúcich hodnôt zostalo priznaných namiesto toho, aby si ich UI domyslelo.`
          : "Momentálne sa nezobrazujú žiadne chýbajúce hodnoty.",
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
      ? "Mock režim je priznaný a nedá sa zameniť za živé údaje."
      : "Hlavná pravda pre tento panel ide z runtime API.",
    runtimeIdentity.selectionMode === "pinned"
      ? `Pripnutý beh ${runtimeIdentity.runId} má stav ${runtimeIdentity.pinIntegrityStatus}.`
      : "Panel sleduje najnovší beh, takže cieľ sa môže meniť a je to viditeľne označené.",
    derivedFieldCount > 0
      ? "Odvodené hodnoty sú dovolené len vtedy, keď sú označené a dajú sa dohľadať."
      : "Momentálne nie sú žiadne odvodené hodnoty, ktoré by si musel kontrolovať.",
    unavailableFieldCount > 0
      ? "Keď údaj chýba, aplikácia to povie otvorene a nič si nedomýšľa."
      : "Momentálne sa nezobrazujú žiadne chýbajúce hodnoty.",
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
