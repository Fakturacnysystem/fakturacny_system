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
        eyebrow="Runtime lock"
        title="Runtime identity"
        subtitle="Effective robot selection is persistent and explicit. No operator should have to infer which run the cockpit is watching."
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
          <div className="rtc-runtime-identity-keyline">Effective run ID</div>
          <div className="rtc-runtime-identity-run">{identity.runId}</div>
          <div className="rtc-kv rtc-runtime-identity-meta">
            <div className="rtc-kv-row">
              <span>Provider / mode</span>
              <strong>{identity.providerId} / {identity.mode}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Resolution source</span>
              <strong>{identity.resolutionSource}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Run path</span>
              <strong>{identity.runPath || "unresolved"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Reason code</span>
              <strong>{identity.reasonCode}</strong>
            </div>
          </div>
        </div>

        <div className="rtc-runtime-identity-column">
          <div className="rtc-runtime-identity-signal-grid">
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.pinIntegrityStatus)}>
              <div className="rtc-summary-label">Pin integrity</div>
              <div className="rtc-summary-value">{identity.pinIntegrityStatus}</div>
              <div className="rtc-summary-hint">Pinned mode must never drift silently.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.endpointConsistencyStatus)}>
              <div className="rtc-summary-label">Endpoint consistency</div>
              <div className="rtc-summary-value">{identity.endpointConsistencyStatus}</div>
              <div className="rtc-summary-hint">Cross-endpoint run truth agreement.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.replayAlignmentStatus)}>
              <div className="rtc-summary-label">Replay alignment</div>
              <div className="rtc-summary-value">{identity.replayAlignmentStatus}</div>
              <div className="rtc-summary-hint">Replay must point at the same effective run.</div>
            </article>
            <article className="rtc-summary-card" data-tone={toneForStatus(identity.freshnessStatus)}>
              <div className="rtc-summary-label">Freshness</div>
              <div className="rtc-summary-value">{identity.freshnessAgeLabel}</div>
              <div className="rtc-summary-hint">{identity.lastArtifactUpdateAt || "awaiting artifact timestamp"}</div>
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
          Pinned run is unresolved or failed integrity checks. The cockpit is refusing to present that state as a healthy target.
        </div>
      ) : null}

      {showMismatchBanner ? (
        <div className="rtc-banner" data-tone="danger">
          Runtime identity mismatch detected across endpoints or replay evidence. Treat the surface as inconsistent until the run selection is reconciled.
        </div>
      ) : null}

      {showPinCommand ? (
        <div className="rtc-code">
          {pinCommand}
        </div>
      ) : null}

      <div className="rtc-runtime-selector">
        <SectionHeader
          eyebrow="Selection"
          title="Run selector"
          subtitle="Observation target stays explicit. Pinned selection never drifts silently, and latest tracking stays visibly non-pinned."
          compact
        />
        <div className="rtc-runtime-selector-grid">
          <label className="rtc-label">
            Available runs
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
                {selectionPending ? "Applying…" : "Track latest"}
              </button>
              <button
                className="rtc-button"
                disabled={selectionPending || !selectedRunId || !onPinRun}
                type="button"
                onClick={() => selectedRunId && onPinRun?.(selectedRunId)}
              >
                {selectionPending ? "Applying…" : "Pin selected run"}
              </button>
            </div>

            <div className="rtc-inline-note">
              {runs?.unresolvedSelection
                ? `Current selection target is unresolved: ${runs.selectionTarget}`
                : `Selection target: ${runs?.selectionTarget ?? identity.runPath}`}
            </div>

            {selectionResponse ? (
              <div className="rtc-code">
                selectionMode={selectionResponse.selectionMode}
                {"\n"}
                runId={selectionResponse.runId ?? "unresolved"}
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
                    {run.current ? <StatusBadge tone="good" value="current" subtle /> : null}
                    {run.latest ? <StatusBadge tone="info" value="latest" subtle /> : null}
                  </div>
                </div>
                <div className="rtc-inline-note">{run.runPath}</div>
                <div className="rtc-live-meta">
                  <span>{run.providerId}</span>
                  <span>{run.mode}</span>
                  <span>{run.stateKind}</span>
                  <span>{run.artifactFreshnessStatus ?? "unavailable"}</span>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </GlassPanel>
  );
}
