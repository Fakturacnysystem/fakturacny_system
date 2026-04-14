import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { UiInferenceOversight } from "@/components/ui-inference-oversight";
import type { UiInferenceContract } from "@/types/contracts";

const oversight: UiInferenceContract = {
  status: "watch",
  source: "runtime-api",
  derivedFieldCount: 6,
  unavailableFieldCount: 9,
  linkedArtifactCount: 14,
  surfaces: [
    {
      id: "command",
      label: "Hlavný panel",
      status: "contained",
      directEvidenceCount: 12,
      derivedFieldCount: 0,
      unavailableFieldCount: 0,
      linkedArtifactCount: 0,
      notes: ["Hlavný panel je naviazaný na runtime summary a telemetrické payloady."],
    },
    {
      id: "brain",
      label: "Rozhodovanie",
      status: "watch",
      directEvidenceCount: 18,
      derivedFieldCount: 3,
      unavailableFieldCount: 4,
      linkedArtifactCount: 6,
      notes: ["Odvodené rady pre ďalší krok sú výslovne označené."],
    },
  ],
  rules: [
    {
      label: "Zdroj dát je jasný",
      status: "pass",
      detail: "UI je naviazané na údaje z runtime API.",
    },
    {
      label: "Odvodené polia sú priznané",
      status: "pass",
      detail: "V paneli je výslovne označených 6 odvodených polí.",
    },
  ],
  notes: [
    "Runtime API je aktívna cesta pravdy pre celý panel.",
    "Chýbajúce hodnoty ostávajú priznané, takže UI si nevymýšľa skrytú istotu.",
  ],
};

describe("UiInferenceOversight", () => {
  it("renders a persistent oversight ledger for direct, derived, and unavailable UI data", () => {
    const html = renderToStaticMarkup(
      React.createElement(UiInferenceOversight, { oversight }),
    );

    expect(html).toContain("Dohľad nad tým, čo si UI iba odvodilo");
    expect(html).toContain("Odvodené polia");
    expect(html).toContain("Chýbajúce hodnoty");
    expect(html).toContain("Hlavný panel");
    expect(html).toContain("Rozhodovanie");
    expect(html).toContain("Kontroly pravdivosti");
    expect(html).toContain("V paneli je výslovne označených 6 odvodených polí.");
  });
});
