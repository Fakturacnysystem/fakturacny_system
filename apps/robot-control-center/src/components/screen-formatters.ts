const exactTextMap: Record<string, string> = {
  "Canonical operator/replay bundles are missing; runtime API is reconstructing state from raw artifacts.":
    "Chýbajú hlavné balíky pre operátora a históriu. Panel preto skladá stav zo surových artefaktov.",
  "Canonical runtime bundles missing; reconstructed artifact mode is active.":
    "Chýbajú hlavné runtime balíky. Panel preto používa rekonštruovaný režim z artefaktov.",
  "Manual review required before continuation.":
    "Pred pokračovaním je potrebná manuálna kontrola.",
  "structured payload":
    "štruktúrovaný záznam",
  "costAdjustedEdgeBps is only populated when a direct net-after-cost field exists in runtime artifacts.":
    "Výhoda po nákladoch sa ukáže len vtedy, keď ju beh poslal priamo v artefaktoch.",
  "nextEligibleAction is marked derived when inferred from decision intent plus current live ordering gate.":
    "Ďalší možný krok je označený ako odvodený, keď vznikol z kombinácie zámeru a aktuálnej brány obchodovania.",
  "Pinned mode never silently falls back to latest; unresolved pin integrity is surfaced as unsafe.":
    "Pri pevnom pripnutí panel nikdy potichu nespadne na najnovší beh. Ak je pripnutie nejasné, ukáže to ako riziko.",
  "Guard statuses only compare direct observed values against direct configured thresholds; missing evidence stays unavailable.":
    "Ochrany porovnávajú iba priamo namerané hodnoty s priamo nastavenými limitmi. Chýbajúce dôkazy ostávajú nedostupné.",
  "Applied runtime control is sourced from control_journal.jsonl; queued operator commands are sourced from rcc_control_outbox.jsonl.":
    "To, čo momentálne platí, ide z control_journal.jsonl. Čakajúce príkazy operátora idú z rcc_control_outbox.jsonl.",
  "Orders surface only uses direct order/fill lifecycle artifacts. Missing OMS fields remain unavailable.":
    "Obrazovka pokynov používa iba priame udalosti o pokynoch a vykonaniach. Chýbajúce polia z OMS ostávajú nedostupné.",
  "Position rows are emitted only when current exposure is observable from account or position snapshots.":
    "Pozície sa ukazujú len vtedy, keď ich vie potvrdiť stav účtu alebo snímka pozícií.",
  "Venue telemetry uses direct auth-stream, lifecycle-evidence, execution-journal, and reconciliation artifacts only.":
    "Telemetria z burzy sa berie len z priamych artefaktov o prihlásenom streame, priebehu, denníku vykonania a zhode účtovania.",
};

const exactLabelMap: Record<string, string> = {
  "Run directory": "Priečinok behu",
  "Artifact age": "Vek artefaktu",
  "Artifact fallback": "Náhradné čítanie artefaktov",
  "Public quote path": "Cesta verejných cien",
  "Event feed": "Tok udalostí",
  "Open quote snapshots": "Počet snímok cien",
  "Doctrine action": "Ochranný zásah",
  "Capability confidence": "Istota schopností",
  "Reconciliation": "Zhoda účtovania",
  "Live ordering": "Live zadávanie pokynov",
  "Timeline items": "Položky časovej osi",
  "Incidents": "Incidenty",
  "Critical alerts": "Kritické upozornenia",
  "Counterfactuals": "Alternatívne scenáre",
  "Truth Confidence Snapshot": "Snímka dôveryhodnosti pravdy",
  "Manual review": "Manuálna kontrola",
};

const exactCodeMap: Record<string, string> = {
  manual_review_required: "treba manuálna kontrola",
  doctrine_probe_dominates: "ochranný test má prednosť",
  mastermind_continue: "hlavný koordinátor odporúča pokračovať",
  truth_context_missing: "chýba kontext pravdy",
  manual_review: "manuálna kontrola",
  continue: "pokračovať",
  block: "blokované",
  active: "aktívne",
  degraded: "zhoršené",
  enabled: "povolené",
  none: "žiadne",
  ok: "v poriadku",
  pinned: "pevne pripnuté",
  stale: "staré",
  latest: "najnovšie",
  unresolved: "nevyriešené",
  healthy: "zdravé",
  live: "živé",
  paper: "papierové",
  live_readonly: "živé len na čítanie",
  explicit_run_id: "priamy výber podľa ID",
  default_latest: "predvolený najnovší beh",
  caution: "opatrnosť",
  critical: "kritické",
  warn: "varovanie",
  unsafe: "nebezpečné",
};

