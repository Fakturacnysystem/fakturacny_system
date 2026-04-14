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
  humanizeRuntimeText,
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
    detail: "Zastaví nové vstupy, ale panel aj živé údaje zostanú ďalej viditeľné.",
    confirmTitle: "Pozastaviť nové vstupy",
    confirmSubtitle: "Robot budeš ďalej vidieť, ale prestane otvárať nové obchody, kým to znova nepovolíš.",
    confirmLabel: "Pozastaviť",
    requiresConfirmation: true,
  },
  resume: {
    icon: "→",
    tone: "good",
    detail: "Vráti robot do bežného chodu, ak tomu nebránia problémy alebo blokácie.",
    confirmTitle: "Pokračovať v chode",
    confirmSubtitle: "Pokračovanie dávaj len vtedy, keď je jasné, že stav systému je v poriadku.",
    confirmLabel: "Pokračovať",
    requiresConfirmation: false,
  },
  freeze: {
    icon: "✦",
    tone: "danger",
    detail: "Zastaví vykonávanie, ale diagnostika a bezpečnostné údaje zostanú k dispozícii.",
    confirmTitle: "Zmraziť vykonávanie",
    confirmSubtitle: "Toto je bezpečnostný zásah. Použi ho, keď by ďalšie pokračovanie nebolo bezpečné.",
    confirmLabel: "Zmraziť",
    requiresConfirmation: true,
  },
  flatten: {
    icon: "↓",
    tone: "danger",
    detail: "Požiada o rýchle uzavretie otvoreného rizika a zníženie expozície.",
    confirmTitle: "Núdzovo zavrieť expozíciu",
    confirmSubtitle: "Toto je tvrdý zásah. Potvrď ho len vtedy, keď chceš otvorené riziko zavrieť čo najskôr.",
    confirmLabel: "Núdzovo zavrieť",
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
    "Pozorovaný zhoršený stav runtime API. Dôvod zásahu aj nadväzná kontrola histórie boli zapísané.",
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
      label: "Hlavný panel",
      detail: `${dashboard.mode} / ${dashboard.healthState.status}`,
      tone: toneFromStateKind(dashboard.healthState.status),
      hotkey: "1",
    },
    {
      id: "brain",
      label: "Rozhodovanie",
      detail: `${contract.brain.selectedSymbol} / ${contract.brain.actionState}`,
      tone: toneFromStateKind(contract.brain.stateKind),
      hotkey: "2",
    },
    {
      id: "shield",
      label: "Bezpečnosť",
      detail: `dôvera ${contract.shield.trustVerdict}`,
      tone: toneFromVerdict(contract.shield.trustVerdict),
      hotkey: "3",
    },
    {
      id: "execution",
      label: "Obchody",
      detail: `${contract.execution.orders.length} pokynov / ${contract.execution.positions.length} pozícií`,
      tone: toneFromStateKind(contract.execution.stateKind),
      hotkey: "4",
    },
  ];

  const floatingBar = (
    <FloatingActionBar
      title="Rýchle ovládanie"
      subtitle="Tu sú najdôležitejšie akcie. Rizikové zásahy sú oddelené od bežných úkonov a vždy zostávajú dohľadateľné v histórii."
      status={(
        <div className="rtc-pill-row">
          <StatusBadge tone={toneFromStateKind(dashboard.healthState.status)} label="systém" value={dashboard.healthState.status} />
          <StatusBadge tone={toneFromVerdict(shield.trustVerdict)} label="dôvera" value={shield.trustVerdict} />
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
            Aktuálne platí: {shield.appliedControl ? `${shield.appliedControl.action} cez ${shield.appliedControl.controlSurface}` : "nedostupné"}
          </div>
          <button className="rtc-button rtc-button-quiet" type="button" onClick={refreshAll}>
            Obnoviť údaje
          </button>
        </div>
      )}
    />
  );

  const missionDeck = (
    <GlassPanel className="rtc-hero rtc-screen-hero-card" elevated>
      <SectionHeader
        eyebrow="Rýchly prehľad"
        title="Najdôležitejšie na prvý pohľad"
        subtitle="Za pár sekúnd vidíš, čo sleduješ, v akom je to stave, či sú údaje čerstvé a či robot práve niečo rieši."
        meta={(
          <div className="rtc-pill-row">
            <StatusBadge tone={dashboard.source === "runtime-api" ? "good" : "danger"} label="zdroj" value={dashboard.source} />
            <StatusBadge tone={toneFromStateKind(contract.runtimeIdentity.stateKind)} label="stav" value={contract.runtimeIdentity.stateKind} />
            <StatusBadge tone={contract.runtimeIdentity.selectionMode === "pinned" ? "good" : "warn"} label="výber" value={contract.runtimeIdentity.selectionMode} />
          </div>
        )}
        actions={(
          <button className="rtc-button rtc-button-quiet" type="button" onClick={refreshAll}>
            Obnoviť stav
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
          title="Prehľad trhu"
          subtitle="Tu vidíš základný stav trhu pre hlavné páry v práve sledovanom behu."
          items={featuredSymbols}
          empty={(
            <EmptyState
              title="Zatiaľ nie sú k dispozícii trhové snímky"
              description="Tento beh zatiaľ neposlal údaje o sledovaných pároch."
            />
          )}
          renderItem={(symbol) => (
            <article className="rtc-feed-card rtc-live-card" key={`${symbol.symbol}-${symbol.ts}`}>
              <div className="rtc-live-card-header">
                <strong>{symbol.symbol}</strong>
                <StatusBadge tone={symbol.stale ? "warn" : "good"} value={symbol.stale ? "staré" : "živé"} subtle />
              </div>
              <div className="rtc-live-price">
                {symbol.bid.toFixed(2)} <span>/</span> {symbol.ask.toFixed(2)}
              </div>
              <div className="rtc-live-meta">
                <span>{humanizeRuntimeText(symbol.venue)}</span>
                <span>{symbol.spreadBps.toFixed(2)} bps</span>
                <span>{symbol.latencyMs} ms</span>
                <span>q {symbol.qualityScore.toFixed(1)}</span>
              </div>
            </article>
          )}
        />

        <LiveFeedList
          title="Posledné rozhodnutia"
          subtitle="Tu rýchlo vidíš, čo robot naposledy chcel urobiť a čo ho pri tom brzdilo."
          items={featuredDecisions}
          empty={(
            <EmptyState
              title="Zatiaľ nie sú k dispozícii rozhodnutia"
              description="Tento beh zatiaľ neposlal žiadne rozhodnutia."
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
              <div className="rtc-inline-note">{decision.topReasons.length > 0 ? decision.topReasons.map(humanizeRuntimeText).join(", ") : "bez prekážok"}</div>
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
          eyebrow="Načítavam"
          title="Pripravujem panel"
          subtitle="Aplikácia čaká na spoľahlivé údaje, aby nezobrazila nič nepresné."
        />
        <SkeletonState blocks={4} />
      </GlassPanel>
    </div>
  ) : (
    <div className="rtc-screen-panel">
      <section className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Prihlásenie"
            title="Kto panel ovláda"
            subtitle="Najprv musí byť jasné, kto panel používa. Kým nikto nie je prihlásený, dôležité zásahy zostanú zablokované."
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
                  ID používateľa
                  <input className="rtc-input" value={operatorId} onChange={(event) => setOperatorId(event.target.value)} />
                </label>
                <label className="rtc-label">
                  Meno
                  <input className="rtc-input" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
                </label>
              </div>

              <label className="rtc-label">
                Rola
                <select className="rtc-select" value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="operator">operátor</option>
                  <option value="admin">správca</option>
                  <option value="observer">pozorovateľ</option>
                </select>
              </label>

              <div className="rtc-button-row">
                <button className="rtc-button" type="submit">
                  Prihlásiť používateľa
                </button>
                <button className="rtc-button rtc-button-quiet" type="button" onClick={() => actions.clearIdentity()}>
                  Odhlásiť
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
                  <span>Stav</span>
                  <strong>{dashboard.authSummary.status}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>ID relácie</span>
                  <strong>{dashboard.authSummary.sessionId}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Možnosti ovládania</span>
                  <strong>{controls.statusLine}</strong>
                </div>
              </div>

              <div className="rtc-banner">
                Nebezpečné zásahy sú povolené až po prihlásení. Je to ochrana proti anonymným zásahom bez stopy v histórii.
              </div>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel tone="warn" interactive>
          <SectionHeader
            eyebrow="Ovládanie"
            title="Potvrdenie zásahu"
            subtitle="Bežné a rizikové zásahy sú oddelené. Vždy vidíš aj to, čo si poslal, aj čo systém naozaj prijal."
            meta={(
              <div className="rtc-pill-row">
                <StatusBadge
                  tone={runtimeControls.pendingAction ? "warn" : "good"}
                  label="odoslanie"
                  value={runtimeControls.pendingAction ? "prebieha" : "nič nebeží"}
                />
              </div>
            )}
          />

          <label className="rtc-label">
            Prečo to robíš
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
            <p className="rtc-inline-note">Zatiaľ si neposlal žiadny zásah.</p>
          )}

          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Čo momentálne platí</span>
              <strong>{shield.appliedControl ? `${shield.appliedControl.action} cez ${shield.appliedControl.controlSurface}` : "nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Vynútený režim rizika</span>
              <strong>{shield.appliedControl?.forcedRiskMode ?? "nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Čakajúci príkaz</span>
              <strong>{shield.queuedCommand ? `${shield.queuedCommand.action} / ${shield.queuedCommand.effectiveState}` : "nič nečaká"}</strong>
            </div>
          </div>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-three">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Stav systému"
            title="Zdravie systému"
            subtitle="Tu vidíš, či systém beží, či má spojenie a či sa neopiera len o náhradné dáta."
          />
          <ul className="rtc-list rtc-tight-list">
            {dashboard.warnings.length > 0 ? dashboard.warnings.map((warning) => <li key={warning}>{humanizeRuntimeText(warning)}</li>) : <li>žiadne aktívne varovania</li>}
          </ul>
          <div className="rtc-kv">
            {dashboard.healthDetails.map((detail) => (
              <div className="rtc-kv-row" key={detail.label}>
                <span>{humanizeRuntimeText(detail.label)}</span>
                <strong>{humanizeRuntimeText(detail.value)}</strong>
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel tone={dashboard.blockers.length > 0 ? "danger" : "good"} interactive>
          <SectionHeader
            eyebrow="Spoľahlivosť"
            title="Spoľahlivosť a blokácie"
            subtitle="Ak niečo blokuje robot alebo je nejasné, ostane to viditeľné, kým systém nedokáže opak."
          />
          <div className="rtc-pill-row">
            {dashboard.blockers.length > 0
              ? dashboard.blockers.map((blocker) => (
                  <StatusBadge key={blocker} tone="danger" value={blocker} />
                ))
              : <StatusBadge tone="good" value="bez blokácií" />}
          </div>
          <div className="rtc-kv">
            {dashboard.integrityDetails.map((detail) => (
              <div className="rtc-kv-row" key={detail.label}>
                <span>{humanizeRuntimeText(detail.label)}</span>
                <strong>{humanizeRuntimeText(detail.value)}</strong>
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Poznámky"
            title="Poznámka k situácii"
            subtitle="Aj poznámky sa zapisujú pod menom používateľa a patria ku konkrétnemu behu."
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
                Závažnosť
                <select className="rtc-select" value={incidentSeverity} onChange={(event) => setIncidentSeverity(event.target.value)}>
                  <option value="SEV-1">SEV-1</option>
                  <option value="SEV-2">SEV-2</option>
                  <option value="SEV-3">SEV-3</option>
                </select>
              </label>
              <label className="rtc-label">
                Štítky
                <input className="rtc-input" value={incidentTags} onChange={(event) => setIncidentTags(event.target.value)} />
              </label>
            </div>

            <label className="rtc-label">
              Poznámka
              <textarea className="rtc-textarea" value={incidentNote} onChange={(event) => setIncidentNote(event.target.value)} />
            </label>

            <div className="rtc-inline-note">Dĺžka textu: {deferredIncidentNote.length} znakov.</div>

            <div className="rtc-button-row">
              <button className="rtc-button" disabled={!controls.canWriteIncidentNotes || incidentWriter.pending} type="submit">
                {incidentWriter.pending ? "Odosielam…" : "Uložiť poznámku"}
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
            eyebrow="Trh"
            title="Prehľad trhu"
            subtitle="Trhové údaje a rozhodnutia sú oddelené, aby sa staré alebo blokované dáta netvárili zdravo."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Pár</th>
                  <th>Burza</th>
                  <th>Nákupná cena</th>
                  <th>Predajná cena</th>
                  <th>Rozdiel ceny (bps)</th>
                  <th>Odozva</th>
                  <th>Kvalita</th>
                  <th>Staré dáta</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.symbols.length > 0 ? (
                  dashboard.symbols.map((symbol) => (
                    <tr key={symbol.symbol}>
                      <td>{symbol.symbol}</td>
                      <td>{humanizeRuntimeText(symbol.venue)}</td>
                      <td>{symbol.bid.toFixed(2)}</td>
                      <td>{symbol.ask.toFixed(2)}</td>
                      <td>{symbol.spreadBps.toFixed(1)}</td>
                      <td>{symbol.latencyMs} ms</td>
                      <td>{symbol.qualityScore.toFixed(2)}</td>
                      <td>
                        <StatusBadge tone={symbol.stale ? "warn" : "good"} value={symbol.stale ? "áno" : "nie"} subtle />
                      </td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={8} message="Momentálne nie sú k dispozícii trhové údaje." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Rozhodnutie"
            title="Prehľad rozhodnutí"
            subtitle="Tu vidíš, čo robot chcel urobiť, čo mu v tom bránilo a aký bol výsledok rozhodnutia."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Pár</th>
                  <th>Zámer</th>
                  <th>Istota</th>
                  <th>Výhoda</th>
                  <th>Výsledok</th>
                  <th>Prekážky</th>
                  <th>Posledná akcia</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.decisions.length > 0 ? (
                  dashboard.decisions.map((decision) => (
                    <tr key={decision.id}>
                      <td>{decision.symbol}</td>
                      <td>{humanizeRuntimeText(decision.intent)}</td>
                      <td>{decision.confidence.toFixed(2)}</td>
                      <td>{decision.expectedEdgeBps} bps</td>
                      <td>
                        <StatusBadge tone={toneFromVerdict(decision.riskVerdict)} value={decision.riskVerdict} subtle />
                      </td>
                      <td>{decision.blockers.length > 0 ? decision.blockers.map(humanizeRuntimeText).join(", ") : "žiadne"}</td>
                      <td>{humanizeRuntimeText(decision.lastAction)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={7} message="Momentálne nie sú k dispozícii žiadne rozhodnutia." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Upozornenia"
            title="Prehľad upozornení"
            subtitle="Kritické upozornenia majú smerovať k zastaveniu alebo zníženiu rizika, nie k tichému pokračovaniu."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Závažnosť</th>
                  <th>Modul</th>
                  <th>Správa</th>
                  <th>Čas</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.alerts.length > 0 ? (
                  dashboard.alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>
                        <StatusBadge tone={toneFromSeverity(alert.severity)} value={alert.severity} subtle />
                      </td>
                      <td>{humanizeRuntimeText(alert.module)}</td>
                      <td>{humanizeRuntimeText(alert.message)}</td>
                      <td>{formatMoment(alert.ts)}</td>
                    </tr>
                  ))
                ) : (
                  <EmptyTableRow colSpan={4} message="Momentálne nie sú k dispozícii žiadne upozornenia." />
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="História"
            title="Čo sa stalo"
            subtitle="Táto časť ukazuje priebeh a súvislosti pre vybraný beh, aby si sa opieral o dôkazy, nie o domnienky."
          />
          <div className="rtc-badges">
            {replay.summary.map((badge) => (
              <StatusBadge key={`${badge.label}-${badge.value}`} tone={badge.tone} label={badge.label} value={badge.value} />
            ))}
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Časová os</h3>
              <div className="rtc-timeline">
                {replay.timeline.map((item) => (
                  <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>
                    <div className="rtc-inline-note">{item.ts}</div>
                    <div>{humanizeRuntimeText(item.detail)}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Udalosti</h3>
              <div className="rtc-timeline">
                {replay.incidents.map((item) => (
                  <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>
                    <div className="rtc-inline-note">{item.ts}</div>
                    <div>{humanizeRuntimeText(item.detail)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Podobné situácie</h3>
              <ul className="rtc-list">
                {replay.analogMatches.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>: {humanizeRuntimeText(item.detail)}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Čo by bolo keby</h3>
              <ul className="rtc-list">
                {replay.counterfactuals.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>: {humanizeRuntimeText(item.detail)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Rozpad výsledku</h3>
              <ul className="rtc-list">
                {replay.pnlAttribution.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>: {humanizeRuntimeText(item.detail)}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Poznámky</h3>
              <ul className="rtc-list">
                {replay.notes.map((item) => (
                  <li key={`${item.label}-${item.ts}`}>
                    <strong>{humanizeRuntimeText(item.label)}</strong>: {humanizeRuntimeText(item.detail)}
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
            eyebrow="Postupy"
            title="Odporúčaný postup"
            subtitle="Odporúčané kroky sú priamo v aplikácii, aby si mal postup po ruke pri zásahu aj pri spätnej kontrole."
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
          <h3 className="rtc-section-title">Kontrolný zoznam pri spätnej kontrole</h3>
          <ol className="rtc-list">
            {contract.runbook.replayChecklist.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Vydanie aplikácie"
            title="Pripravenosť verzie pre macOS"
            subtitle="Tento postup je pripravený, ale niektoré posledné kroky stále závisia od Apple."
          />
          <div className="rtc-release-grid">
            <div>
              <div className="rtc-pill-row">
                <StatusBadge tone={release.status === "ready" ? "good" : "warn"} value={`stav vydania: ${release.status}`} />
                <StatusBadge tone="info" value={`bundleId: ${release.bundleId}`} />
              </div>
              <div className="rtc-kv">
                {release.checklist.map((item) => (
                  <div className="rtc-kv-row" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.satisfied ? "nastavené" : humanizeRuntimeText(item.detail)}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Presné príkazy</h3>
              <div className="rtc-code">{release.exactCommands.join("\n")}</div>
              {release.missingInputs.length > 0 ? (
                <>
                  <h3 className="rtc-section-title">Chýbajúce externé vstupy</h3>
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
              eyebrow="Načítavam"
              title="Načítavam vysvetlenie rozhodnutí"
              subtitle="Čakám na údaje, ktoré vysvetľujú, prečo sa robot rozhodol takto."
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
              eyebrow="Načítavam"
              title="Načítavam bezpečnostný stav"
              subtitle="Čakám na údaje o bezpečnosti, ochranných pravidlách a dôvere."
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
              eyebrow="Načítavam"
              title="Načítavam priebeh obchodov"
              subtitle="Čakám na údaje o pokynoch, burze a účte."
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
        title={confirmAction ? controlCopy[confirmAction].confirmTitle : "Potvrď zásah"}
        subtitle={confirmAction ? controlCopy[confirmAction].confirmSubtitle : "Pred pokračovaním si ešte raz skontroluj dôvod zásahu."}
        detail={confirmAction ? controlCopy[confirmAction].detail : undefined}
        reason={actionReason}
        auditNote={`${dashboard.authSummary.operatorLabel} / ${dashboard.authSummary.sessionId}`}
        confirmLabel={confirmAction ? controlCopy[confirmAction].confirmLabel : "Potvrdiť"}
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
