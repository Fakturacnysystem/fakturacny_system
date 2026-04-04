import React from "react";
import { EmptyState } from "@/components/ui/states";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type { ExecutionOrder, ExecutionState } from "@/types/runtime";
import {
  formatMoment,
  formatOptionalNumber,
  toneFromSeverity,
  toneFromVerdict,
} from "@/components/screen-formatters";

function orderFocus(order: ExecutionOrder | null) {
  if (!order) {
    return null;
  }
  return [
    order.rejectedTs,
    order.filledTs,
    order.acknowledgedTs,
    order.submittedTs,
    order.decisionTs,
    ...order.transitions.map((item) => item.ts),
  ]
    .filter(Boolean)
    .sort()
    .pop() ?? null;
}

export function ExecutionScreen({ execution }: { execution: ExecutionState }) {
  const focusedOrder =
    execution.orders
      .slice()
      .sort((left, right) => {
        const rightTs = orderFocus(right) ?? "";
        const leftTs = orderFocus(left) ?? "";
        return rightTs.localeCompare(leftTs);
      })[0] ?? null;
  const alphaSections: Array<{ label: string; payload: Record<string, unknown> | undefined }> = execution.alphaTelemetry
    ? [
        { label: "Private stream", payload: execution.alphaTelemetry.privateStreamHealth },
        { label: "Reject taxonomy", payload: execution.alphaTelemetry.orderRejectTaxonomy },
        { label: "Maker first", payload: execution.alphaTelemetry.makerFirstEffectiveness },
        { label: "Quality bucket", payload: execution.alphaTelemetry.executionQualityBucket },
        { label: "Entry timing", payload: execution.alphaTelemetry.entryTimingOptimizer },
        { label: "Adaptive cadence", payload: execution.alphaTelemetry.adaptiveCadence },
        { label: "Live degradation", payload: execution.alphaTelemetry.liveDegradation },
        { label: "Self throttling", payload: execution.alphaTelemetry.selfThrottling },
      ]
    : [];

  return (
    <div className="rtc-screen-panel">
      <GlassPanel className="rtc-screen-hero-card" elevated>
        <SectionHeader
          eyebrow="Execution"
          title="Order, position, and venue observability"
          subtitle="Execution shows only what the run actually emitted: lifecycle events, direct fee and slippage fields, current exposure, and reconciliation-linked notes."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromSeverity(execution.stateKind)} label="state" value={execution.stateKind} />
              <StatusBadge tone={execution.orders.length > 0 ? "good" : "warn"} label="orders" value={String(execution.orders.length)} />
              <StatusBadge tone={execution.positions.length > 0 ? "good" : "info"} label="positions" value={String(execution.positions.length)} />
              <StatusBadge tone={execution.linkedArtifacts.length > 0 ? "good" : "warn"} label="evidence" value={`${execution.linkedArtifacts.length} artifacts`} />
            </div>
          )}
        />
        <div className="rtc-inline-note">updated {formatMoment(execution.lastUpdatedAt)}</div>
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Quality"
          title="Execution Quality"
          subtitle="Summary cards keep raw counters and derived metrics separate so fill rate, rejection rate, and fee leakage are visibly traceable."
        />
        <div className="rtc-summary-grid rtc-summary-grid-wide">
          {execution.summary.map((metric) => (
            <article className="rtc-summary-card" data-tone={metric.derived ? "info" : metric.value === null ? "warn" : "good"} key={metric.label}>
              <div className="rtc-summary-label">{metric.label}</div>
              <div className="rtc-summary-value">
                {metric.value === null ? "Unavailable" : formatOptionalNumber(metric.value, metric.unit === "percent" ? 2 : metric.unit === "count" ? 0 : 4)}
                {metric.value === null ? "" : metric.unit === "count" ? "" : ` ${metric.unit}`}
              </div>
              <div className="rtc-summary-hint">{metric.detail}</div>
            </article>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Alpha"
          title="Execution alpha telemetry"
          subtitle="These panels expose stream health, reject taxonomy, maker-first effectiveness, cadence, degradation, and throttling without over-claiming execution certainty."
        />
        {execution.alphaTelemetry ? (
          <div className="rtc-mini-grid">
            {alphaSections.map(({ label, payload }) => (
              <article className="rtc-state-card" key={label}>
                <div className="rtc-live-card-header">
                  <strong>{label}</strong>
                  <StatusBadge tone="info" value="telemetry" subtle />
                </div>
                <div className="rtc-code">{JSON.stringify(payload ?? {}, null, 2)}</div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No execution alpha telemetry is available."
            description="The active run has not emitted fill-aware execution diagnostics yet."
          />
        )}
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Orders"
          title="Orders"
          subtitle="Lifecycle states are reconstructed from direct order and fill events only. Missing OMS or venue fields remain unavailable instead of being back-filled by the UI."
        />
        <div className="rtc-table-wrap">
          <table className="rtc-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Symbol / side</th>
                <th>Qty / notional</th>
                <th>Price</th>
                <th>Fees / slippage</th>
                <th>Status</th>
                <th>Timestamps</th>
                <th>Venue / reject</th>
              </tr>
            </thead>
            <tbody>
              {execution.orders.length > 0 ? (
                execution.orders.map((order) => (
                  <tr key={order.id}>
                    <td>
                      <strong>{order.id}</strong>
                      {order.derivedFields.length > 0 ? (
                        <div className="rtc-pill-row">
                          {order.derivedFields.map((field) => (
                            <StatusBadge key={`${order.id}-${field}`} tone="info" value={field} subtle />
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div>{order.symbol}</div>
                      <div className="rtc-inline-note">{order.side ?? "Unavailable"}</div>
                    </td>
                    <td>
                      <div>{order.quantity === null ? "qty unavailable" : formatOptionalNumber(order.quantity, 8)}</div>
                      <div className="rtc-inline-note">
                        {order.targetNotional === null ? "notional unavailable" : `notional ${formatOptionalNumber(order.targetNotional, 6)}`}
                      </div>
                    </td>
                    <td>{order.price === null ? "Unavailable" : formatOptionalNumber(order.price, 6)}</td>
                    <td>
                      <div>{order.fees === null ? "fees unavailable" : `fee ${formatOptionalNumber(order.fees, 8)}`}</div>
                      <div className="rtc-inline-note">
                        {order.slippage === null ? "slippage unavailable" : `slippage ${formatOptionalNumber(order.slippage, 8)}`}
                      </div>
                    </td>
                    <td>
                      <StatusBadge tone={toneFromVerdict(order.status)} value={order.status} subtle />
                    </td>
                    <td>
                      <div>decision {formatMoment(order.decisionTs)}</div>
                      <div className="rtc-inline-note">submitted {formatMoment(order.submittedTs)}</div>
                      <div className="rtc-inline-note">filled {formatMoment(order.filledTs)}</div>
                      <div className="rtc-inline-note">rejected {formatMoment(order.rejectedTs)}</div>
                    </td>
                    <td>
                      <div>{order.venueResponseSummary ?? "Unavailable"}</div>
                      <div className="rtc-inline-note">{order.rejectionReason ?? "no rejection reason"}</div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8}>No execution order lifecycle payload is available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Positions"
            title="Positions"
            subtitle="Current exposure only appears when position or account snapshots can prove it. Flat runs remain flat rather than showing synthetic exposure cards."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side / qty</th>
                  <th>Exposure</th>
                  <th>Entry / mark</th>
                  <th>Unrealized / realized</th>
                  <th>Exit eligibility</th>
                  <th>Sell floor</th>
                </tr>
              </thead>
              <tbody>
                {execution.positions.length > 0 ? (
                  execution.positions.map((position) => (
                    <tr key={`${position.symbol}-${position.ts}`}>
                      <td>
                        <strong>{position.symbol}</strong>
                        {position.derivedFields.length > 0 ? (
                          <div className="rtc-pill-row">
                            {position.derivedFields.map((field) => (
                              <StatusBadge key={`${position.symbol}-${field}`} tone="info" value={field} subtle />
                            ))}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <div>{position.side ?? "Unavailable"}</div>
                        <div className="rtc-inline-note">qty {position.quantity === null ? "Unavailable" : formatOptionalNumber(position.quantity, 8)}</div>
                      </td>
                      <td>{position.exposureNotional === null ? "Unavailable" : formatOptionalNumber(position.exposureNotional, 6)}</td>
                      <td>
                        <div>{position.entryPrice === null ? "entry unavailable" : `entry ${formatOptionalNumber(position.entryPrice, 6)}`}</div>
                        <div className="rtc-inline-note">{position.markPrice === null ? "mark unavailable" : `mark ${formatOptionalNumber(position.markPrice, 6)}`}</div>
                      </td>
                      <td>
                        <div>{position.unrealizedPnl === null ? "uPnL unavailable" : `uPnL ${formatOptionalNumber(position.unrealizedPnl, 6)}`}</div>
                        <div className="rtc-inline-note">{position.realizedPnl === null ? "rPnL unavailable" : `rPnL ${formatOptionalNumber(position.realizedPnl, 6)}`}</div>
                      </td>
                      <td>{position.exitEligibility ?? "Unavailable"}</td>
                      <td>{position.sellFloorStatus ?? "Unavailable"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>No open positions are observable from the active run.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Account"
            title="Account Truth"
            subtitle="This snapshot comes directly from account event telemetry. Balance, fees, slippage, and exposure are shown only when emitted by the run."
          />
          {execution.accountSnapshot ? (
            <div className="rtc-kv">
              <div className="rtc-kv-row">
                <span>Venue / symbol</span>
                <strong>{execution.accountSnapshot.venue ?? "Unavailable"} / {execution.accountSnapshot.symbol ?? "Unavailable"}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Baseline / exchange balance</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.baselineBalance, 6)} / {formatOptionalNumber(execution.accountSnapshot.exchangeBalance, 6)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Exposure / fills</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.grossExposureNotional, 6)} / {formatOptionalNumber(execution.accountSnapshot.fillCount, 0)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Fees / slippage</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.cumulativeFees, 8)} / {formatOptionalNumber(execution.accountSnapshot.cumulativeSlippage, 8)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Realized / unrealized PnL</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.realizedPnl, 6)} / {formatOptionalNumber(execution.accountSnapshot.unrealizedPnl, 6)}</strong>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No direct account snapshot is available for the active run."
              description="The run has not emitted authoritative account telemetry yet."
            />
          )}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Timeline"
            title="Execution Timeline"
            subtitle="Timeline focuses on the latest order with observable lifecycle transitions, then falls back to global execution events. No synthetic ordering path is invented."
          />
          {focusedOrder ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Focused order</span>
                  <strong>{focusedOrder.id}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Symbol / status</span>
                  <strong>{focusedOrder.symbol} / {focusedOrder.status}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Venue summary</span>
                  <strong>{focusedOrder.venueResponseSummary ?? "Unavailable"}</strong>
                </div>
              </div>
              <div className="rtc-timeline">
                {focusedOrder.transitions.length > 0 ? (
                  focusedOrder.transitions.map((item) => (
                    <div className="rtc-timeline-item" key={`${focusedOrder.id}-${item.label}-${item.ts}`}>
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
                    title="Focused order has no emitted lifecycle transitions."
                    description="The order exists but did not emit any timeline transitions."
                  />
                )}
              </div>
            </>
          ) : (
            <EmptyState
              title="No order is available to anchor a focused execution timeline."
              description="The active run has not emitted enough order evidence to build a focused lifecycle view."
            />
          )}
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Venue"
            title="Venue / Lifecycle Truth"
            subtitle="Authenticated stream posture, lifecycle proof, reconciliation, and execution plan style are all sourced from emitted telemetry, not UI reconstruction."
          />
          {execution.venueTelemetry ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>User stream</span>
                  <strong>{execution.venueTelemetry.userStreamStatus}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Last event</span>
                  <strong>{execution.venueTelemetry.lastUserStreamEvent ?? "Unavailable"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Lifecycle status</span>
                  <strong>{execution.venueTelemetry.lifecycleStatus}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Reconciliation</span>
                  <strong>{execution.venueTelemetry.reconciliationStatus ?? "Unavailable"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Execution style / fill probability</span>
                  <strong>{execution.venueTelemetry.executionPlanStyle ?? "Unavailable"} / {formatOptionalNumber(execution.venueTelemetry.fillProbability, 2)}</strong>
                </div>
              </div>
              <div className="rtc-pill-row">
                {execution.venueTelemetry.subscribedChannels.length > 0
                  ? execution.venueTelemetry.subscribedChannels.map((channel) => (
                      <StatusBadge key={channel} tone="info" value={channel} />
                    ))
                  : <StatusBadge tone="warn" value="no subscriptions emitted" />}
                {execution.venueTelemetry.lifecycleGapReasons.map((reason) => (
                  <StatusBadge key={reason} tone="warn" value={reason} />
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title="No venue telemetry is available for the active run."
              description="The run has not emitted user-stream or lifecycle evidence yet."
            />
          )}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Fabric"
            title="Execution Fabric"
            subtitle="Global execution events remain visible even when no single order has a complete lifecycle. This helps operators see what the runtime actually emitted."
          />
          <div className="rtc-timeline">
            {execution.timeline.length > 0 ? (
              execution.timeline.map((item) => (
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
                title="No global execution timeline events are available."
                description="The run has not emitted a global execution fabric yet."
              />
            )}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Notes"
            title="Data Notes"
            subtitle="These notes explain where the surface is intentionally incomplete and which files back the current execution state."
          />
          <ul className="rtc-list rtc-tight-list">
            {execution.dataNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div className="rtc-pill-row">
            {execution.linkedArtifacts.length > 0 ? (
              execution.linkedArtifacts.map((artifact) => (
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
