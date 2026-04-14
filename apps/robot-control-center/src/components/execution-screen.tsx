import React from "react";
import { EmptyState } from "@/components/ui/states";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import type { ExecutionOrder, ExecutionState } from "@/types/runtime";
import {
  formatMoment,
  formatOptionalNumber,
  humanizeRuntimeText,
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
        { label: "Súkromný stream", payload: execution.alphaTelemetry.privateStreamHealth },
        { label: "Druhy zamietnutí", payload: execution.alphaTelemetry.orderRejectTaxonomy },
        { label: "Preferencia maker", payload: execution.alphaTelemetry.makerFirstEffectiveness },
        { label: "Kôš kvality", payload: execution.alphaTelemetry.executionQualityBucket },
        { label: "Načasovanie vstupu", payload: execution.alphaTelemetry.entryTimingOptimizer },
        { label: "Prispôsobenie tempa", payload: execution.alphaTelemetry.adaptiveCadence },
        { label: "Zhoršenie live stavu", payload: execution.alphaTelemetry.liveDegradation },
        { label: "Samospomaľovanie", payload: execution.alphaTelemetry.selfThrottling },
      ]
    : [];

  return (
    <div className="rtc-screen-panel">
      <GlassPanel className="rtc-screen-hero-card" elevated>
        <SectionHeader
          eyebrow="Obchody"
          title="Čo sa naozaj stalo pri pokynoch a obchodoch"
          subtitle="Táto obrazovka ukazuje len to, čo beh skutočne poslal: priebeh pokynov, poplatky, sklz ceny, expozíciu a poznámky z kontroly zhody."
          meta={(
            <div className="rtc-pill-row">
              <StatusBadge tone={toneFromSeverity(execution.stateKind)} label="stav" value={execution.stateKind} />
              <StatusBadge tone={execution.orders.length > 0 ? "good" : "warn"} label="pokyny" value={String(execution.orders.length)} />
              <StatusBadge tone={execution.positions.length > 0 ? "good" : "info"} label="pozície" value={String(execution.positions.length)} />
              <StatusBadge tone={execution.linkedArtifacts.length > 0 ? "good" : "warn"} label="dôkazy" value={`${execution.linkedArtifacts.length} súborov`} />
            </div>
          )}
        />
        <div className="rtc-inline-note">aktualizované {formatMoment(execution.lastUpdatedAt)}</div>
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Kvalita"
          title="Kvalita vykonania"
          subtitle="Súhrn necháva vedľa seba surové počty aj odvodené metriky, aby bolo jasné, koľko pokynov sa naozaj vykonalo a koľko sa stratilo na poplatkoch či zamietnutiach."
        />
        <div className="rtc-summary-grid rtc-summary-grid-wide">
          {execution.summary.map((metric) => (
            <article className="rtc-summary-card" data-tone={metric.derived ? "info" : metric.value === null ? "warn" : "good"} key={metric.label}>
              <div className="rtc-summary-label">{metric.label}</div>
              <div className="rtc-summary-value">
                {metric.value === null ? "Nedostupné" : formatOptionalNumber(metric.value, metric.unit === "percent" ? 2 : metric.unit === "count" ? 0 : 4)}
                {metric.value === null ? "" : metric.unit === "count" ? "" : ` ${metric.unit}`}
              </div>
              <div className="rtc-summary-hint">{metric.detail}</div>
            </article>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Telemetria"
          title="Doplnkové údaje o vykonaní"
          subtitle="Tu sú pomocné telemetrie o zdraví streamu, typoch zamietnutí, preferovanom type pokynov a spomaľovaní. Nehovoria viac, než čo naozaj prišlo z behu."
        />
        {execution.alphaTelemetry ? (
          <div className="rtc-mini-grid">
            {alphaSections.map(({ label, payload }) => (
              <article className="rtc-state-card" key={label}>
                <div className="rtc-live-card-header">
                    <strong>{humanizeRuntimeText(label)}</strong>
                  <StatusBadge tone="info" value="telemetria" subtle />
                </div>
                <div className="rtc-code">{JSON.stringify(payload ?? {}, null, 2)}</div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Doplnková telemetria o vykonaní zatiaľ nie je dostupná."
            description="Tento beh zatiaľ neposlal rozšírené diagnostické údaje o priebehu vykonania."
          />
        )}
      </GlassPanel>

      <GlassPanel interactive>
        <SectionHeader
          eyebrow="Pokyny"
          title="Pokyny"
          subtitle="Priebeh pokynov sa skladá len z priamych udalostí o pokynoch a obchodoch. Chýbajúce údaje z burzy alebo OMS panel nedopočítava."
        />
        <div className="rtc-table-wrap">
          <table className="rtc-table">
            <thead>
              <tr>
                  <th>Pokyn</th>
                  <th>Pár / smer</th>
                  <th>Množstvo / objem</th>
                  <th>Cena</th>
                  <th>Poplatky / sklz</th>
                  <th>Stav</th>
                  <th>Časy</th>
                  <th>Burza / dôvod zamietnutia</th>
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
                        <div className="rtc-inline-note">{order.side ? humanizeRuntimeText(order.side) : "Nedostupné"}</div>
                    </td>
                    <td>
                        <div>{order.quantity === null ? "množstvo nedostupné" : formatOptionalNumber(order.quantity, 8)}</div>
                        <div className="rtc-inline-note">
                          {order.targetNotional === null ? "objem nedostupný" : `objem ${formatOptionalNumber(order.targetNotional, 6)}`}
                        </div>
                      </td>
                    <td>{order.price === null ? "Nedostupné" : formatOptionalNumber(order.price, 6)}</td>
                    <td>
                      <div>{order.fees === null ? "poplatok nedostupný" : `poplatok ${formatOptionalNumber(order.fees, 8)}`}</div>
                      <div className="rtc-inline-note">
                        {order.slippage === null ? "sklz nedostupný" : `sklz ${formatOptionalNumber(order.slippage, 8)}`}
                      </div>
                    </td>
                    <td>
                      <StatusBadge tone={toneFromVerdict(order.status)} value={order.status} subtle />
                    </td>
                    <td>
                      <div>rozhodnutie {formatMoment(order.decisionTs)}</div>
                      <div className="rtc-inline-note">odoslané {formatMoment(order.submittedTs)}</div>
                      <div className="rtc-inline-note">vykonané {formatMoment(order.filledTs)}</div>
                      <div className="rtc-inline-note">zamietnuté {formatMoment(order.rejectedTs)}</div>
                    </td>
                    <td>
                      <div>{order.venueResponseSummary ? humanizeRuntimeText(order.venueResponseSummary) : "Nedostupné"}</div>
                      <div className="rtc-inline-note">{order.rejectionReason ? humanizeRuntimeText(order.rejectionReason) : "bez dôvodu zamietnutia"}</div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8}>Zatiaľ nie je k dispozícii priebeh pokynov.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </GlassPanel>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Pozície"
            title="Pozície"
            subtitle="Aktuálna expozícia sa ukáže len vtedy, keď ju vedia potvrdiť pozície alebo stav účtu. Panel nevytvára žiadne umelé pozície."
          />
          <div className="rtc-table-wrap">
            <table className="rtc-table">
              <thead>
                <tr>
                  <th>Pár</th>
                  <th>Smer / množstvo</th>
                  <th>Expozícia</th>
                  <th>Vstup / aktuálna cena</th>
                  <th>Nerealizovaný / realizovaný výsledok</th>
                  <th>Možnosť ukončenia</th>
                  <th>Minimálna predajná hranica</th>
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
                        <div>{position.side ? humanizeRuntimeText(position.side) : "Nedostupné"}</div>
                        <div className="rtc-inline-note">množstvo {position.quantity === null ? "Nedostupné" : formatOptionalNumber(position.quantity, 8)}</div>
                      </td>
                      <td>{position.exposureNotional === null ? "Nedostupné" : formatOptionalNumber(position.exposureNotional, 6)}</td>
                      <td>
                        <div>{position.entryPrice === null ? "vstup nedostupný" : `vstup ${formatOptionalNumber(position.entryPrice, 6)}`}</div>
                        <div className="rtc-inline-note">{position.markPrice === null ? "aktuálna cena nedostupná" : `cena ${formatOptionalNumber(position.markPrice, 6)}`}</div>
                      </td>
                      <td>
                        <div>{position.unrealizedPnl === null ? "priebežný výsledok nedostupný" : `priebežný ${formatOptionalNumber(position.unrealizedPnl, 6)}`}</div>
                        <div className="rtc-inline-note">{position.realizedPnl === null ? "realizovaný výsledok nedostupný" : `realizovaný ${formatOptionalNumber(position.realizedPnl, 6)}`}</div>
                      </td>
                      <td>{position.exitEligibility ? humanizeRuntimeText(position.exitEligibility) : "Nedostupné"}</td>
                      <td>{position.sellFloorStatus ? humanizeRuntimeText(position.sellFloorStatus) : "Nedostupné"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>Z tohto behu zatiaľ nie sú pozorovateľné žiadne otvorené pozície.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Účet"
            title="Skutočný stav účtu"
            subtitle="Tento prehľad ide priamo z udalostí účtu. Zostatok, poplatky, sklz a expozícia sa ukazujú len vtedy, keď ich beh naozaj poslal."
          />
          {execution.accountSnapshot ? (
            <div className="rtc-kv">
              <div className="rtc-kv-row">
                <span>Burza / pár</span>
                <strong>{execution.accountSnapshot.venue ?? "Nedostupné"} / {execution.accountSnapshot.symbol ?? "Nedostupné"}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Počiatočný / aktuálny zostatok</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.baselineBalance, 6)} / {formatOptionalNumber(execution.accountSnapshot.exchangeBalance, 6)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Expozícia / počet vykonaní</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.grossExposureNotional, 6)} / {formatOptionalNumber(execution.accountSnapshot.fillCount, 0)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Poplatky / sklz</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.cumulativeFees, 8)} / {formatOptionalNumber(execution.accountSnapshot.cumulativeSlippage, 8)}</strong>
              </div>
              <div className="rtc-kv-row">
                <span>Realizovaný / priebežný výsledok</span>
                <strong>{formatOptionalNumber(execution.accountSnapshot.realizedPnl, 6)} / {formatOptionalNumber(execution.accountSnapshot.unrealizedPnl, 6)}</strong>
              </div>
            </div>
          ) : (
            <EmptyState
              title="Priamy stav účtu zatiaľ nie je dostupný."
              description="Tento beh zatiaľ neposlal spoľahlivú telemetriu o účte."
            />
          )}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Priebeh"
            title="Časový priebeh obchodov"
            subtitle="Táto časť sa zameria na najnovší pokyn s pozorovateľným priebehom. Keď taký nie je, ukáže aspoň globálne udalosti vykonania bez domýšľania."
          />
          {focusedOrder ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Sledovaný pokyn</span>
                  <strong>{focusedOrder.id}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Pár / stav</span>
                  <strong>{focusedOrder.symbol} / {humanizeRuntimeText(focusedOrder.status)}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Zhrnutie z burzy</span>
                  <strong>{focusedOrder.venueResponseSummary ?? "Nedostupné"}</strong>
                </div>
              </div>
              <div className="rtc-timeline">
                {focusedOrder.transitions.length > 0 ? (
                  focusedOrder.transitions.map((item) => (
                    <div className="rtc-timeline-item" key={`${focusedOrder.id}-${item.label}-${item.ts}`}>
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
                    title="Tento pokyn zatiaľ nemá zaznamenaný priebeh krokov."
                    description="Pokyn existuje, ale neposlal žiadne udalosti o svojom ďalšom priebehu."
                  />
                )}
              </div>
            </>
          ) : (
            <EmptyState
              title="Nie je k dispozícii pokyn, na ktorom by sa dal ukázať detailný priebeh."
              description="Tento beh zatiaľ neposlal dosť dôkazov o pokynoch na zostavenie detailného časového priebehu."
            />
          )}
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Burza"
            title="Pravda o burze a priebehu"
            subtitle="Stav prihláseného streamu, dôkazy o priebehu, zhoda účtovania aj štýl vykonania sa berú priamo z telemetrie, nie z dopočtu v UI."
          />
          {execution.venueTelemetry ? (
            <>
              <div className="rtc-kv">
                <div className="rtc-kv-row">
                  <span>Používateľský stream</span>
                  <strong>{humanizeRuntimeText(execution.venueTelemetry.userStreamStatus)}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Posledná udalosť</span>
                  <strong>{execution.venueTelemetry.lastUserStreamEvent ? humanizeRuntimeText(execution.venueTelemetry.lastUserStreamEvent) : "Nedostupné"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Stav priebehu</span>
                  <strong>{humanizeRuntimeText(execution.venueTelemetry.lifecycleStatus)}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Zhoda účtovania</span>
                  <strong>{execution.venueTelemetry.reconciliationStatus ? humanizeRuntimeText(execution.venueTelemetry.reconciliationStatus) : "Nedostupné"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Štýl vykonania / pravdepodobnosť vykonania</span>
                  <strong>{execution.venueTelemetry.executionPlanStyle ? humanizeRuntimeText(execution.venueTelemetry.executionPlanStyle) : "Nedostupné"} / {formatOptionalNumber(execution.venueTelemetry.fillProbability, 2)}</strong>
                </div>
              </div>
              <div className="rtc-pill-row">
                {execution.venueTelemetry.subscribedChannels.length > 0
                  ? execution.venueTelemetry.subscribedChannels.map((channel) => (
                      <StatusBadge key={channel} tone="info" value={humanizeRuntimeText(channel)} />
                    ))
                  : <StatusBadge tone="warn" value="bez odoslaných odberov" />}
                {execution.venueTelemetry.lifecycleGapReasons.map((reason) => (
                  <StatusBadge key={reason} tone="warn" value={humanizeRuntimeText(reason)} />
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title="Telemetria z burzy zatiaľ nie je dostupná."
              description="Tento beh zatiaľ neposlal údaje o používateľskom streame ani o priebehu vykonania."
            />
          )}
        </GlassPanel>
      </section>

      <section className="rtc-grid rtc-grid-main">
        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Udalosti"
            title="Celkový priebeh vykonania"
            subtitle="Aj keď žiadny jednotlivý pokyn nemá celý priebeh, tu zostávajú viditeľné globálne udalosti o vykonaní. Vidíš teda aspoň to, čo systém naozaj poslal."
          />
          <div className="rtc-timeline">
            {execution.timeline.length > 0 ? (
              execution.timeline.map((item) => (
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
                title="Globálne udalosti o vykonaní zatiaľ nie sú dostupné."
                description="Tento beh zatiaľ neposlal globálny priebeh vykonania."
              />
            )}
          </div>
        </GlassPanel>

        <GlassPanel interactive>
          <SectionHeader
            eyebrow="Poznámky"
            title="Poznámky k údajom"
            subtitle="Tieto poznámky vysvetľujú, kde je obrazovka úmyselne neúplná a ktoré súbory podkladajú aktuálny stav obchodov."
          />
          <ul className="rtc-list rtc-tight-list">
            {execution.dataNotes.map((note) => (
              <li key={note}>{humanizeRuntimeText(note)}</li>
            ))}
          </ul>
          <div className="rtc-pill-row">
            {execution.linkedArtifacts.length > 0 ? (
              execution.linkedArtifacts.map((artifact) => (
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
