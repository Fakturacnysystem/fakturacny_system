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
  humanizeRuntimeText,
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
          eyebrow="Bezpečnosť"
          title="Dá sa tomuto robotovi práve teraz veriť?"
          subtitle="Táto obrazovka ukazuje, či je systém bezpečný na sledovanie alebo zásah. Každý záver stojí na reálnych dátach z behu, nie na dojme z UI."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromVerdict(shield.trustVerdict)} label="dôvera" value={shield.trustVerdict} />
              <StatusBadge tone={toneFromSeverity(shield.stateKind)} label="stav" value={shield.stateKind} />
              <StatusBadge
                tone={
                  shield.runtimeIdentity?.pinIntegrityStatus === "ok"
                    ? "good"
                    : shield.runtimeIdentity?.pinIntegrityStatus === "not_pinned"
                      ? "warn"
                      : "danger"
                }
                label="pevné pripnutie"
                value={shield.runtimeIdentity?.pinIntegrityStatus ?? "unavailable"}
              />
              <StatusBadge
                tone={shield.runtimeIdentity?.driftStatus === "locked" ? "good" : "warn"}
                label="odklon"
                value={shield.runtimeIdentity?.driftStatus ?? "unavailable"}
              />
            </div>
          )}
        />
        <div className="rtc-inline-note">aktualizované {formatMoment(shield.lastUpdatedAt)}</div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Dôvera"
            title="Celkové hodnotenie dôvery"
            subtitle="Najdôležitejšie dôvody ostávajú hore. Keď je systém rizikový alebo neistý, panel to neschová za pekné zelené kartičky."
          />
          <div className="rtc-summary-grid">
            <article className="rtc-summary-card" data-tone={toneFromVerdict(shield.trustVerdict)}>
              <div className="rtc-summary-label">Výsledok</div>
              <div className="rtc-summary-value">{shield.trustVerdict}</div>
              <div className="rtc-summary-hint">Aktuálne hodnotenie dôvery pre vybraný beh.</div>
            </article>
            <article className="rtc-summary-card" data-tone={shield.runtimeIdentity?.artifactFreshness?.status === "stale" ? "danger" : "info"}>
              <div className="rtc-summary-label">Čerstvosť dát</div>
              <div className="rtc-summary-value">{shield.runtimeIdentity?.artifactFreshness?.status ?? shield.stateKind}</div>
              <div className="rtc-summary-hint">Čerstvosť sa berie priamo z identity behu, panel ju sám nevypočítava.</div>
            </article>
          </div>
          <div className="rtc-pill-row">
            {shield.trustReasons.length > 0 ? (
              shield.trustReasons.map((reason) => (
                <StatusBadge key={reason} tone={toneFromSeverity(reason)} value={reason} />
              ))
            ) : (
              <StatusBadge tone="good" value="žiadne aktívne zhoršenie dôvery" />
            )}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Stav"
            title="Bezpečnostný stav systému"
            subtitle="Tieto riadky hovoria, či je robot bezpečné sledovať alebo ovládať: či je správne pripnutý, či sú dáta čerstvé, či je povolené obchodovanie a či funguje spojenie s burzou."
          />
          <div className="rtc-state-grid">
            {shield.runtimeSafety.map((item) => (
              <article className="rtc-state-card" key={item.label}>
                <div className="rtc-live-card-header">
                <strong>{humanizeRuntimeText(item.label)}</strong>
                  <StatusBadge tone={toneFromVerdict(item.status)} value={item.status} subtle />
                </div>
                <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                <div>{humanizeRuntimeText(item.detail)}</div>
                <ul className="rtc-list rtc-tight-list">
                  {item.evidence.length > 0 ? item.evidence.map((evidence) => <li key={`${item.label}-${evidence}`}>{humanizeRuntimeText(evidence)}</li>) : <li>Nie sú pripojené dôkazy</li>}
                </ul>
              </article>
            ))}
          </div>
        </GlassPanel>
      </section>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Nasadenie"
          title="Stav nasadenia a návratu späť"
          subtitle="Tu vidíš, či systém pôsobí pripraveno na ďalší krok, či nehrozí návrat späť a či bežia obnovovacie režimy alebo dôležité streamy."
        />
        {shield.performanceControl ? (
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Skóre pripravenosti</span>
              <strong>{shield.performanceControl.promotionScore == null ? "Nedostupné" : shield.performanceControl.promotionScore.toFixed(3)}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Stav pripravenosti</span>
              <strong>{shield.performanceControl.promotionStatus ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Spustený návrat späť</span>
              <strong>{shield.performanceControl.rollbackTriggered == null ? "Nedostupné" : shield.performanceControl.rollbackTriggered ? "áno" : "nie"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Obnovovací režim</span>
              <strong>{shield.performanceControl.recoveryMode ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Zhoršenie live stavu</span>
              <strong>{shield.performanceControl.liveDegradationStatus ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Samospomaľovanie</span>
              <strong>
                {shield.performanceControl.selfThrottlingActive == null
                  ? "Nedostupné"
                  : shield.performanceControl.selfThrottlingActive
                    ? "aktívne"
                    : "neaktívne"}
              </strong>
            </div>
            <div className="rtc-kv-row">
              <span>Zdravie súkromného streamu</span>
              <strong>{shield.performanceControl.privateStreamHealth ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Hranica oprávnení</span>
              <strong>{shield.performanceControl.authorityBoundary ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Riziko návratu späť</span>
              <strong>{shield.performanceControl.rollbackRisk ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Dôveryhodnosť cieľa</span>
              <strong>{shield.performanceControl.targetPlausibility ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Rozdiel od cieľa (net bps)</span>
              <strong>
                {shield.performanceControl.targetGapNetBps == null
                  ? "Nedostupné"
                  : shield.performanceControl.targetGapNetBps.toFixed(1)}
              </strong>
            </div>
            <div className="rtc-kv-row">
              <span>Stav pripravenosti</span>
              <strong>{shield.performanceControl.readinessStatus ?? "Nedostupné"}</strong>
            </div>
          </div>
        ) : (
          <div className="rtc-inline-note">Údaje o pripravenosti a návrate späť zatiaľ pre tento beh nie sú dostupné.</div>
        )}
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Ochrany"
            title="Prehľad ochranných pravidiel"
            subtitle="Limit a skutočne nameraná hodnota sú vedľa seba. Ak niečo chýba, riadok zostane otvorene nedostupný a netvári sa, že ochrana prešla."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Ochrana</th>
                  <th>Limit</th>
                  <th>Skutočná hodnota</th>
                  <th>Stav</th>
                  <th>Dopad</th>
                  <th>Dôkazy</th>
                  <th>Naposledy aktivované</th>
                </tr>
              </thead>
              <tbody>
                {shield.guardMatrix.length > 0 ? (
                  shield.guardMatrix.map((guard) => (
                    <tr key={guard.name}>
                      <td>
                        <strong>{humanizeRuntimeText(guard.name)}</strong>
                        {guard.derived ? <div className="rtc-inline-note">odvodené porovnanie</div> : null}
                      </td>
                      <td>{humanizeRuntimeText(guard.configuredThreshold)}</td>
                      <td>{humanizeRuntimeText(guard.observedValue)}</td>
                      <td>
                        <StatusBadge tone={toneFromGuardStatus(guard.status)} value={guard.status} subtle />
                      </td>
                      <td>{humanizeRuntimeText(guard.impact)}</td>
                      <td>
                        <ul className="rtc-list rtc-tight-list">
                          {guard.evidence.length > 0 ? guard.evidence.map((item) => <li key={`${guard.name}-${item}`}>{humanizeRuntimeText(item)}</li>) : <li>Bez dôkazu</li>}
                        </ul>
                      </td>
                      <td>{guard.lastTriggeredAt ? formatMoment(guard.lastTriggeredAt) : "Nedostupné"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>Zatiaľ nie je k dispozícii prehľad ochranných pravidiel.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel tone="warn" interactive>
          <SectionHeader
            eyebrow="Zásahy"
            title="Bezpečné ovládanie"
            subtitle="Každý zásah ostáva dohľadateľný. Keď systém nevie dokázať, kto zásah robí alebo či sa dá auditovať, tlačidlá ostanú zablokované."
          />
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Stav ovládania</span>
              <strong>{controls.statusLine}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Kto a odkiaľ</span>
              <strong>{controls.provenanceLine}</strong>
            </div>
          </div>
          <label className="rtc-label">
            Dôvod zásahu
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
                {pendingAction === control.action ? "Odosiela sa..." : control.label}
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
            <p className="rtc-inline-note">Z tejto relácie zatiaľ nebol odoslaný žiadny bezpečnostný zásah.</p>
          )}
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Čo momentálne platí</span>
              <strong>{shield.appliedControl ? `${humanizeRuntimeText(shield.appliedControl.action)} cez ${humanizeRuntimeText(shield.appliedControl.controlSurface)}` : "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Vynútený režim rizika</span>
              <strong>{shield.appliedControl?.forcedRiskMode ? humanizeRuntimeText(shield.appliedControl.forcedRiskMode) : "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Čakajúci príkaz</span>
              <strong>{shield.queuedCommand ? `${humanizeRuntimeText(shield.queuedCommand.action)} / ${humanizeRuntimeText(shield.queuedCommand.effectiveState)}` : "nič nečaká"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Používateľský stream</span>
              <strong>{humanizeRuntimeText(shield.userStream.status)}</strong>
            </div>
          </div>
          {shield.appliedControl?.reasons.length ? (
            <div className="rtc-pill-row">
              {shield.appliedControl.reasons.map((reason) => (
                <StatusBadge key={reason} tone="warn" value={humanizeRuntimeText(reason)} />
              ))}
            </div>
          ) : null}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Pravda"
            title="Zhoda a spoľahlivosť"
            subtitle="Tu vidíš základné pravdy: ktorý beh je vybraný, či nehrozí odklon na iný beh, aké čerstvé sú dôkazy a či sa jednotlivé časti navzájom nebijú."
          />
          <ul className="rtc-list rtc-tight-list">
            {shield.truthNotes.map((note) => (
              <li key={note}>{humanizeRuntimeText(note)}</li>
            ))}
          </ul>
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Spôsob výberu</span>
              <strong>{shield.runtimeIdentity?.runSelectionMode ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Cesta k behu</span>
              <strong>{shield.runtimeIdentity?.runPath ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Zhoda pevného pripnutia</span>
              <strong>{shield.runtimeIdentity?.pinIntegrityStatus ?? "unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Stav odklonu</span>
              <strong>{shield.runtimeIdentity?.driftStatus ?? "unavailable"}</strong>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Dôkazy"
            title="Napojené dôkazy"
            subtitle="Tieto súbory priamo podkladajú bezpečnostné hodnotenie. Z panelu sa tak vieš dostať ku konkrétnym dôkazom bez hádania."
          />
          <div className="rtc-pill-row">
            {shield.linkedArtifacts.length > 0 ? (
              shield.linkedArtifacts.map((artifact) => (
                <StatusBadge key={artifact} tone="info" value={artifact} />
              ))
            ) : (
              <StatusBadge tone="warn" value="bez napojených dôkazov" />
            )}
          </div>
        </GlassPanel>
      </section>
    </div>
  );
}
