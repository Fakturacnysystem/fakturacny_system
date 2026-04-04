"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { BrainScreen } from "@/components/brain-screen";
import { ExecutionScreen } from "@/components/execution-screen";
import { RuntimeIdentityCard } from "@/components/runtime-identity-card";
import { ShieldScreen } from "@/components/shield-screen";
import { UiInferenceOversight } from "@/components/ui-inference-oversight";
import { AppShell, type AppShellTab } from "@/components/ui/app-shell";
import { CommandButton } from "@/components/ui/command-button";
import { ConfirmationSheet } from "@/components/ui/confirmation-sheet";
import { FloatingActionBar } from "@/components/ui/floating-action-bar";
import { EmptyState, SkeletonState } from "@/components/ui/states";
import { GlassPanel, LiveFeedList, MetricCard, SectionHeader, StatusBadge } from "@/components/ui/surface";
import { useScreenContracts } from "@/lib/contracts/use-screen-contracts";
import { staggerContainer } from "@/lib/ui/motion";
import type { RuntimeControlAction } from "@/types/runtime";
import {
  formatMoment,
  toneFromSeverity,
  toneFromVerdict,
} from "@/components/screen-formatters";

type ScreenId = "command" | "brain" | "shield" | "execution";

interface ControlCopy {
  icon: string;
  tone: "good" | "warn" | "danger" | "info";
  detail: string;
  confirmTitle: string;
  confirmSubtitle: string;
  confirmLabel: string;
  requiresConfirmation: boolean;
}

const controlCopy: Record<RuntimeControlAction, ControlCopy> = {
  pause: {
    icon: "∥",
    tone: "warn",
    detail: "Block new entries while preserving live telemetry and runtime visibility.",
    confirmTitle: "Pause new entries",
    confirmSubtitle: "This keeps the robot observable but stops additional entry flow until the operator explicitly resumes.",
    confirmLabel: "Pause entries",
    requiresConfirmation: true,
  },
  resume: {
    icon: "→",
    tone: "good",
    detail: "Return to guarded normal execution posture.",
    confirmTitle: "Resume guarded execution",
    confirmSubtitle: "Resume only after reviewing blockers, trust posture, and effective run identity.",
    confirmLabel: "Resume",
    requiresConfirmation: false,
  },
  freeze: {
    icon: "✦",
    tone: "danger",
    detail: "Stop runtime execution while keeping diagnostic and safety surfaces available.",
    confirmTitle: "Freeze runtime execution",
    confirmSubtitle: "Freeze is a safety intervention. Use it when current alerts or trust posture imply continued execution is unsafe.",
    confirmLabel: "Freeze runtime",
    requiresConfirmation: true,
  },
  flatten: {
    icon: "↓",
    tone: "danger",
    detail: "Request immediate reduction of live exposure and collapse risk posture.",
    confirmTitle: "Flatten live exposure",
    confirmSubtitle: "Flatten is destructive by design. Confirm only if the active run must exit exposure immediately.",
    confirmLabel: "Flatten exposure",
    requiresConfirmation: true,
  },
};

function parseScreenHash(hash: string): ScreenId {
  const value = hash.replace(/^#/, "").trim().toLowerCase();
  if (value === "brain" || value === "shield" || value === "execution") {
    return value;
  }
  return "command";
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || target.isContentEditable
  );
}

function toneFromStateKind(stateKind: string) {
  if (["error", "unavailable", "unresolved"].includes(stateKind)) {
    return "danger" as const;
  }
  if (["stale", "degraded"].includes(stateKind)) {
    return "warn" as const;
  }
  if (stateKind === "partial") {
    return "info" as const;
  }
  return "good" as const;
}

function EmptyTableRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan}>{message}</td>
    </tr>
  );
}

