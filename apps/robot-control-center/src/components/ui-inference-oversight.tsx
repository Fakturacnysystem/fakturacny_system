import React from "react";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
import { humanizeRuntimeText } from "@/components/screen-formatters";
import type { UiInferenceContract } from "@/types/contracts";

function toneForStatus(value: string): "good" | "warn" | "danger" | "info" {
  if (["breach", "fail"].includes(value)) {
    return "danger";
  }
  if (["watch", "warn"].includes(value)) {
    return "warn";
  }
  if (["contained", "pass"].includes(value)) {
    return "good";
  }
  return "info";
}

export function UiInferenceOversight({ oversight }: { oversight: UiInferenceContract }) {
  return (
    <GlassPanel>
      <SectionHeader
        eyebrow="Kontrola pravdivosti"
        title="Dohľad nad tým, čo si UI iba odvodilo"
        subtitle="Tu vidíš, kde aplikácia ukazuje priamo reálne údaje, kde niečo dopočítala, a kde úmyselne priznáva, že údaj chýba."
        meta={(
          <div className="rtc-pill-row">
            <StatusBadge tone={toneForStatus(oversight.status)} label="dohľad" value={oversight.status} />
            <StatusBadge tone={oversight.source === "runtime-api" ? "good" : "danger"} label="zdroj" value={oversight.source} />
          </div>
        )}
      />

      <div className="rtc-summary-grid rtc-summary-grid-wide">
        <article className="rtc-summary-card" data-tone={toneForStatus(oversight.status)}>
          <div className="rtc-summary-label">Stav dohľadu</div>
          <div className="rtc-summary-value">{oversight.status}</div>
          <div className="rtc-summary-hint">Stav „contained“ znamená, že aplikácia momentálne nič neschováva ani si tajne nedomýšľa.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.derivedFieldCount > 0 ? "warn" : "good"}>
          <div className="rtc-summary-label">Odvodené polia</div>
          <div className="rtc-summary-value">{oversight.derivedFieldCount}</div>
          <div className="rtc-summary-hint">Každá dopočítaná hodnota musí byť na obrazovke jasne označená.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.unavailableFieldCount > 0 ? "warn" : "good"}>
          <div className="rtc-summary-label">Chýbajúce hodnoty</div>
          <div className="rtc-summary-value">{oversight.unavailableFieldCount}</div>
          <div className="rtc-summary-hint">Keď údaj chýba, UI ho nedopĺňa nasilu a radšej to otvorene prizná.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.linkedArtifactCount > 0 ? "good" : "warn"}>
          <div className="rtc-summary-label">Napojené dôkazy</div>
          <div className="rtc-summary-value">{oversight.linkedArtifactCount}</div>
          <div className="rtc-summary-hint">Počet súborov a dôkazov, o ktoré sa aktuálna obrazovka opiera.</div>
        </article>
      </div>

      <div className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel compact className="rtc-nested-panel" interactive>
          <SectionHeader
            eyebrow="Prehľad"
            title="Stav jednotlivých obrazoviek"
            subtitle="Každá obrazovka má vlastný stav dôkazov, aby sa Hlavný panel, Rozhodovanie, Bezpečnosť a Obchody neschovali za jedno spoločné číslo."
            compact
          />
          <div className="rtc-state-grid rtc-state-grid-tight">
            {oversight.surfaces.map((surface) => (
              <article className="rtc-state-card" key={surface.id}>
                <div className="rtc-live-card-header">
                  <strong>{surface.label}</strong>
                  <StatusBadge tone={toneForStatus(surface.status)} value={surface.status} subtle />
                </div>
                <div className="rtc-kv rtc-kv-tight">
                  <div className="rtc-kv-row">
                    <span>Priame dôkazy</span>
                    <strong>{surface.directEvidenceCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Odvodené polia</span>
                    <strong>{surface.derivedFieldCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Chýbajúce hodnoty</span>
                    <strong>{surface.unavailableFieldCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Napojené dôkazy</span>
                    <strong>{surface.linkedArtifactCount}</strong>
                  </div>
                </div>
                <ul className="rtc-list rtc-tight-list">
                  {surface.notes.map((note) => (
                    <li key={`${surface.id}-${note}`}>{humanizeRuntimeText(note)}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel compact className="rtc-nested-panel" interactive>
          <SectionHeader
            eyebrow="Kontroly"
            title="Kontroly pravdivosti"
            subtitle="Tieto kontroly hovoria, či samotná aplikácia pracuje poctivo: či je jasný zdroj dát, či je beh zamknutý správne, či si časti neprotirečia a či sú odvodené údaje priznané."
            compact
          />
          <div className="rtc-state-grid rtc-state-grid-tight">
            {oversight.rules.map((rule) => (
              <article className="rtc-state-card" key={rule.label}>
                <div className="rtc-live-card-header">
                  <strong>{rule.label}</strong>
                  <StatusBadge tone={toneForStatus(rule.status)} value={rule.status} subtle />
                </div>
                <div className="rtc-inline-note">{humanizeRuntimeText(rule.detail)}</div>
              </article>
            ))}
          </div>
          <ul className="rtc-list rtc-tight-list">
            {oversight.notes.map((note) => (
              <li key={note}>{humanizeRuntimeText(note)}</li>
            ))}
          </ul>
        </GlassPanel>
      </div>
    </GlassPanel>
  );
}
