import React from "react";
import { GlassPanel, SectionHeader, StatusBadge } from "@/components/ui/surface";
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
        eyebrow="Truth discipline"
        title="UI inference oversight"
        subtitle="This ledger monitors where the cockpit is showing direct runtime evidence, where values are derived, and where the UI is intentionally incomplete."
        meta={(
          <div className="rtc-pill-row">
            <StatusBadge tone={toneForStatus(oversight.status)} label="oversight" value={oversight.status} />
            <StatusBadge tone={oversight.source === "runtime-api" ? "good" : "danger"} label="source" value={oversight.source} />
          </div>
        )}
      />

      <div className="rtc-summary-grid rtc-summary-grid-wide">
        <article className="rtc-summary-card" data-tone={toneForStatus(oversight.status)}>
          <div className="rtc-summary-label">Oversight status</div>
          <div className="rtc-summary-value">{oversight.status}</div>
          <div className="rtc-summary-hint">Contained means no hidden guesswork path is currently detected.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.derivedFieldCount > 0 ? "warn" : "good"}>
          <div className="rtc-summary-label">Derived fields</div>
          <div className="rtc-summary-value">{oversight.derivedFieldCount}</div>
          <div className="rtc-summary-hint">Every derived value must stay individually labeled on-screen.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.unavailableFieldCount > 0 ? "warn" : "good"}>
          <div className="rtc-summary-label">Unavailable values</div>
          <div className="rtc-summary-value">{oversight.unavailableFieldCount}</div>
          <div className="rtc-summary-hint">Unavailable means the UI refused to back-fill missing runtime truth.</div>
        </article>
        <article className="rtc-summary-card" data-tone={oversight.linkedArtifactCount > 0 ? "good" : "warn"}>
          <div className="rtc-summary-label">Linked artifacts</div>
          <div className="rtc-summary-value">{oversight.linkedArtifactCount}</div>
          <div className="rtc-summary-hint">Artifact count backing the current cockpit surface.</div>
        </article>
      </div>

      <div className="rtc-grid rtc-grid-main rtc-grid-main-balanced">
        <GlassPanel compact className="rtc-nested-panel" interactive>
          <SectionHeader
            eyebrow="Ledger"
            title="Surface ledger"
            subtitle="Each screen gets its own evidence posture so Command Center, Brain, Shield, and Execution cannot hide behind one aggregate status."
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
                    <span>Direct evidence</span>
                    <strong>{surface.directEvidenceCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Derived fields</span>
                    <strong>{surface.derivedFieldCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Unavailable values</span>
                    <strong>{surface.unavailableFieldCount}</strong>
                  </div>
                  <div className="rtc-kv-row">
                    <span>Linked artifacts</span>
                    <strong>{surface.linkedArtifactCount}</strong>
                  </div>
                </div>
                <ul className="rtc-list rtc-tight-list">
                  {surface.notes.map((note) => (
                    <li key={`${surface.id}-${note}`}>{note}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel compact className="rtc-nested-panel" interactive>
          <SectionHeader
            eyebrow="Checks"
            title="Oversight checks"
            subtitle="These checks answer whether the UI truth path itself is behaving correctly: source explicitness, run lock integrity, endpoint consistency, replay alignment, and derivation discipline."
            compact
          />
          <div className="rtc-state-grid rtc-state-grid-tight">
            {oversight.rules.map((rule) => (
              <article className="rtc-state-card" key={rule.label}>
                <div className="rtc-live-card-header">
                  <strong>{rule.label}</strong>
                  <StatusBadge tone={toneForStatus(rule.status)} value={rule.status} subtle />
                </div>
                <div className="rtc-inline-note">{rule.detail}</div>
              </article>
            ))}
          </div>
          <ul className="rtc-list rtc-tight-list">
            {oversight.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </GlassPanel>
      </div>
    </GlassPanel>
  );
}
