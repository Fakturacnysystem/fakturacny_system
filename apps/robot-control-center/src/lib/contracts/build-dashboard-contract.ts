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
  return new Intl.NumberFormat("sk-SK", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value: number, suffix = ""): string {
  return `${new Intl.NumberFormat("sk-SK", {
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
      return "prihlásený";
    case "expired":
      return "vypršané";
    case "invalid":
      return "neplatné";
    case "provider-unavailable":
      return "služba nedostupná";
    default:
      return "anonym";
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
      ? "Údaje idú cez REST aj živý stream"
      : "Údaje idú cez pravidelné načítavanie"
    : "Spojenie so systémom je oslabené";
  const subtitle =
    awaitingAuthoritativeSummary
      ? "Aplikácia čaká na prvé spoľahlivé údaje. Kým neprídu, nič si nevymýšľa a radšej ukáže, že ešte čaká."
      : source === "runtime-api"
      ? "Toto sú skutočné údaje z runtime API. Keď niečo chýba, panel to prizná nahlas a nevydáva to za živý stav."
      : "Runtime API nie je nastavené. Panel preto beží v skúšobnom režime a jasne to priznáva.";
  const badges: ContractBadge[] = [
    { label: "Zdroj", value: source, tone: sourceTone },
    { label: "Výber behu", value: summary.runtimeIdentity.runSelectionMode, tone: selectionTone },
    { label: "Stav spojenia", value: summary.bridge.health_status, tone: primaryTone },
    { label: "Prihlásenie", value: authStatusLabel(auth), tone: auth.status === "active" ? "good" : "warn" },
    { label: "Režim", value: summary.mode, tone: "info" },
  ];

  const metrics: MetricCard[] = [
    {
      label: "Hodnota účtu",
      value: awaitingAuthoritativeSummary ? "Čaká sa" : formatMoney(summary.portfolio.equityEur),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na súhrn peňazí v účte"
        : `Voľné peniaze ${formatMoney(summary.portfolio.freeCashEur)}`,
      tone: awaitingAuthoritativeSummary ? "info" : "good",
    },
    {
      label: "Otvorené obchody",
      value: awaitingAuthoritativeSummary
        ? "Čaká sa"
        : `${summary.portfolio.openPositions} otvorených pozícií`,
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na stav pozícií a objednávok"
        : `${summary.portfolio.openOrders} otvorených pokynov`,
      tone: awaitingAuthoritativeSummary
        ? "info"
        : summary.portfolio.openPositions > 0
          ? "warn"
          : "info",
    },
    {
      label: "Odozva",
      value: awaitingAuthoritativeSummary
        ? "Čaká sa"
        : formatNumber(summary.bridge.avgLatencyMs, " ms"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na prvé spoľahlivé údaje"
        : latencyHint,
      tone: awaitingAuthoritativeSummary ? "info" : latencyTone,
    },
    {
      label: "Ako dlho beží",
      value: awaitingAuthoritativeSummary ? "Čaká sa" : formatDuration(summary.uptimeSec),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na identitu zdroja dát"
        : `Zdroj ${summary.providerId}`,
      tone: "info",
    },
    {
      label: "Využitie kapitálu",
      value:
        awaitingAuthoritativeSummary || summary.performance?.capitalUtilizationPct == null
          ? "Čaká sa"
          : formatNumber(summary.performance.capitalUtilizationPct, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na údaje o využití kapitálu"
        : "Koľko kapitálu je práve zapojeného",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.capitalUtilizationPct ?? 0) >= 50
            ? "good"
            : "warn",
    },
    {
      label: "Očakávaný výsledok",
      value:
        awaitingAuthoritativeSummary || summary.performance?.netExpectancyBps == null
          ? "Čaká sa"
          : formatNumber(summary.performance.netExpectancyBps, " bps"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na odhad výsledku"
        : "Priebežný odhad po započítaní nákladov",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.netExpectancyBps ?? 0) > 0
            ? "good"
            : "warn",
    },
    {
      label: "Úspešnosť pokynov",
      value:
        awaitingAuthoritativeSummary || summary.performance?.fillRate == null
          ? "Čaká sa"
          : formatNumber((summary.performance.fillRate ?? 0) * 100, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na kvalitu realizácie"
        : "Koľko pokynov sa naozaj premenilo na obchod",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.fillRate ?? 0) >= 0.5
            ? "good"
            : "warn",
    },
    {
      label: "Podiel výhodnejších pokynov",
      value:
        awaitingAuthoritativeSummary || summary.performance?.makerRatio == null
          ? "Čaká sa"
          : formatNumber((summary.performance.makerRatio ?? 0) * 100, "%"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na rozdelenie typov pokynov"
        : "Podiel pokynov, ktoré mali nižší poplatok",
      tone:
        awaitingAuthoritativeSummary
          ? "info"
          : (summary.performance?.makerRatio ?? 0) >= 0.6
            ? "good"
            : "warn",
    },
    {
      label: "Koľko cieľov mešká",
      value: awaitingAuthoritativeSummary
        ? "Čaká sa"
        : formatNumber(Object.keys(summary.performance?.targetGap ?? {}).length, " cieľov"),
      hint: awaitingAuthoritativeSummary
        ? "Čaká sa na porovnanie s cieľmi"
        : "Počet oblastí, kde je robot pod cieľom",
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
    title: "Riadiaci panel robota",
    subtitle,
    source,
    runId: awaitingAuthoritativeSummary ? "čaká-sa-na-spoľahlivé-údaje" : summary.runId,
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
      operatorLabel: auth.displayName || auth.operatorId || "Nikto nie je prihlásený",
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