function capitalizeFirst(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function formatMoment(value: string | null | undefined) {
  if (!value) {
    return "čaká sa na údaje";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("sk-SK", {
    hour12: false,
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function toneFromVerdict(verdict: string) {
  if (["block", "unsafe", "fail", "rejected", "unresolved", "disconnected"].includes(verdict)) {
    return "danger" as const;
  }
  if (["watch", "warn", "caution", "partially filled"].includes(verdict)) {
    return "warn" as const;
  }
  return "good" as const;
}

export function toneFromSeverity(severity: string) {
  if (["critical", "danger", "unsafe", "block", "fail", "unresolved"].includes(severity)) {
    return "danger" as const;
  }
  if (["warn", "warning", "caution"].includes(severity)) {
    return "warn" as const;
  }
  return "info" as const;
}

export function toneFromPipelineStatus(status: string) {
  if (status === "fail") {
    return "danger" as const;
  }
  if (status === "warn") {
    return "warn" as const;
  }
  if (status === "pass") {
    return "good" as const;
  }
  return "info" as const;
}

export function toneFromGuardStatus(status: string) {
  if (status === "block") {
    return "danger" as const;
  }
  if (status === "warn") {
    return "warn" as const;
  }
  if (status === "ok") {
    return "good" as const;
  }
  return "info" as const;
}

export function formatOptionalNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Nedostupné";
  }
  return new Intl.NumberFormat("sk-SK", {
    maximumFractionDigits: digits,
  }).format(value);
}

export function humanizeRuntimeText(value: string | null | undefined) {
  if (!value) {
    return "Nedostupné";
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return "Nedostupné";
  }

  if (exactTextMap[trimmed]) {
    return exactTextMap[trimmed];
  }
  if (exactLabelMap[trimmed]) {
    return exactLabelMap[trimmed];
  }
  if (trimmed.startsWith("Latest runtime artifact is ") && trimmed.endsWith(" old.")) {
    const age = trimmed.replace("Latest runtime artifact is ", "").replace(" old.", "");
    return `Posledný dostupný artefakt je starý ${age}.`;
  }
  if (trimmed.startsWith("Bounded Support: ")) {
    return `Ohraničená podpora: ${trimmed.slice("Bounded Support: ".length)}`;
  }
  if (trimmed.startsWith("Capital posture: ")) {
    return `Stav kapitálu: ${trimmed.slice("Capital posture: ".length)}`;
  }
  if (trimmed.startsWith("Equity: ")) {
    return `Hodnota účtu: ${trimmed.slice("Equity: ".length)}`;
  }
  if (trimmed.startsWith("Fills: ")) {
    return `Vykonané obchody: ${trimmed.slice("Fills: ".length)}`;
  }
  if (trimmed.startsWith("Reconciliation: ")) {
    return `Zhoda účtovania: ${trimmed.slice("Reconciliation: ".length)}`;
  }
  if (trimmed.startsWith("Truth ownership: ")) {
    return `Vlastníctvo pravdy: ${trimmed.slice("Truth ownership: ".length)}`;
  }
  if (trimmed.startsWith("Artifact fallback: ")) {
    return `Náhradné čítanie artefaktov: ${trimmed.slice("Artifact fallback: ".length)}`;
  }
  if (trimmed.startsWith("Missing ") && trimmed.endsWith(".")) {
    return `Chýba ${trimmed.slice("Missing ".length, -1)}.`;
  }

  if (/^[a-z0-9_:-]+$/i.test(trimmed) && exactCodeMap[trimmed]) {
    return `${capitalizeFirst(exactCodeMap[trimmed])} [${trimmed}]`;
  }

  return trimmed;
}