export function RobotControlCenterApp() {
  const { contract, actions, errors, runtimeControls, runSelection, incidentWriter, queries } = useScreenContracts();
  const [operatorId, setOperatorId] = useState("ops.mh");
  const [displayName, setDisplayName] = useState("Martin Holik");
  const [role, setRole] = useState("operator");
  const [actionReason, setActionReason] = useState("manual_operator_review");
  const [incidentSeverity, setIncidentSeverity] = useState("SEV-2");
  const [incidentTags, setIncidentTags] = useState("manual-review,replay");
  const [incidentNote, setIncidentNote] = useState(
    "Observed degraded runtime API posture. Control action reason and replay follow-up documented.",
  );
  const [activeScreen, setActiveScreen] = useState<ScreenId>("command");
  const [confirmAction, setConfirmAction] = useState<RuntimeControlAction | null>(null);
  const deferredIncidentNote = useDeferredValue(incidentNote);

  const dashboard = contract.dashboard;
  const controls = contract.controls;
  const replay = contract.replay;
  const release = contract.release;
  const shield = contract.shield;
  const featuredSymbols = dashboard.symbols.slice(0, 3);
  const featuredDecisions = dashboard.decisions.slice(0, 3);
  const pinCommand = `cd /Users/martinholik/Projects/fakturacny_system/apps/robot-control-center && RUNTIME_API_RUN_ID=${contract.runtimeIdentity.runId} npm run runtime:api`;
  const runs = queries.runs.data ?? null;

  const controlButtons = useMemo(
    () => {
      const byAction = new Map(controls.actions.map((action) => [action.action, action]));
      return ["pause", "resume", "freeze", "flatten"]
        .map((action) => byAction.get(action as RuntimeControlAction))
        .filter((action): action is NonNullable<typeof action> => Boolean(action));
    },
    [controls.actions],
  );

  const refreshAll = useCallback(() => {
    queries.summary.refresh();
    queries.runs.refresh();
    queries.symbols.refresh();
    queries.decisions.refresh();
    queries.alerts.refresh();
    queries.health.refresh();
    queries.integrity.refresh();
    queries.brain.refresh();
    queries.shield.refresh();
    queries.execution.refresh();
    queries.replay.refresh();
  }, [queries]);

  const invokeControl = useCallback(
    (action: RuntimeControlAction) => {
      void actions.invokeControl(action, actionReason.trim() || "manual_operator_review");
    },
    [actionReason, actions],
  );

  const requestControl = useCallback(
    (action: RuntimeControlAction) => {
      if (controlCopy[action].requiresConfirmation) {
        setConfirmAction(action);
        return;
      }
      invokeControl(action);
    },
    [invokeControl],
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const syncFromHash = () => setActiveScreen(parseScreenHash(window.location.hash));
    const onKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "1") {
        event.preventDefault();
        setActiveScreen("command");
      } else if (key === "2") {
        event.preventDefault();
        setActiveScreen("brain");
      } else if (key === "3") {
        event.preventDefault();
        setActiveScreen("shield");
      } else if (key === "4") {
        event.preventDefault();
        setActiveScreen("execution");
      } else if (key === "r") {
        event.preventDefault();
        refreshAll();
      }
    };

    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("hashchange", syncFromHash);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [refreshAll]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const nextHash = `#${activeScreen}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, [activeScreen]);

  const screenTabs: AppShellTab[] = [
    {
      id: "command",
      label: "Command Center",
      detail: `${dashboard.mode} / ${dashboard.healthState.status}`,
      tone: toneFromStateKind(dashboard.healthState.status),
      hotkey: "1",
    },
    {
      id: "brain",
      label: "Brain",
      detail: `${contract.brain.selectedSymbol} / ${contract.brain.actionState}`,
      tone: toneFromStateKind(contract.brain.stateKind),
      hotkey: "2",
    },
    {
      id: "shield",
      label: "Shield",
      detail: `trust ${contract.shield.trustVerdict}`,
      tone: toneFromVerdict(contract.shield.trustVerdict),
      hotkey: "3",
    },
    {
      id: "execution",
      label: "Execution",
      detail: `${contract.execution.orders.length} orders / ${contract.execution.positions.length} positions`,
      tone: toneFromStateKind(contract.execution.stateKind),
      hotkey: "4",
    },
  ];

  const floatingBar = (
    <FloatingActionBar
      title="Operator action zone"
      subtitle="Controls remain reason-coded and audit-preserving. Destructive actions are separated, sticky, and never visually mixed with routine operations."
      status={(
        <div className="rtc-pill-row">
          <StatusBadge tone={toneFromStateKind(dashboard.healthState.status)} label="runtime" value={dashboard.healthState.status} />
          <StatusBadge tone={toneFromVerdict(shield.trustVerdict)} label="trust" value={shield.trustVerdict} />
        </div>
      )}
      primary={(
        <>
          {controlButtons
            .filter((control) => control.tone !== "danger")
            .map((control) => (
              <CommandButton
                key={control.action}
                label={control.label}
                tone={controlCopy[control.action].tone}
                icon={controlCopy[control.action].icon}
                detail={control.enabled ? controlCopy[control.action].detail : control.disabledReason}
                pending={runtimeControls.pendingAction === control.action}
                disabled={!control.enabled}
                title={control.disabledReason}
                onClick={() => requestControl(control.action)}
              />
            ))}
        </>
      )}
      danger={(
        <>
          {controlButtons
            .filter((control) => control.tone === "danger")
            .map((control) => (
              <CommandButton
                key={control.action}
                label={control.label}
                tone="danger"
                icon={controlCopy[control.action].icon}
                detail={control.enabled ? controlCopy[control.action].detail : control.disabledReason}
                pending={runtimeControls.pendingAction === control.action}
                disabled={!control.enabled}
                title={control.disabledReason}
                onClick={() => requestControl(control.action)}
              />
            ))}
        </>
      )}
      aside={(
        <div className="rtc-floating-bar-side-stack">
          <div className="rtc-inline-note">
            Applied: {shield.appliedControl ? `${shield.appliedControl.action} via ${shield.appliedControl.controlSurface}` : "unavailable"}
          </div>
          <button className="rtc-button rtc-button-quiet" type="button" onClick={refreshAll}>
            Refresh telemetry
          </button>
        </div>
      )}
    />
  );

  const missionDeck = (
    <GlassPanel className="rtc-hero rtc-screen-hero-card" elevated>
      <SectionHeader
        eyebrow="Mission deck"
        title="Runtime posture at a glance"
        subtitle="The shell keeps effective run identity, health posture, live quote fabric, and active decision pressure readable in under two seconds."
        meta={(
          <div className="rtc-pill-row">
            <StatusBadge tone={dashboard.source === "runtime-api" ? "good" : "danger"} label="source" value={dashboard.source} />
            <StatusBadge tone={toneFromStateKind(contract.runtimeIdentity.stateKind)} label="state" value={contract.runtimeIdentity.stateKind} />
            <StatusBadge tone={contract.runtimeIdentity.selectionMode === "pinned" ? "good" : "warn"} label="selection" value={contract.runtimeIdentity.selectionMode} />
          </div>
        )}
        actions={(
          <button className="rtc-button rtc-button-quiet" type="button" onClick={refreshAll}>
            Refresh runtime
          </button>
        )}
      />

      <div className="rtc-badges">
        {dashboard.badges.map((badge) => (
          <StatusBadge key={`${badge.label}-${badge.value}`} tone={badge.tone} label={badge.label} value={badge.value} />
        ))}
      </div>

      <motion.div className="rtc-metric-grid" initial="initial" animate="animate" variants={staggerContainer(0.07, 0.06)}>
        {dashboard.metrics.map((metric, index) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            value={metric.value}
            hint={metric.hint}
            tone={metric.tone}
            emphasis={index === 0}
          />
        ))}
      </motion.div>

      <div className="rtc-live-ribbon">
        <LiveFeedList
          title="Market monitor"
          subtitle="Direct quote path, latency, spread, and staleness for the leading symbols in the active run."
          items={featuredSymbols}
          empty={(
            <EmptyState
              title="No live symbol snapshots"
              description="The active run has not emitted symbol snapshots yet."
            />
          )}
          renderItem={(symbol) => (
            <article className="rtc-feed-card rtc-live-card" key={`${symbol.symbol}-${symbol.ts}`}>
              <div className="rtc-live-card-header">
                <strong>{symbol.symbol}</strong>
                <StatusBadge tone={symbol.stale ? "warn" : "good"} value={symbol.stale ? "stale" : "live"} subtle />
              </div>
              <div className="rtc-live-price">
                {symbol.bid.toFixed(2)} <span>/</span> {symbol.ask.toFixed(2)}
              </div>
              <div className="rtc-live-meta">
                <span>{symbol.venue}</span>
                <span>{symbol.spreadBps.toFixed(2)} bps</span>
                <span>{symbol.latencyMs} ms</span>
                <span>q {symbol.qualityScore.toFixed(1)}</span>
              </div>
            </article>
          )}
        />

        <LiveFeedList
          title="Decision pressure"
          subtitle="Latest intent, risk verdict, and top reasons remain visible before the operator enters deeper replay or explainability screens."
          items={featuredDecisions}
          empty={(
            <EmptyState
              title="No decision records"
              description="The active run has not emitted decision rows yet."
            />
          )}
          renderItem={(decision) => (
            <article className="rtc-feed-card rtc-quick-decision" key={decision.id}>
              <div className="rtc-live-card-header">
                <strong>{decision.symbol}</strong>
                <StatusBadge tone={toneFromVerdict(decision.riskVerdict)} value={decision.riskVerdict} subtle />
              </div>
              <div className="rtc-decision-intent">{decision.intent}</div>
              <div className="rtc-live-meta">
                <span>conf {decision.confidence.toFixed(2)}</span>
                <span>edge {decision.expectedEdgeBps.toFixed(1)} bps</span>
              </div>
              <div className="rtc-inline-note">{decision.topReasons.join(", ") || "no blockers"}</div>
            </article>
          )}
        />
      </div>
    </GlassPanel>
  );

  const bootstrapping = queries.summary.isLoading && !queries.summary.data;

  const commandCenterScreen = bootstrapping ? (
    <div className="rtc-screen-panel">
      <GlassPanel>
        <SectionHeader
          eyebrow="Loading"
          title="Bootstrapping cockpit"
          subtitle="Waiting for authoritative runtime payloads before rendering the operator surface."
        />
        <SkeletonState blocks={4} />
      </GlassPanel>
    </div>
  ) : (
    <div className="rtc-screen-panel">
      <section className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Identity"
            title="Operator session"
            subtitle="Local persisted identity is explicit, not hidden. POST controls and incident notes stay blocked until a named operator session is bound."
          />

          <div className="rtc-auth-grid">
            <form
              className="rtc-form"
              onSubmit={(event) => {
                event.preventDefault();
                actions.setIdentity({
                  operatorId,
                  displayName,
                  role,
                  authSource: "local",
                  expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
                });
              }}
            >
              <div className="rtc-form-grid">
                <label className="rtc-label">
                  Operator ID
                  <input className="rtc-input" value={operatorId} onChange={(event) => setOperatorId(event.target.value)} />
                </label>
                <label className="rtc-label">
                  Display name
                  <input className="rtc-input" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
                </label>
              </div>

              <label className="rtc-label">
                Role
                <select className="rtc-select" value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="operator">operator</option>
                  <option value="admin">admin</option>
                  <option value="observer">observer</option>
                </select>
              </label>

              <div className="rtc-button-row">
                <button className="rtc-button" type="submit">
                  Persist operator session
                </button>
                <button className="rtc-button rtc-button-quiet" type="button" onClick={() => actions.clearIdentity()}>
                  Clear session
                </button>
              </div>
            </form>

            <div className="rtc-stack">
              <div className="rtc-operator-summary">
                <div className="rtc-operator-avatar" aria-hidden="true">
                  {dashboard.authSummary.operatorLabel.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="rtc-operator-name">{dashboard.authSummary.operatorLabel}</div>
                  <div className="rtc-inline-note">
                    {dashboard.authSummary.role} / {dashboard.authSummary.authSource}
                  </div>
                </div>
              </div>

              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Status</span>
                  <strong>{dashboard.authSummary.status}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Session ID</span>
                  <strong>{dashboard.authSummary.sessionId}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Control posture</span>
                  <strong>{controls.statusLine}</strong>
                </div>
              </div>

              <div className="rtc-banner">
                Destructive controls are blocked unless session status is <strong>active</strong>. This protects audit provenance and avoids anonymous command paths.
              </div>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel tone="warn" interactive>
          <SectionHeader
            eyebrow="Command"
            title="Control confirmation"
            subtitle="Routine and destructive actions stay separated. Runtime acknowledgement and currently applied control remain visible together."
            meta={(
              <div className="rtc-pill-row">
                <StatusBadge
                  tone={runtimeControls.pendingAction ? "warn" : "good"}
                  label="send state"
                  value={runtimeControls.pendingAction ? "pending" : "idle"}
                />
              </div>
            )}
          />

          <label className="rtc-label">
            Reason text
            <input className="rtc-input" value={actionReason} onChange={(event) => setActionReason(event.target.value)} />
          </label>

          <div className="rtc-command-grid">
            {controls.actions.map((control) => (
              <CommandButton
                key={control.action}
                label={control.label}
                tone={controlCopy[control.action].tone}
                icon={controlCopy[control.action].icon}
                detail={control.enabled ? controlCopy[control.action].detail : control.disabledReason}
                pending={runtimeControls.pendingAction === control.action}
                disabled={!control.enabled}
                title={control.disabledReason}
                onClick={() => requestControl(control.action)}
              />
            ))}
          </div>

          {controls.lastResponse ? (
            <div className="rtc-code">
              status={controls.lastResponse.status}
              {"\n"}
              effectiveState={controls.lastResponse.effectiveState}
              {"\n"}
              operatorMessage={controls.lastResponse.operatorMessage}
              {"\n"}
              auditReference={controls.lastResponse.auditReference ?? "n/a"}
            </div>
          ) : (
            <p className="rtc-inline-note">No control action sent yet.</p>
          )}

          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Applied runtime control</span>
              <strong>{shield.appliedControl ? `${shield.appliedControl.action} via ${shield.appliedControl.controlSurface}` : "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Forced risk mode</span>
              <strong>{shield.appliedControl?.forcedRiskMode ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Queued operator command</span>
              <strong>{shield.queuedCommand ? `${shield.queuedCommand.action} / ${shield.queuedCommand.effectiveState}` : "none queued"}</strong>
            </div>
          </div>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-three">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Health"
            title="Runtime health"
            subtitle="Bridge, backend, and artifact-fallback state stay explicit so runtime degradation is immediately visible."
          />
          <ul className="rtc-list rtc-tight-list">
            {dashboard.warnings.length > 0 ? dashboard.warnings.map((warning) => <li key={warning}>{warning}</li>) : <li>no active warnings</li>}
          </ul>
          <div className="rtc-kv">
            {dashboard.healthDetails.map((detail) => (
              <div className="rtc-kv-row" key={detail.label}>
                <span>{detail.label}</span>
                <strong>{detail.value}</strong>
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel tone={dashboard.blockers.length > 0 ? "danger" : "good"} interactive>
          <SectionHeader
            eyebrow="Integrity"
            title="Operational integrity"
            subtitle="Blockers are first-class. Anything ambiguous stays visible until the runtime can prove otherwise."
          />
          <div className="rtc-pill-row">
            {dashboard.blockers.length > 0
              ? dashboard.blockers.map((blocker) => (
                  <StatusBadge key={blocker} tone="danger" value={blocker} />
                ))
              : <StatusBadge tone="good" value="no blockers" />}
          </div>
          <div className="rtc-kv">
            {dashboard.integrityDetails.map((detail) => (
              <div className="rtc-kv-row" key={detail.label}>
                <span>{detail.label}</span>
                <strong>{detail.value}</strong>
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Forensics"
            title="Incident note"
            subtitle="Note-writing follows the same operator provenance rules as controls and stays coupled to the replay run."
          />
          <form
            className="rtc-form"
            onSubmit={(event) => {
              event.preventDefault();
              void actions.submitIncidentNote({
                runId: replay.runId,
                operatorId,
                note: incidentNote,
                severity: incidentSeverity,
                tags: incidentTags
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              });
            }}
          >
            <div className="rtc-form-grid">
              <label className="rtc-label">
                Severity
                <select className="rtc-select" value={incidentSeverity} onChange={(event) => setIncidentSeverity(event.target.value)}>
                  <option value="SEV-1">SEV-1</option>
                  <option value="SEV-2">SEV-2</option>
                  <option value="SEV-3">SEV-3</option>
                </select>
              </label>
              <label className="rtc-label">
                Tags
                <input className="rtc-input" value={incidentTags} onChange={(event) => setIncidentTags(event.target.value)} />
              </label>
            </div>

            <label className="rtc-label">
              Note
              <textarea className="rtc-textarea" value={incidentNote} onChange={(event) => setIncidentNote(event.target.value)} />
            </label>

            <div className="rtc-inline-note">Deferred preview length: {deferredIncidentNote.length} characters.</div>

            <div className="rtc-button-row">
              <button className="rtc-button" disabled={!controls.canWriteIncidentNotes || incidentWriter.pending} type="submit">
                {incidentWriter.pending ? "Submitting…" : "Write incident note"}
              </button>
            </div>

            {incidentWriter.lastResponse ? (
              <div className="rtc-code">
                noteId={incidentWriter.lastResponse.noteId ?? "n/a"}
                {"\n"}
                operatorMessage={incidentWriter.lastResponse.operatorMessage}
                {"\n"}
                auditReference={incidentWriter.lastResponse.auditReference ?? "n/a"}
              </div>
            ) : null}
          </form>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Market"
            title="Market monitor"
            subtitle="Symbols and decisions are separated so stale or blocked surfaces cannot masquerade as healthy."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Venue</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Spread bps</th>
                  <th>Latency</th>
                  <th>Quality</th>
                  <th>Stale</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.symbols.length > 0 ? (
                  dashboard.symbols.map((symbol) => (
                    <tr key={symbol.symbol}>
                      <td>{symbol.symbol}</td>
                      <td>{symbol.venue}</td>
                      <td>{symbol.bid.toFixed(2)}</td>
                      <td>{symbol.ask.toFixed(2)}</td>
                      <td>{symbol.spreadBps.toFixed(1)}</td>
                      <td>{symbol.latencyMs} ms</td>
                      <td>{symbol.qualityScore.toFixed(2)}</td>
                      <td>
                        <StatusBadge tone={symbol.stale ? "warn" : "good"} value={symbol.stale ? "yes" : "no"} subtle />
                      </td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={8} message="No market snapshots are currently available." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Decision"
            title="Decision feed"
            subtitle="Risk verdicts, blockers, and last actions remain explicit so control operators can challenge the runtime instead of trusting summaries."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Intent</th>
                  <th>Confidence</th>
                  <th>Edge</th>
                  <th>Verdict</th>
                  <th>Blockers</th>
                  <th>Last action</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.decisions.length > 0 ? (
                  dashboard.decisions.map((decision) => (
                    <tr key={decision.id}>
                      <td>{decision.symbol}</td>
                      <td>{decision.intent}</td>
                      <td>{decision.confidence.toFixed(2)}</td>
                      <td>{decision.expectedEdgeBps} bps</td>
                      <td>
                        <StatusBadge tone={toneFromVerdict(decision.riskVerdict)} value={decision.riskVerdict} subtle />
                      </td>
                      <td>{decision.blockers.join(", ") || "none"}</td>
                      <td>{decision.lastAction}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={7} message="No decision records are currently available." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Alerts"
            title="Alert feed"
            subtitle="Critical alerts should bias toward freeze or flatten, not silent continuation."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Module</th>
                  <th>Message</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.alerts.length > 0 ? (
                  dashboard.alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>
                        <StatusBadge tone={toneFromSeverity(alert.severity)} value={alert.severity} subtle />
                      </td>
                      <td>{alert.module}</td>
                      <td>{alert.message}</td>
                      <td>{formatMoment(alert.ts)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={4} message="No alerts are currently available." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Replay"
            title="Replay lab"
            subtitle="Forensics surfaces remain attached to the active run so incident review starts from evidence, not memory."
          />
          <div className="rtc-badges">
            {replay.summary.map((badge) => (
              <StatusBadge key={`${badge.label}-${badge.value}`} tone={badge.tone} label={badge.label} value={badge.value} />
            ))}
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Timeline</h3>
              <div className="rtc-timeline">
                {replay.timeline.map((item) => (
                  <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>
                    <div className="rtc-inline-note">{item.ts}</div>
                    <div>{item.detail}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Incidents</h3>
              <div className="rtc-timeline">
                {replay.incidents.map((item) => (
                  <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>
                    <div className="rtc-inline-note">{item.ts}</div>
                    <div>{item.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Analog matches</h3>
              <ul className="rtc-list">
                {replay.analogMatches.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>: {item.detail}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Counterfactuals</h3>
              <ul className="rtc-list">
                {replay.counterfactuals.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>: {item.detail}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">PnL attribution</h3>
              <ul className="rtc-list">
                {replay.pnlAttribution.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>: {item.detail}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Notes</h3>
              <ul className="rtc-list">
                {replay.notes.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{item.label}</strong>: {item.detail}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Runbook"
            title="Runbook alignment"
            subtitle="Procedures are visible in-product so operator action, incident notes, and replay review stay coupled."
          />
          <div className="rtc-procedure-grid">
            {contract.runbook.procedures.map((procedure) => (
              <GlassPanel key={procedure.title} compact className="rtc-nested-panel" interactive>
                <SectionHeader title={procedure.title} subtitle={procedure.whenToUse.join(" · ")} compact />
                <ol className="rtc-list">
                  {procedure.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </GlassPanel>
            ))}
          </div>
          <h3 className="rtc-section-title">Replay checklist</h3>
          <ol className="rtc-list">
            {contract.runbook.replayChecklist.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Release"
            title="macOS release readiness"
            subtitle="This path is scriptable and explicit, but still blocked on Apple-controlled external inputs."
          />
          <div className="rtc-release-grid">
            <div>
              <div className="rtc-pill-row">
                <StatusBadge tone={release.status === "ready" ? "good" : "warn"} value={`release status: ${release.status}`} />
                <StatusBadge tone="info" value={`bundleId: ${release.bundleId}`} />
              </div>
              <div className="rtc-kv">
                {release.checklist.map((item) => (
                  <div className="rtc-kv-row" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.satisfied ? "configured" : item.detail}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Exact commands</h3>
              <div className="rtc-code">{release.exactCommands.join("\n")}</div>
              {release.missingInputs.length > 0 ? (
                <>
                  <h3 className="rtc-section-title">Missing external inputs</h3>
                  <ul className="rtc-list">
                    {release.missingInputs.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          </div>
        </GlassPanel>
      </section>
    </div>
  );

  const activeScreenLoading =
    (activeScreen === "brain" && queries.brain.isLoading && !queries.brain.data)
    || (activeScreen === "shield" && queries.shield.isLoading && !queries.shield.data)
    || (activeScreen === "execution" && queries.execution.isLoading && !queries.execution.data);

  let screenContent: ReactNode = commandCenterScreen;
  if (activeScreen === "brain") {
    screenContent = activeScreenLoading
      ? (
          <GlassPanel>
            <SectionHeader
              eyebrow="Loading"
              title="Loading brain evidence"
              subtitle="Waiting for decision and explainability artifacts."
            />
            <SkeletonState blocks={3} />
          </GlassPanel>
        )
      : <BrainScreen brain={contract.brain} />;
  } else if (activeScreen === "shield") {
    screenContent = activeScreenLoading
      ? (
          <GlassPanel>
            <SectionHeader
              eyebrow="Loading"
              title="Loading shield posture"
              subtitle="Waiting for safety, guard, and trust evidence."
            />
            <SkeletonState blocks={3} />
          </GlassPanel>
        )
      : (
          <ShieldScreen
            shield={contract.shield}
            controls={controls}
            actionReason={actionReason}
            onActionReasonChange={setActionReason}
            onInvokeControl={requestControl}
            pendingAction={runtimeControls.pendingAction}
            lastResponse={runtimeControls.lastResponse}
          />
        );
  } else if (activeScreen === "execution") {
    screenContent = activeScreenLoading
      ? (
          <GlassPanel>
            <SectionHeader
              eyebrow="Loading"
              title="Loading execution telemetry"
              subtitle="Waiting for order, venue, and account artifacts."
            />
            <SkeletonState blocks={3} />
          </GlassPanel>
        )
      : <ExecutionScreen execution={contract.execution} />;
  }

  return (
    <>
      <AppShell
        activeScreen={activeScreen}
        screenTabs={screenTabs}
        onSelectScreen={(screen) => setActiveScreen(screen as ScreenId)}
        runtimeIdentity={(
          <RuntimeIdentityCard
            identity={contract.runtimeIdentity}
            pinCommand={pinCommand}
            runs={runs}
            selectionPending={runSelection.pending}
            selectionError={runSelection.error}
            selectionResponse={runSelection.lastResponse}
            onTrackLatest={() => {
              void actions.selectRun({ mode: "latest" }).then(() => {
                refreshAll();
              });
            }}
            onPinRun={(runId) => {
              void actions.selectRun({ mode: "pinned", runId }).then(() => {
                refreshAll();
              });
            }}
          />
        )}
        actionBar={floatingBar}
        hero={missionDeck}
        oversight={<UiInferenceOversight oversight={contract.uiInference} />}
        errors={errors}
      >
        {screenContent}
      </AppShell>

      <ConfirmationSheet
        open={confirmAction !== null}
        tone={confirmAction ? controlCopy[confirmAction].tone : "warn"}
        title={confirmAction ? controlCopy[confirmAction].confirmTitle : "Confirm action"}
        subtitle={confirmAction ? controlCopy[confirmAction].confirmSubtitle : "Review the operator reason before continuing."}
        detail={confirmAction ? controlCopy[confirmAction].detail : undefined}
        reason={actionReason}
        auditNote={`${dashboard.authSummary.operatorLabel} / ${dashboard.authSummary.sessionId}`}
        confirmLabel={confirmAction ? controlCopy[confirmAction].confirmLabel : "Confirm"}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          if (confirmAction) {
            invokeControl(confirmAction);
          }
          setConfirmAction(null);
        }}
      />
    </>
  );
}
