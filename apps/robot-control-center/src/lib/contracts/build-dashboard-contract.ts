import type {
  ContractBadge,
  DashboardContract,
  MetricCard,
} from "@/types/contracts";
import type {
  HealthState,
  IntegrityState,
  RuntimeDataSource,
  RuntimeSummary,
  RuntimeTone,
  RuntimeListResponse,
  SymbolSnapshot,
  DecisionRecord,
  AlertRecord,
} from "@/types/runtime";
import type { RuntimeAuthSnapshot } from "@/lib/auth/runtime-auth";

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value: number, suffix = ""): string {
  return `${new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: 2,
  }).format(value)}${suffix}`;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

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

function toneFromHealth(health: HealthState, integrity: IntegrityState): RuntimeTone {
  if (health.status === "danger" || integrity.stateKind === "error") {
    return "danger";
  }
  if (health.status === "warn" || integrity.blockers.length > 0) {
    return "warn";
  }
  return "good";
}

function authStatusLabel(snapshot: RuntimeAuthSnapshot): string {
  switch (snapshot.status) {
    case "active":
      return "authenticated";
    case "expired":
      return "expired";
    case "invalid":
      return "invalid";
    case "provider-unavailable":
      return "provider unavailable";
    default:
      return "anonymous";
  }
}

export interface BuildDashboardContractInput {
  summary: RuntimeSummary;
  health: HealthState;
  integrity: IntegrityState;
  symbols: RuntimeListResponse<SymbolSnapshot>;
  decisions: RuntimeListResponse<DecisionRecord>;
  alerts: RuntimeListResponse<AlertRecord>;
  auth: RuntimeAuthSnapshot;
  source: RuntimeDataSource;
}

export function buildDashboardContract({
  summary,
  health,
  integrity,
  symbols,
  decisions,
  alerts,
  auth,
  source,
}: BuildDashboardContractInput): DashboardContract {
  const awaitingAuthoritativeSummary =
    source === "runtime-api" && summary.bridge.reasonCode === "runtime_api_unavailable";
  const primaryTone = toneFromHealth(health, integrity);
  const sourceTone = source === "runtime-api" ? (summary.bridge.health_status === "unavailable" ? "danger" : "good") : "warn";
  const selectionTone = summary.runtimeIdentity.runSelectionMode === "pinned" ? "good" : "warn";
  const latencyTone =
    summary.bridge.health_status === "healthy"
      ? "good"
      : summary.bridge.restHealthy
        ? "info"
        : "warn";
  const latencyHint = summary.bridge.restHealthy
    ? summary.bridge.wsConnected
      ? "Runtime API live via REST + event feed"
      : "Runtime API live via REST polling"
    : "Runtime connectivity degraded";
  const subtitle =
    awaitingAuthoritativeSummary
      ? "Runtime API is configured and bootstrap is in progress. RCC keeps waiting explicit so no synthetic zero-state can masquerade as authoritative runtime truth."
      : source === "runtime-api"
      ? "Runtime API is the active truth path. Any unavailable payload stays explicit so operators never see synthetic fallback disguised as live state."
      : "Runtime API is not configured. RCC is intentionally in explicit mock mode so operational truth boundaries remain visible.";
  const badges: ContractBadge[] = [
    { label: "Source", value: source, tone: sourceTone },
    { label: "Run lock", value: summary.runtimeIdentity.runSelectionMode, tone: selectionTone },
    { label: "Bridge", value: summary.bridge.health_status, tone: primaryTone },
    { label: "Auth", value: authStatusLabel(auth), tone: auth.status === "active" ? "good" : "warn" },
    { label: "Mode", value: summary.mode, tone: "info" },
  ];

  const metrics: MetricCard[] = [
    {
      label: "Equity",
      value: awaitingAuthoritativeSummary ? "Awaiting" : formatMoney(summary.portfolio.equityEur),
      hint: awaitingAuthoritativeSummary
        ? "Authoritative portfolio summary pending"
        : `Free cash ${formatMoney(summary.portfolio.freeCashEur)}`,
      tone: awaitingAuthoritativeSummary ? "info" : "good",
    },
    {
      label: "Exposure",
      value: awaitingAuthoritativeSummary
        ? "Awaiting"
        : `${summary.portfolio.openPositions} positions`,
      hint: awaitingAuthoritativeSummary
        ? "Position and order truth pending"
        : `${summary.portfolio.openOrders} open orders`,
      tone: awaitingAuthoritativeSummary
        ? "info"
        : summary.portfolio.openPositions > 0
          ? "warn"
          : "info",
    },
    {
      label: "Latency",
      value: awaitingAuthoritativeSummary
        ? "Pending"
        : formatNumber(summary.bridge.avgLatencyMs, " ms"),
      hint: awaitingAuthoritativeSummary
        ? "Waiting for authoritative summary bootstrap"
        : latencyHint,
      tone: awaitingAuthoritativeSummary ? "info" : latencyTone,
    },
    {
      label: "Uptime",
      value: awaitingAuthoritativeSummary ? "Awaiting" : formatDuration(summary.uptimeSec),
      hint: awaitingAuthoritativeSummary
        ? "Provider identity pending"
        : `Provider ${summary.providerId}`,
      tone: "info",
    },
    {
      label: "Capital utilization",
      value:
        awaitingAuthoritativeSummary || summary.performance?.capitalUtilizationPct == null
          ? "Awaiting"
          : formatNumber(summary.performance.capitalUtilizationPct, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Waiting for capital envelope diagnostics"
        : "Deployable capital currently in use",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.capitalUtilizationPct ?? 0) >= 50
            ? "good"
            : "warn",
    },
    {
      label: "Expectancy",
      value:
        awaitingAuthoritativeSummary || summary.performance?.netExpectancyBps == null
          ? "Awaiting"
          : formatNumber(summary.performance.netExpectancyBps, " bps"),
      hint: awaitingAuthoritativeSummary
        ? "Expectancy engine not loaded yet"
        : "Rolling net expectancy after modeled costs",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.netExpectancyBps ?? 0) > 0
            ? "good"
            : "warn",
    },
    {
      label: "Fill rate",
      value:
        awaitingAuthoritativeSummary || summary.performance?.fillRate == null
          ? "Awaiting"
          : formatNumber((summary.performance.fillRate ?? 0) * 100, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Waiting for execution-quality telemetry"
        : "Observed order-to-fill conversion",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.fillRate ?? 0) >= 0.5
            ? "good"
            : "warn",
    },
    {
      label: "Maker ratio",
      value:
        awaitingAuthoritativeSummary || summary.performance?.makerRatio == null
          ? "Awaiting"
          : formatNumber((summary.performance.makerRatio ?? 0) * 100, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Waiting for maker/taker mix report"
        : "Maker-first execution share",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.makerRatio ?? 0) >= 0.6
            ? "good"
            : "warn",
    },
    {
      label: "Target gap",
      value: awaitingAuthoritativeSummary
        ? "Awaiting"
        : formatNumber(Object.keys(summary.performance?.targetGap ?? {}).length, " gaps"),
      hint: awaitingAuthoritativeSummary
        ? "Waiting for performance target translation"
        : "Number of active target shortfall dimensions",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : Object.keys(summary.performance?.targetGap ?? {}).length === 0
            ? "good"
            : "warn",
    },
  ];

  const warnings = [
    ...health.warnings,
    ...integrity.warnings,
    ...(summary.bridge.reasonText ? [summary.bridge.reasonText] : []),
  ];

  return {
    title: "Robot Control Center",
    subtitle,
    source,
    runId: awaitingAuthoritativeSummary ? "awaiting-authoritative-summary" : summary.runId,
    mode: summary.mode,
    lastUpdatedAt: awaitingAuthoritativeSummary ? "" : summary.bridge.lastUpdatedAt,
    runtimeIdentity: {
      runId: summary.runtimeIdentity.runId,
      selectionMode: summary.runtimeIdentity.runSelectionMode,
      resolutionSource: summary.runtimeIdentity.runResolutionSource,
      runPath: summary.runtimeIdentity.runPath,
      providerId: summary.runtimeIdentity.providerId,
      mode: summary.runtimeIdentity.mode,
      stateKind: summary.runtimeIdentity.stateKind,
      reasonCode: summary.runtimeIdentity.reasonCode ?? "ok",
      driftStatus: summary.runtimeIdentity.driftStatus,
      pinIntegrityStatus: summary.runtimeIdentity.pinIntegrityStatus,
      freshnessStatus: summary.runtimeIdentity.artifactFreshness.status,
      freshnessAgeLabel: formatAge(summary.runtimeIdentity.artifactFreshness.ageSeconds),
      lastArtifactUpdateAt: summary.runtimeIdentity.lastArtifactUpdateAt ?? "",
      schemaVersion: String(summary.runtimeIdentity.schemaVersion ?? "unknown"),
    },
    healthState: {
      status: health.status,
      bridgeHealthy: health.bridgeHealthy,
      backendHealthy: health.backendHealthy,
      artifactFallbackActive: health.artifactFallbackActive,
    },
    integrityState: {
      doctrineStatus: integrity.doctrineStatus,
      capabilityConfidence: integrity.capabilityConfidence,
      degradationState: integrity.degradationState,
      unlockActions: integrity.unlockActions,
      stateKind: integrity.stateKind,
    },
    badges,
    metrics,
    warnings,
    blockers: integrity.blockers,
    authSummary: {
      status: authStatusLabel(auth),
      operatorLabel: auth.displayName || auth.operatorId || "No operator bound",
      role: auth.role,
      sessionId: auth.sessionId,
      authSource: auth.authSource,
    },
    healthDetails: health.details,
    integrityDetails: integrity.details,
    symbols: symbols.items,
    decisions: decisions.items,
    alerts: alerts.items,
  };
}
