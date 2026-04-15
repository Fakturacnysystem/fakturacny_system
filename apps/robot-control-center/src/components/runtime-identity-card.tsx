import React, { useEffect, useMemo, useState } from "react";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type { RuntimeIdentityContract } from "@/types/contracts";
import type { RuntimeRunCatalog, RuntimeRunSelectionResponse } from "@/types/runtime";

function toneForStatus(value: string): "good" | "warn" | "danger" | "info" {
  if (["mismatch", "unresolved", "unsafe", "error", "danger"].includes(value)) {
    return "danger";
  }
  if (["stale", "partial", "warn", "tracking_latest", "not_pinned"].includes(value)) {
    return "warn";
  }
  if (["locked", "consistent", "aligned", "fresh", "ok", "pinned"].includes(value)) {
    return "good";
  }
  return "info";
}

export interface RuntimeIdentityCardProps {
  identity: RuntimeIdentityContract;
  pinCommand?: string;
  runs?: RuntimeRunCatalog | null;
  selectionPending?: boolean;
  selectionError?: string | null;
  selectionResponse?: RuntimeRunSelectionResponse | null;
  onTrackLatest?: () => void;
  onPinRun?: (runId: string) => void;
}

export function RuntimeIdentityCard({
  identity,
  pinCommand,
  runs,
  selectionPending = false,
  selectionError,
  selectionResponse,
  onTrackLatest,
  onPinRun,
}: RuntimeIdentityCardProps) {
  const showPinCommand = identity.selectionMode === "latest" && pinCommand;
  const showMismatchBanner = identity.endpointConsistencyStatus === "mismatch" || identity.replayAlignmentStatus === "mismatch";
  const showPinnedFailure = identity.selectionMode === "pinned" && identity.pinIntegrityStatus !== "ok";
  const availableRuns = runs?.items ?? [];
  const defaultRunId = useMemo(
    () => availableRuns.find((item) => item.current)?.runId ?? availableRuns[0]?.runId ?? identity.runId,
    [availableRuns, identity.runId],
  );
  const [selectedRunId, setSelectedRunId] = useState(defaultRunId);

  useEffect(() => {
    setSelectedRunId(defaultRunId);
  }, [defaultRunId]);

  return (
    <GlassPanel className="rtc-runtime-identity-card" elevated>
      <SectionHeader
        eyebrow="Zamknutý výber"
        title="Čo teraz sleduješ"
        subtitle="Tu vždy vidíš, ktorý konkrétny beh robota je otvorený. Panel nesmie potichu preskočiť na iný beh bez toho, aby to bolo jasne vidieť."
        meta={(
          <div className="rtc-pill-row rtc-runtime-identity-badges">
            <StatusBadge tone={toneForStatus(identity.selectionMode)} value={identity.selectionMode} />
            <StatusBadge tone={toneForStatus(identity.stateKind)} value={identity.stateKind} />
            <StatusBadge tone={toneForStatus(identity.driftStatus)} value={`drift ${identity.driftStatus}`} />
            <StatusBadge tone={toneForStatus(identity.freshnessStatus)} value={identity.freshnessStatus} />
          </div>
        )}
      />

      <div className="rtc-runtime-identity-grid">
        <div className="rtc-runtime-identity-column">
          <div className="rtc-runtime-identity-keyline">Aktívny beh robota</div>
          <div className="rtc-runtime-identity-run">{identity.runId}</div>
          <div className="rtc-kv rtc-runtime-identity-meta">
            <div className="rtc-kv-row">
              <span>Burza / režim</span>
              <strong>{identity.providerId} / {identity.mode}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Odkiaľ bol vybraný</span>
              <strong>{identity.resolutionSource}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Cesta k dátam</span>
              <strong>{identity.runPath || "nepodarilo sa nájsť"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Dôvodový kód</span>
              <strong>{identity.reasonCode}</strong>
            </div>
          </div>
        </div>

        <div className="rtc-runtime-identity-column">
          <div className="rtc-runtime-identity-signal-grid">
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.pinIntegrityStatus)}>
              <div className="rtc-summary-label">Pevné pripnutie</div>
              <div className="rtc-summary-value">{identity.pinIntegrityStatus}</div>
              <div className="rtc-summary-hint">Ak je beh pripnutý napevno, panel nesmie potichu prejsť inde.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.endpointConsistencyStatus)}>
              <div className="rtc-summary-label">Zhoda dát</div>
              <div className="rtc-summary-value">{identity.endpointConsistencyStatus}</div>
              <div className="rtc-summary-hint">Či sa všetky časti aplikácie pozerajú na ten istý beh.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.replayAlignmentStatus)}>
              <div className="rtc-summary-label">Zhoda s históriou</div>
              <div className="rtc-summary-value">{identity.replayAlignmentStatus}</div>
              <div className="rtc-summary-hint">Aj história a vysvetlenia musia patriť k tomu istému behu.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.freshnessStatus)}>
              <div className="rtc-summary-label">Čerstvosť dát</div>
              <div className="rtc-summary-value">{identity.freshnessAgeLabel}</div>
              <div className="rtc-summary-hint">{identity.lastArtifactUpdateAt || "čaká sa na čas poslednej aktualizácie"}</div>
            </article>
          </div>
        </div>
      </div>

      {identity.issues.length > 0 ? (
        <div className="rtc-pill-row rtc-runtime-identity-issues">
          {identity.issues.map((issue) => (
            <StatusBadge
              key={issue}
              tone={toneForStatus(
                identity.endpointConsistencyStatus === "mismatch"
                || issue.includes("mismatch")
                || issue.includes("unresolved")
                  ? "mismatch"
                  : issue.includes("latest")
                    ? "tracking_latest"
                    : "warn",
              )}
              value={issue}
            />
          ))}
        </div>
      ) : null}

      {showPinnedFailure ? (
        <div className="rtc-banner" data-tone="danger">
          Pripnutý beh sa nepodarilo spoľahlivo nájsť alebo neprešiel kontrolou. Aplikácia ho preto naschvál neukazuje ako zdravý stav.
        </div>
      ) : null}

      {showMismatchBanner ? (
        <div className="rtc-banner" data-tone="danger">
          Niektoré časti aplikácie ukazujú iný beh alebo inú históriu. Kým sa to nezrovná, ber panel ako nekonzistentný.
        </div>
      ) : null}

      {showPinCommand ? (
        <div className="rtc-code">
          {pinCommand}
        </div>
      ) : null}

      <div className="rtc-runtime-selector">
        <SectionHeader
          eyebrow="Výber"
          title="Vyber sledovaný beh"
          subtitle="Tu rozhodneš, či chceš sledovať konkrétny beh robota napevno, alebo len najnovší dostupný beh."
          compact
        />
        <div className="rtc-runtime-selector-grid">
          <label className="rtc-label">
            Dostupné behy
            <select
              className="rtc-select"
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
            >
              {availableRuns.length > 0 ? (
                availableRuns.map((run) => (
                  <option key={run.runId} value={run.runId}>
                    {run.runId} · {run.mode} · {run.stateKind}
                  </option>
                ))
              ) : (
                <option value={identity.runId}>{identity.runId}</option>
              )}
            </select>
          </label>

          <div className="rtc-stack">
            <div className="rtc-button-row">
              <button
                className="rtc-button rtc-button-quiet"
                disabled={selectionPending || !onTrackLatest}
                type="button"
                onClick={() => onTrackLatest?.()}
              >
                {selectionPending ? "Pracujem…" : "Sledovať najnovší"}
              </button>
              <button
                className="rtc-button"
                disabled={selectionPending || !selectedRunId || !onPinRun}
                type="button"
                onClick={() => selectedRunId && onPinRun?.(selectedRunId)}
              >
                {selectionPending ? "Pracujem…" : "Pripnúť vybraný beh"}
              </button>
            </div>

            <div className="rtc-inline-note">
              {runs?.unresolvedSelection
                ? `Aktuálne vybraný cieľ sa nepodarilo nájsť: ${runs.selectionTarget}`
                : `Aktuálne sleduješ: ${runs?.selectionTarget ?? identity.runPath}`}
            </div>

            {selectionResponse ? (
              <div className="rtc-code">
                selectionMode={selectionResponse.selectionMode}
                {"\n"}
                runId={selectionResponse.runId ?? "nenájdené"}
                {"\n"}
                operatorMessage={selectionResponse.operatorMessage}
              </div>
            ) : null}

            {selectionError ? <div className="rtc-banner" data-tone="danger">{selectionError}</div> : null}
          </div>
        </div>

        {availableRuns.length > 0 ? (
          <div className="rtc-runtime-catalog">
            {availableRuns.slice(0, 6).map((run) => (
              <article className="rtc-runtime-catalog-item" key={run.runId}>
                <div className="rtc-live-card-header">
                  <strong>{run.runId}</strong>
                  <div className="rtc-pill-row">
                    {run.current ? <StatusBadge tone="good" value="aktuálny" subtle /> : null}
                    {run.latest ? <StatusBadge tone="info" value="najnovší" subtle /> : null}
                  </div>
                </div>
                <div className="rtc-inline-note">{run.runPath}</div>
                <div className="rtc-live-meta">
                  <span>{run.providerId}</span>
                  <span>{run.mode}</span>
                  <span>{run.stateKind}</span>
                  <span>{run.artifactFreshnessStatus ?? "nedostupné"}</span>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </GlassPanel>
  );
}
