import React from "react";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type {
  RuntimeControlAction,
  RuntimeControlResponse,
  ShieldState,
} from "@/types/runtime";
import type { ControlsContract } from "@/types/contracts";
import {
  formatMoment,
  toneFromGuardStatus,
  toneFromSeverity,
  toneFromVerdict,
} from "@/components/screen-formatters";

interface ShieldScreenProps {
  shield: ShieldState;
  controls: ControlsContract;
  actionReason: string;
  onActionReasonChange: (value: string) => void;
  onInvokeControl: (action: RuntimeControlAction) => void;
  pendingAction: RuntimeControlAction | null;
  lastResponse: RuntimeControlResponse | null;
}

export function ShieldScreen({
  shield,
  controls,
  actionReason,
  onActionReasonChange,
  onInvokeControl,
  pendingAction,
  lastResponse,
}: ShieldScreenProps) {
  return (
    <div className="rtc-screen-panel">
      <GlassPanel className="rtc-screen-hero-card" elevated>
        <SectionHeader
          eyebrow="Shield"
          title="Runtime trust and safety surface"
          subtitle="Shield answers one question first: can the operator trust this robot right now. Every verdict is grounded in current runtime evidence, not UI inference."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromVerdict(shield.trustVerdict)} label="trust verdict" value={shield.trustVerdict} />
              <StatusBadge tone={toneFromSeverity(shield.stateKind)} label="runtime state" value={shield.stateKind} />
              <StatusBadge
                tone={
                  shield.runtimeIdentity?.pinIntegrityStatus === "ok"
                    ? "good"
                    : shield.runtimeIdentity?.pinIntegrityStatus === "not_pinned"
                      ? "warn"
                      : "danger"
                }
                label="pin integrity"
                value={shield.runtimeIdentity?.pinIntegrityStatus ?? "unavailable"}
              />
              <StatusBadge
                tone={shield.runtimeIdentity?.driftStatus === "locked" ? "good" : "warn"}
                label="drift"
                value={shield.runtimeIdentity?.driftStatus ?? "unavailable"}
              />
            </div>
          )}
        />
        <div className="rtc-inline-note">updated {formatMoment(shield.lastUpdatedAt)}</div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Trust"
            title="Trust Verdict"
            subtitle="Critical reasons stay visible at the top. Unsafe or cautionary posture is never hidden behind green summary cards."
          />
          <div className="rtc-summary-grid">
            <article className="rtc-summary-card" data-tone={toneFromVerdict(shield.trustVerdict)}>
              <div className="rtc-summary-label">Verdict</div>
              <div className="rtc-summary-value">{shield.trustVerdict}</div>
              <div className="rtc-summary-hint">Active operator trust posture for the selected run.</div>
            </article>
            <article className="rtc-summary-card" data-tone={shield.runtimeIdentity?.artifactFreshness?.status === "stale" ? "danger" : "info"}>
              <div className="rtc-summary-label">Freshness</div>
              <div className="rtc-summary-value">{shield.runtimeIdentity?.artifactFreshness?.status ?? shield.stateKind}</div>
              <div className="rtc-summary-hint">Artifact freshness is consumed from runtime identity, not recomputed in the UI.</div>
            </article>
          </div>
          <div className="rtc-pill-row">
            {shield.trustReasons.length > 0 ? (
              shield.trustReasons.map((reason) => (
                <StatusBadge key={reason} tone={toneFromSeverity(reason)} value={reason} />
              ))
            ) : (
              <StatusBadge tone="good" value="no active trust degraders" />
            )}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Safety"
            title="Runtime Safety State"
            subtitle="These rows answer whether the robot is safe to operate: identity lock, freshness, execution gate, market integrity, exchange connectivity, and permission path."
          />
          <div className="rtc-state-grid">
            {shield.runtimeSafety.map((item) => (
              <article className="rtc-state-card" key={item.label}>
                <div className="rtc-live-card-header">
                  <strong>{item.label}</strong>
                  <StatusBadge tone={toneFromVerdict(item.status)} value={item.status} subtle />
                </div>
                <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                <div>{item.detail}</div>
                <ul className="rtc-list rtc-tight-list">
                  {item.evidence.length > 0 ? item.evidence.map((evidence) => <li key={`${item.label}-${evidence}`}>{evidence}</li>) : <li>No linked evidence</li>}
                </ul>
              </article>
            ))}
          </div>
        </GlassPanel>
      </section>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Promotion"
          title="Promotion / rollback posture"
          subtitle="Shield surfaces promotion score, rollback trigger state, recovery mode, and stream health so rollout decisions stay evidence-bound and reversible."
        />
        {shield.performanceControl ? (
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Promotion score</span>
              <strong>{shield.performanceControl.promotionScore == null ? "Unavailable" : shield.performanceControl.promotionScore.toFixed(3)}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Promotion status</span>
              <strong>{shield.performanceControl.promotionStatus ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Rollback triggered</span>
              <strong>{shield.performanceControl.rollbackTriggered == null ? "Unavailable" : shield.performanceControl.rollbackTriggered ? "yes" : "no"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Recovery mode</span>
              <strong>{shield.performanceControl.recoveryMode ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Live degradation</span>
              <strong>{shield.performanceControl.liveDegradationStatus ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Self throttling</span>
              <strong>
                {shield.performanceControl.selfThrottlingActive == null
                  ? "Unavailable"
                  : shield.performanceControl.selfThrottlingActive
                    ? "active"
                    : "inactive"}
              </strong>
            </div>
            <div className="rtc-kv-row">
              <span>Private stream health</span>
              <strong>{shield.performanceControl.privateStreamHealth ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Authority boundary</span>
              <strong>{shield.performanceControl.authorityBoundary ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Rollback risk</span>
              <strong>{shield.performanceControl.rollbackRisk ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Target plausibility</span>
              <strong>{shield.performanceControl.targetPlausibility ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Target gap (net bps)</span>
              <strong>
                {shield.performanceControl.targetGapNetBps == null
                  ? "Unavailable"
                  : shield.performanceControl.targetGapNetBps.toFixed(1)}
              </strong>
            </div>
            <div className="rtc-kv-row">
              <span>Readiness status</span>
              <strong>{shield.performanceControl.readinessStatus ?? "Unavailable"}</strong>
            </div>
          </div>
        ) : (
          <div className="rtc-inline-note">Promotion and rollback telemetry is not available for the active run.</div>
        )}
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Guards"
            title="Guard Matrix"
            subtitle="Configured thresholds and observed values remain side by side. If either side is missing, the row stays unavailable instead of pretending the guard passed."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Guard</th>
                  <th>Threshold</th>
                  <th>Observed</th>
                  <th>Status</th>
                  <th>Impact</th>
                  <th>Evidence</th>
                  <th>Last triggered</th>
                </tr>
              </thead>
              <tbody>
                {shield.guardMatrix.length > 0 ? (
                  shield.guardMatrix.map((guard) => (
                    <tr key={guard.name}>
                      <td>
                        <strong>{guard.name}</strong>
                        {guard.derived ? <div className="rtc-inline-note">derived comparison</div> : null}
                      </td>
                      <td>{guard.configuredThreshold}</td>
                      <td>{guard.observedValue}</td>
                      <td>
                        <StatusBadge tone={toneFromGuardStatus(guard.status)} value={guard.status} subtle />
                      </td>
                      <td>{guard.impact}</td>
                      <td>
                        <ul className="rtc-list rtc-tight-list">
                          {guard.evidence.length > 0 ? guard.evidence.map((item) => <li key={`${guard.name}-${item}`}>{item}</li>) : <li>No evidence</li>}
                        </ul>
                      </td>
                      <td>{guard.lastTriggeredAt ? formatMoment(guard.lastTriggeredAt) : "Unavailable"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>No guard matrix payload is available.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel tone="warn" interactive>
          <SectionHeader
            eyebrow="Control"
            title="Control Safety Panel"
            subtitle="Typed actions remain provenance-aware. If the runtime cannot prove operator identity or auditability, the buttons stay blocked and the reason remains visible."
          />
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Control status</span>
              <strong>{controls.statusLine}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Provenance</span>
              <strong>{controls.provenanceLine}</strong>
            </div>
          </div>
          <label className="rtc-label">
            Action reason
            <input
              className="rtc-input"
              value={actionReason}
              onChange={(event) => onActionReasonChange(event.target.value)}
            />
          </label>
          <div className="rtc-command-grid">
            {controls.actions.map((control) => (
              <button
                className="rtc-button"
                data-variant={control.tone === "danger" ? "danger" : undefined}
                disabled={!control.enabled || pendingAction === control.action}
                key={control.action}
                title={control.disabledReason}
                type="button"
                onClick={() => onInvokeControl(control.action)}
              >
                {pendingAction === control.action ? "Sending..." : control.label}
              </button>
            ))}
          </div>
          {lastResponse ? (
            <div className="rtc-code">
              status={lastResponse.status}
              {"\n"}
              effectiveState={lastResponse.effectiveState}
              {"\n"}
              operatorMessage={lastResponse.operatorMessage}
              {"\n"}
              auditReference={lastResponse.auditReference ?? "n/a"}
            </div>
          ) : (
            <p className="rtc-inline-note">No safety action has been sent from this session yet.</p>
          )}
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Applied control</span>
              <strong>{shield.appliedControl ? `${shield.appliedControl.action} via ${shield.appliedControl.controlSurface}` : "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Forced risk mode</span>
              <strong>{shield.appliedControl?.forcedRiskMode ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Queued command</span>
              <strong>{shield.queuedCommand ? `${shield.queuedCommand.action} / ${shield.queuedCommand.effectiveState}` : "None queued"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>User stream</span>
              <strong>{shield.userStream.status}</strong>
            </div>
          </div>
          {shield.appliedControl?.reasons.length ? (
            <div className="rtc-pill-row">
              {shield.appliedControl.reasons.map((reason) => (
                <StatusBadge key={reason} tone="warn" value={reason} />
              ))}
            </div>
          ) : null}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Truth"
            title="Integrity / Truth"
            subtitle="Shield keeps the core truth questions explicit: which run is selected, whether drift exists, how fresh the evidence is, and whether endpoint/replay integrity remains aligned."
          />
          <ul className="rtc-list rtc-tight-list">
            {shield.truthNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Selection mode</span>
              <strong>{shield.runtimeIdentity?.runSelectionMode ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Run path</span>
              <strong>{shield.runtimeIdentity?.runPath ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Pin integrity</span>
              <strong>{shield.runtimeIdentity?.pinIntegrityStatus ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Drift status</span>
              <strong>{shield.runtimeIdentity?.driftStatus ?? "unavailable"}</strong>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Artifacts"
            title="Linked Evidence"
            subtitle="These files back the shield verdict directly. Operators can move from UI posture to concrete runtime artifacts without guesswork."
          />
          <div className="rtc-pill-row">
            {shield.linkedArtifacts.length > 0 ? (
              shield.linkedArtifacts.map((artifact) => (
                <StatusBadge key={artifact} tone="info" value={artifact} />
              ))
            ) : (
              <StatusBadge tone="warn" value="no linked artifacts" />
            )}
          </div>
        </GlassPanel>
      </section>
    </div>
  );
}
