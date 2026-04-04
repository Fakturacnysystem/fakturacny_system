import React from "react";
import { EmptyState } from "@/components/ui/states";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type { BrainState } from "@/types/runtime";
import {
  formatMoment,
  formatOptionalNumber,
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
          eyebrow="Brain"
          title="Decision evidence graph"
          subtitle="Brain renders the runtime decision chain without inventing hidden confidence. Missing artifacts stay explicitly unavailable."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromPipelineStatus(brain.stateKind === "healthy" ? "pass" : "warn")} label="state" value={brain.stateKind} />
              <StatusBadge tone={toneFromVerdict(brain.actionState)} label="action" value={brain.actionState} />
              <StatusBadge tone={brain.marketRegime === "unavailable" ? "info" : "good"} label="regime" value={brain.marketRegime} />
              <StatusBadge tone={brain.executionEligibilityOutcome === "ordering_allowed" ? "good" : "warn"} label="execution gate" value={brain.executionEligibilityOutcome} />
            </div>
          )}
        />
        <div className="rtc-inline-note">updated {formatMoment(brain.lastUpdatedAt)}</div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Focus"
            title="Decision focus"
            subtitle="Selected symbol context comes from direct runtime evidence: quotes, blockers, last decision, and explicitly marked derived hints."
          />
          {selectedSymbolView ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Symbol / venue</span>
                  <strong>{selectedSymbolView.symbol} / {selectedSymbolView.venue}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Bid / ask</span>
                  <strong>
                    {selectedSymbolView.bid === null || selectedSymbolView.ask === null
                      ? "Unavailable"
                      : `${formatOptionalNumber(selectedSymbolView.bid)} / ${formatOptionalNumber(selectedSymbolView.ask)}`}
                  </strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Spread / depth</span>
                  <strong>
                    {selectedSymbolView.spreadBps === null
                      ? "Unavailable"
                      : `${formatOptionalNumber(selectedSymbolView.spreadBps)} bps`}
                    {" / "}
                    {selectedSymbolView.depthNotional === null
                      ? "Unavailable"
                      : formatOptionalNumber(selectedSymbolView.depthNotional)}
                  </strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Signal / forecast</span>
                  <strong>{selectedSymbolView.signal ?? "Unavailable"} / {selectedSymbolView.forecast ?? "Unavailable"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Confidence</span>
                  <strong>{selectedSymbolView.confidence === null ? "Unavailable" : formatOptionalNumber(selectedSymbolView.confidence, 3)}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Current block reason</span>
                  <strong>{selectedSymbolView.currentBlockReason ?? "none"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Last / next</span>
                  <strong>{selectedSymbolView.lastAction ?? "Unavailable"} / {selectedSymbolView.nextEligibleAction ?? "Unavailable"}</strong>
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
              title="No symbol brain payload is available."
              description="The active run has not emitted symbol-level brain evidence."
            />
          )}
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Explainability"
            title="Why / Why-Not"
            subtitle="The operator sees affirmative evidence, blocking reasons, and derived edge fields separately so explainability never over-claims certainty."
          />
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Why trade</h3>
              <ul className="rtc-list rtc-tight-list">
                {brain.whyTrade.length > 0 ? brain.whyTrade.map((item) => <li key={item}>{item}</li>) : <li>Unavailable</li>}
              </ul>
            </div>
            <div>
              <h3 className="rtc-section-title">Why not trade</h3>
              <ul className="rtc-list rtc-tight-list">
                {brain.whyNotTrade.length > 0 ? brain.whyNotTrade.map((item) => <li key={item}>{item}</li>) : <li>Unavailable</li>}
              </ul>
            </div>
          </div>
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Blocking reasons</span>
              <strong>{brain.blockingReasons.length > 0 ? brain.blockingReasons.join(", ") : "none"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Supporting signals</span>
              <strong>{brain.supportingSignals.length > 0 ? brain.supportingSignals.join(", ") : "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Cost-adjusted edge</span>
              <strong>{brain.costAdjustedEdgeBps === null ? "Unavailable" : `${formatOptionalNumber(brain.costAdjustedEdgeBps)} bps`}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Edge source</span>
              <strong>{brain.costAdjustedEdgeSource ?? "Unavailable"}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Sell floor</span>
              <strong>{brain.sellFloorStatus}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Risk gating</span>
              <strong>{brain.riskGatingOutcome}</strong>
            </div>
          </div>
          <ul className="rtc-list rtc-tight-list">
            {brain.evidenceNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </GlassPanel>
      </section>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Auction"
          title="Opportunity ranking"
          subtitle="The ranking view shows which playbook and pair won, how much backlog pressure remains, and whether the decision stack is under-trading or over-accepting."
        />
        {brain.opportunityRanking ? (
          <>
            <div className="rtc-kv">
              <div className="rtc-kv-row">
                <span>Selected playbook</span>
                <strong>{brain.opportunityRanking.selectedPlaybook ?? "Unavailable"}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Selected score</span>
                <strong>{brain.opportunityRanking.selectedScore == null ? "Unavailable" : formatOptionalNumber(brain.opportunityRanking.selectedScore, 3)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Backlog pressure</span>
                <strong>{brain.opportunityRanking.backlogPressure == null ? "Unavailable" : formatOptionalNumber(brain.opportunityRanking.backlogPressure, 3)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>False-negative / false-positive</span>
                <strong>
                  {brain.opportunityRanking.falseNegativeRate == null ? "Unavailable" : formatOptionalNumber(brain.opportunityRanking.falseNegativeRate, 3)}
                  {" / "}
                  {brain.opportunityRanking.falsePositiveRate == null ? "Unavailable" : formatOptionalNumber(brain.opportunityRanking.falsePositiveRate, 3)}
                </strong>
              </div>
            </div>
            <div className="rtc-table-wrap">
              <table className="rtc-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Playbook</th>
                    <th>Score</th>
                    <th>Net edge</th>
                    <th>Quality</th>
                    <th>Execution</th>
                  </tr>
                </thead>
                <tbody>
                  {(brain.opportunityRanking.topCandidates ?? []).length > 0 ? (
                    brain.opportunityRanking.topCandidates?.map((candidate) => (
                      <tr key={`${candidate.symbol}-${candidate.playbook}`}>
                        <td>{candidate.symbol}</td>
                        <td>{candidate.playbook}</td>
                        <td>{formatOptionalNumber(candidate.score, 3)}</td>
                        <td>{candidate.netEdgeBps == null ? "Unavailable" : `${formatOptionalNumber(candidate.netEdgeBps)} bps`}</td>
                        <td>{candidate.qualityOfEdge == null ? "Unavailable" : formatOptionalNumber(candidate.qualityOfEdge, 3)}</td>
                        <td>{candidate.executionPreference ?? "Unavailable"}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>No ranked opportunity backlog is available.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <EmptyState
            title="No opportunity ranking payload is available."
            description="The active run has not emitted autonomous decision ranking telemetry yet."
          />
        )}
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Pipeline"
          title="Decision Pipeline Map"
          subtitle="Every stage exposes its status, direct reason codes, evidence paths, and whether any field had to be derived from adjacent runtime artifacts."
        />
        {brain.pipeline.length > 0 ? (
          <div className="rtc-pipeline-grid">
            {brain.pipeline.map((step) => (
              <article className="rtc-pipeline-step" key={step.id}>
                <div className="rtc-live-card-header">
                  <strong>{step.title}</strong>
                  <div className="rtc-pill-row">
                    <StatusBadge tone={toneFromPipelineStatus(step.status)} value={step.status} subtle />
                    {step.derived ? <StatusBadge tone="info" value="derived" subtle /> : null}
                  </div>
                </div>
                <div className="rtc-kv rtc-kv-tight">
                  <div className="rtc-kv-row">
                    <span>Timestamp</span>
                    <strong>{formatMoment(step.timestamp)}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Latency</span>
                    <strong>{step.latencyMs === null ? "Unavailable" : `${formatOptionalNumber(step.latencyMs, 0)} ms`}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Inputs</span>
                    <strong>{step.inputSummary}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Outputs</span>
                    <strong>{step.outputSummary}</strong>
                  </div>
                </div>
                {step.reasonCodes.length > 0 ? (
                  <div className="rtc-pill-row">
                    {step.reasonCodes.map((reason) => (
                      <StatusBadge key={`${step.id}-${reason}`} tone="warn" value={reason} />
                    ))}
                  </div>
                ) : null}
                <ul className="rtc-list rtc-tight-list">
                  {step.evidence.map((item) => (
                    <li key={`${step.id}-${item}`}>{item}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No decision pipeline evidence is available for the active run."
            description={brain.evidenceNotes[0] ?? "The active run has not emitted decision pipeline artifacts yet."}
          />
        )}
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Symbols"
            title="Symbol Brain View"
            subtitle="Symbol rows remain evidence-bound. Quote, forecast, blocker, and last-action fields are shown only when present in the active runtime payload."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Bid / Ask</th>
                  <th>Spread</th>
                  <th>Depth</th>
                  <th>Signal</th>
                  <th>Forecast</th>
                  <th>Confidence</th>
                  <th>Block reason</th>
                  <th>Last / next</th>
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
                          ? "Unavailable"
                          : `${formatOptionalNumber(symbol.bid)} / ${formatOptionalNumber(symbol.ask)}`}
                      </td>
                      <td>{symbol.spreadBps === null ? "Unavailable" : `${formatOptionalNumber(symbol.spreadBps)} bps`}</td>
                      <td>{symbol.depthNotional === null ? "Unavailable" : formatOptionalNumber(symbol.depthNotional)}</td>
                      <td>{symbol.signal ?? "Unavailable"}</td>
                      <td>{symbol.forecast ?? "Unavailable"}</td>
                      <td>{symbol.confidence === null ? "Unavailable" : formatOptionalNumber(symbol.confidence, 3)}</td>
                      <td>{symbol.currentBlockReason ?? "none"}</td>
                      <td>
                        <div>{symbol.lastAction ?? "Unavailable"}</div>
                        <div className="rtc-inline-note">next {symbol.nextEligibleAction ?? "Unavailable"}</div>
                        {symbol.derivedFields.length > 0 ? (
                          <div className="rtc-pill-row">
                            {symbol.derivedFields.map((field) => (
                              <StatusBadge key={`${symbol.symbol}-${field}`} tone="info" value={field} subtle />
                            ))}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9}>No symbol brain payload is available.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Replay"
            title="Decision Replay"
            subtitle="Replay is coupled to the effective run identity. If replay ever diverges from the active run, the runtime identity card surfaces the mismatch explicitly."
          />
          <div className="rtc-kv">
            <div className="rtc-kv-row">
              <span>Final verdict</span>
              <strong>{brain.decisionReplay.finalVerdict}</strong>
            </div>
            <div className="rtc-kv-row">
              <span>Linked artifacts</span>
              <strong>{brain.decisionReplay.linkedArtifacts.length}</strong>
            </div>
          </div>
          <div className="rtc-mini-grid">
            <div>
              <h3 className="rtc-section-title">Timeline</h3>
              <div className="rtc-timeline">
                {brain.decisionReplay.timeline.length > 0 ? (
                  brain.decisionReplay.timeline.map((item) => (
                    <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                      <div className="rtc-live-card-header">
                        <strong>{item.label}</strong>
                        {item.severity ? <StatusBadge tone={toneFromSeverity(item.severity)} value={item.severity} subtle /> : null}
                      </div>
                      <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                      <div>{item.detail}</div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    title="Replay timeline unavailable for the active run."
                    description="The run has not emitted replay timeline artifacts yet."
                  />
                )}
              </div>
            </div>
            <div>
              <h3 className="rtc-section-title">Supporting evidence</h3>
              <div className="rtc-timeline">
                {brain.decisionReplay.evidence.length > 0 ? (
                  brain.decisionReplay.evidence.map((item) => (
                    <div className="rtc-timeline-item" key={`${item.label}-${item.ts}`}>
                      <div className="rtc-live-card-header">
                        <strong>{item.label}</strong>
                        {item.severity ? <StatusBadge tone={toneFromSeverity(item.severity)} value={item.severity} subtle /> : null}
                      </div>
                      <div className="rtc-inline-note">{formatMoment(item.ts)}</div>
                      <div>{item.detail}</div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    title="No replay evidence rows are available."
                    description="The active run has not emitted supporting replay rows."
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
