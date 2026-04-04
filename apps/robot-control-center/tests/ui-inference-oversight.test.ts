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
      label: "Command Center",
      status: "contained",
      directEvidenceCount: 12,
      derivedFieldCount: 0,
      unavailableFieldCount: 0,
      linkedArtifactCount: 0,
      notes: ["Command Center is bound to runtime summary and telemetry payloads."],
    },
    {
      id: "brain",
      label: "Brain",
      status: "watch",
      directEvidenceCount: 18,
      derivedFieldCount: 3,
      unavailableFieldCount: 4,
      linkedArtifactCount: 6,
      notes: ["Derived next-eligible hints are tagged explicitly."],
    },
  ],
  rules: [
    {
      label: "Runtime source explicit",
      status: "pass",
      detail: "UI is bound to runtime API data.",
    },
    {
      label: "Derived fields disclosed",
      status: "pass",
      detail: "6 derived fields are explicitly tagged across the cockpit.",
    },
  ],
  notes: [
    "Runtime API is the active truth path for the cockpit.",
    "Unavailable values remain explicit so the UI never fabricates hidden confidence.",
  ],
};

describe("UiInferenceOversight", () => {
  it("renders a persistent oversight ledger for direct, derived, and unavailable UI data", () => {
    const html = renderToStaticMarkup(
      React.createElement(UiInferenceOversight, { oversight }),
    );

    expect(html).toContain("UI inference oversight");
    expect(html).toContain("Derived fields");
    expect(html).toContain("Unavailable values");
    expect(html).toContain("Command Center");
    expect(html).toContain("Brain");
    expect(html).toContain("Oversight checks");
    expect(html).toContain("6 derived fields are explicitly tagged across the cockpit.");
  });
});
