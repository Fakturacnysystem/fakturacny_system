import React from "react";
import { EmptyState } from "@/components/ui/states";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type { BrainState } from "@/types/runtime";
import {
  formatMoment,
  formatOptionalNumber,
  humanizeRuntimeText,
  toneFromPipelineStatus,
  toneFromSeverity,
  toneFromVerdict,
} from "@/components/screen-formatters";

export function BrainScreen({ brain }: { brain: BrainState }) {
  const selectedSymbolView =
    brain.symbolViews.find((symbol) => symbol.symbol === brain.selectedSymbol)
    ?? brain.symbolViews[0]
    ?? null;

  return (
    <div className="rtc-screen-panel">
      <GlassPanel className="rtc-screen-hero-card" elevated>
        <SectionHeader
          eyebrow="Rozhodovanie"
          title="Prečo sa robot rozhodol takto"
          subtitle="Táto obrazovka ukazuje reťaz rozhodovania bez domýšľania. Keď niečo chýba, otvorene to povie."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromPipelineStatus(brain.stateKind === "healthy" ? "pass" : "warn")} label="state" value={brain.stateKind} />
              <StatusBadge tone={toneFromVerdict(brain.actionState)} label="akcia" value={brain.actionState} />
              <StatusBadge tone={brain.marketRegime === "unavailable" ? "info" : "good"} label="režim trhu" value={brain.marketRegime} />
              <StatusBadge tone={brain.executionEligibilityOutcome === "ordering_allowed" ? "good" : "warn"} label="povolenie obchodu" value={brain.executionEligibilityOutcome} />
            </div>
          )}
        />
        <div className="rtc-inline-note">aktualizované {formatMoment(brain.lastUpdatedAt)}</div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Fokus"
            title="Na čo sa robot pozeral"
            subtitle="Vybraný pár je opísaný len cez skutočné údaje: cenu, prekážky, posledné rozhodnutie a jasne označené odvodené poznámky."
          />
          {selectedSymbolView ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Pár / burza</span>
                  <strong>{selectedSymbolView.symbol} / {selectedSymbolView.venue}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Nákup / predaj</span>
                  <strong>
                    {selectedSymbolView.bid === null || selectedSymbolView.ask === null
                      ? "Nedostupné"
                      : `${formatOptionalNumber(selectedSymbolView.bid)} / ${formatOptionalNumber(selectedSymbolView.ask)}`}
                  </strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Rozdiel ceny / hĺbka</span>
                  <strong>
                    {selectedSymbolView.spreadBps === null
                      ? "Nedostupné"
                      : `${formatOptionalNumber(selectedSymbolView.spreadBps)} bps`}
                    {" / "}
                    {selectedSymbolView.depthNotional === null
                      ? "Nedostupné"
                      : formatOptionalNumber(selectedSymbolView.depthNotional)}
                  </strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Signál / odhad</span>
                  <strong>{selectedSymbolView.signal ?? "Nedostupné"} / {selectedSymbolView.forecast ?? "Nedostupné"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Istota</span>
                  <strong>{selectedSymbolView.confidence === null ? "Nedostupné" : formatOptionalNumber(selectedSymbolView.confidence, 3)}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Aktuálna prekážka</span>
                  <strong>{selectedSymbolView.currentBlockReason ?? "žiadna"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Posledné / ďalšie</span>
                  <strong>{selectedSymbolView.lastAction ?? "Nedostupné"} / {selectedSymbolView.nextEligibleAction ?? "Nedostupné"}</strong>
                </div>
              </div>
              {selectedSymbolView.derivedFields.length > 0 ? (
                <div className="rtc-pill-row">
                  {selectedSymbolView.derivedFields.map((field) => (
                    <StatusBadge key={field} tone="info" value={field} />
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <EmptyState
              title="Zatiaľ nie je k dispozícii podrobný pohľad na pár."
              description="Tento beh zatiaľ neposlal detailné vysvetlenie pre konkrétny pár."
            />
          )}
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Vysvetlenie"
            title="Prečo áno / prečo nie"
            subtitle="Tu sú vedľa seba dôvody pre akciu aj dôvody proti nej, aby sa nič netvárilo istejšie, než v skutočnosti je."
          />
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Prečo konať</h3>
              <ul className="rtc-list rtc-tight-list">
                {brain.whyTrade.length > 0 ? brain.whyTrade.map((item) => <li key={item}>{humanizeRuntimeText(item)}</li>) : <li>Nedostupné</li>}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Prečo nekonať</h3>
              <ul className="rtc-list rtc-tight-list">
                {brain.whyNotTrade.length > 0 ? brain.whyNotTrade.map((item) => <li key={item}>{humanizeRuntimeText(item)}</li>) : <li>Nedostupné</li>}
              </ul>
            </div>
          </div>
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Prekážky</span>
              <strong>{brain.blockingReasons.length > 0 ? brain.blockingReasons.map(humanizeRuntimeText).join(", ") : "žiadne"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Podporné signály</span>
              <strong>{brain.supportingSignals.length > 0 ? brain.supportingSignals.map(humanizeRuntimeText).join(", ") : "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Výhoda po nákladoch</span>
              <strong>{brain.costAdjustedEdgeBps === null ? "Nedostupné" : `${formatOptionalNumber(brain.costAdjustedEdgeBps)} bps`}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Zdroj tejto výhody</span>
              <strong>{brain.costAdjustedEdgeSource ?? "Nedostupné"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Minimálna predajná hranica</span>
              <strong>{brain.sellFloorStatus}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Riziková kontrola</span>
              <strong>{brain.riskGatingOutcome}</strong>
            </div>
          </div>
          <ul className="rtc-list rtc-tight-list">
            {brain.evidenceNotes.map((note) => (
              <li key={note}>{humanizeRuntimeText(note)}</li>
            ))}
          </ul>
        </GlassPanel>
      </section>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Výber"
          title="Poradie príležitostí"
          subtitle="Tu vidíš, ktorý pár a ktorý spôsob obchodovania vyšiel najlepšie, aký tlak ostáva v poradovníku a či robot nevynecháva príliš veľa príležitostí."
        />
        {brain.opportunityRanking ? (
          <>
            <div className="rtc-kv">
              <div className="rtc-kv-row">
                <span>Vybraný postup</span>
                <strong>{brain.opportunityRanking.selectedPlaybook ?? "Nedostupné"}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Výsledné skóre</span>
                <strong>{brain.opportunityRanking.selectedScore == null ? "Nedostupné" : formatOptionalNumber(brain.opportunityRanking.selectedScore, 3)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Tlak vo fronte</span>
                <strong>{brain.opportunityRanking.backlogPressure == null ? "Nedostupné" : formatOptionalNumber(brain.opportunityRanking.backlogPressure, 3)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Prehliadnuté / chybné zásahy</span>
                <strong>
                  {brain.opportunityRanking.falseNegativeRate == null ? "Nedostupné" : formatOptionalNumber(brain.opportunityRanking.falseNegativeRate, 3)}
                  {" / "}
                  {brain.opportunityRanking.falsePositiveRate == null ? "Nedostupné" : formatOptionalNumber(brain.opportunityRanking.falsePositiveRate, 3)}
                </strong>
              </div>
            </div>
            <div className="rtc-table-wrap">
              <table className="rtc-table">
                <thead>
                  <tr>
                    <th>Pár</th>
                    <th>Postup</th>
                    <th>Skóre</th>
                    <th>Čistá výhoda</th>
                    <th>Kvalita</th>
                    <th>Spôsob vykonania</th>
                  </tr>
                </thead>
                <tbody>
                  {(brain.opportunityRanking.topCandidates ?? []).length > 0 ? (
                    brain.opportunityRanking.topCandidates?.map((candidate) => (
                      <tr key={`${candidate.symbol}-${candidate.playbook}`}>
                        <td>{candidate.symbol}</td>
                        <td>{candidate.playbook}</td>
                        <td>{formatOptionalNumber(candidate.score, 3)}</td>
                        <td>{candidate.netEdgeBps == null ? "Nedostupné" : `${formatOptionalNumber(candidate.netEdgeBps)} bps`}</td>
                        <td>{candidate.qualityOfEdge == null ? "Nedostupné" : formatOptionalNumber(candidate.qualityOfEdge, 3)}</td>
                        <td>{candidate.executionPreference ?? "Nedostupné"}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>Zatiaľ nie je k dispozícii poradie príležitostí.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <EmptyState
            title="Poradie príležitostí zatiaľ nie je dostupné."
            description="Tento beh zatiaľ neposlal údaje o tom, ako zoradil jednotlivé príležitosti."
          />
        )}
      </GlassPanel>

      <GlassPanel interactive>
          <SectionHeader
            eyebrow="Kroky rozhodnutia"
            title="Mapa rozhodovania"
            subtitle="Každý krok ukazuje svoj stav, dôvodové kódy, dôkazy a aj to, či bolo niečo iba odvodené."
          />
        {brain.pipeline.length > 0 ? (
          <div className="rtc-pipeline-grid">
            {brain.pipeline.map((step) => (
              <article className="rtc-pipeline-step" key={step.id}>
                <div className="rtc-live-card-header">
                      <strong>{humanizeRuntimeText(step.title)}</strong>
                  <div className="rtc-pill-row">
                    <StatusBadge tone={toneFromPipelineStatus(step.status)} value={step.status} subtle />
                    {step.derived ? <StatusBadge tone="info" value="odvodené" subtle /> : null}
                  </div>
                </div>
                <div className="rtc-kv rtc-kv-tight">
                  <div className="rtc-kv-row">
                    <span>Čas</span>
                    <strong>{formatMoment(step.timestamp)}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Oneskorenie</span>
                    <strong>{step.latencyMs === null ? "Nedostupné" : `${formatOptionalNumber(step.latencyMs, 0)} ms`}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Vstupy</span>
                      <strong>{humanizeRuntimeText(step.inputSummary)}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Výstupy</span>
                      <strong>{humanizeRuntimeText(step.outputSummary)}</strong>
                  </div>
                </div>
                {step.reasonCodes.length > 0 ? (
                  <div className="rtc-pill-row">
                    {step.reasonCodes.map((reason) => (
                      <StatusBadge key={`${step.id}-${reason}`} tone="warn" value={humanizeRuntimeText(reason)} />
                    ))}
                  </div>
                ) : null}
                <ul className="rtc-list rtc-tight-list">
                  {step.evidence.map((item) => (
                    <li key={`${step.id}-${item}`}>{humanizeRuntimeText(item)}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Reťaz rozhodovania pre tento beh zatiaľ nie je dostupná."
            description={brain.evidenceNotes[0] ?? "Tento beh zatiaľ neposlal artefakty, z ktorých sa dá poskladať celý priebeh rozhodnutia."}
          />
        )}
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Páry"
            title="Detail sledovaných párov"
            subtitle="Riadky ukazujú iba to, čo beh naozaj poslal: cenu, odhad, prekážku a posledný krok. Keď niečo chýba, ostane to priznané."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Pár</th>
                  <th>Nákup / predaj</th>
                  <th>Rozdiel ceny</th>
                  <th>Hĺbka trhu</th>
                  <th>Signál</th>
                  <th>Odhad</th>
                  <th>Istota</th>
                  <th>Prekážka</th>
                  <th>Posledné / ďalšie</th>
                </tr>
              </thead>
              <tbody>
                {brain.symbolViews.length > 0 ? (
                  brain.symbolViews.map((symbol) => (
                    <tr key={`${symbol.symbol}-${symbol.ts}`}>
                      <td>
                        <strong>{symbol.symbol}</strong>
                        <div className="rtc-inline-note">{symbol.venue}</div>
                      </td>
                      <td>
                        {symbol.bid === null || symbol.ask === null
                          ? "Nedostupné"
                          : `${formatOptionalNumber(symbol.bid)} / ${formatOptionalNumber(symbol.ask)}`}
                      </td>
                      <td>{symbol.spreadBps === null ? "Nedostupné" : `${formatOptionalNumber(symbol.spreadBps)} bps`}</td>
                      <td>{symbol.depthNotional === null ? "Nedostupné" : formatOptionalNumber(symbol.depthNotional)}</td>
                      <td>{symbol.signal ?? "Nedostupné"}</td>
                      <td>{symbol.forecast ?? "Nedostupné"}</td>
                      <td>{symbol.confidence === null ? "Nedostupné" : formatOptionalNumber(symbol.confidence, 3)}</td>
                      <td>{symbol.currentBlockReason ?? "žiadna"}</td>
                      <td>
                        <div>{symbol.lastAction ?? "Nedostupné"}</div>
                        <div className="rtc-inline-note">ďalší krok {symbol.nextEligibleAction ?? "Nedostupné"}</div>
                        {symbol.derivedFields.length > 0 ? (
                          <div className="rtc-pill-row">
                        {symbol.derivedFields.map((field) => (
                              <StatusBadge key={`${symbol.symbol}-${field}`} tone="info" value={humanizeRuntimeText(field)} subtle />
                            ))}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                      <td colSpan={9}>Zatiaľ nie je k dispozícii detailný pohľad na sledované páry.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="História"
            title="Spätný priebeh rozhodnutia"
            subtitle="Táto časť patrí ku konkrétnemu behu. Ak by sa história nezhodovala s aktuálne sledovaným behom, panel to ukáže ako problém."
          />
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Konečný výsledok</span>
              <strong>{humanizeRuntimeText(brain.decisionReplay.finalVerdict)}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Napojené dôkazy</span>
              <strong>{brain.decisionReplay.linkedArtifacts.length}</strong>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Časový priebeh</h3>
              <div className="rtc-timeline">
                {brain.decisionReplay.timeline.length > 0 ? (
                  brain.decisionReplay.timeline.map((item) => (
                    <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                      <div className="rtc-live-card-header">
                        <strong>{humanizeRuntimeText(item.label)}</strong>
                        {item.severity ? <StatusBadge tone={toneFromSeverity(item.severity)} value={item.severity} subtle /> : null}
                      </div>
                      <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                      <div>{humanizeRuntimeText(item.detail)}</div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    title="Časový priebeh rozhodnutia zatiaľ nie je dostupný."
                    description="Tento beh zatiaľ neposlal artefakty, z ktorých sa dá zostaviť spätný priebeh rozhodnutia."
                  />
                )}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Podporné dôkazy</h3>
              <div className="rtc-timeline">
                {brain.decisionReplay.evidence.length > 0 ? (
                  brain.decisionReplay.evidence.map((item) => (
                    <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                      <div className="rtc-live-card-header">
                        <strong>{humanizeRuntimeText(item.label)}</strong>
                        {item.severity ? <StatusBadge tone={toneFromSeverity(item.severity)} value={item.severity} subtle /> : null}
                      </div>
                      <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                      <div>{humanizeRuntimeText(item.detail)}</div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    title="Podporné dôkazy zatiaľ nie sú dostupné."
                    description="Tento beh zatiaľ neposlal podporné riadky pre spätné vysvetlenie."
                  />
                )}
              </div>
            </div>
          </div>
          <div className="rtc-pill-row">
            {brain.decisionReplay.linkedArtifacts.map((artifact) => (
              <StatusBadge key={artifact} tone="info" value={artifact} />
            ))}
          </div>
        </GlassPanel>
      </section>
    </div>
  );
}
