import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ShieldScreen } from "@/components/shield-screen";
import { mockShield } from "@/lib/runtime/mock-data";
import { buildUnavailableShield } from "@/lib/runtime/unavailable-data";
import type { ControlsContract } from "@/types/contracts";

const controls: ControlsContract = {
  statusLine: "operator session active",
  provenanceLine: "ops.mh / local",
  canWriteIncidentNotes: true,
  actions: [
    { action: "pause", label: "Pause entries", enabled: true, tone: "warn" },
    { action: "freeze", label: "Freeze", enabled: true, tone: "danger" },
  ],
  lastResponse: null,
};

describe("ShieldScreen", () => {
  it("renders trust verdict and guard matrix from live safety payload", () => {
    const html = renderToStaticMarkup(
      React.createElement(ShieldScreen, {
        shield: mockShield,
        controls,
        actionReason: "manual_review",
        onActionReasonChange: () => {},
        onInvokeControl: () => {},
        pendingAction: null,
        lastResponse: null,
      }),
    );

    expect(html).toContain("Runtime trust and safety surface");
    expect(html).toContain("caution");
    expect(html).toContain("Max exposure");
    expect(html).toContain("Spread guard");
    expect(html).toContain("Control Safety Panel");
    expect(html).toContain("Applied control");
    expect(html).toContain("force_degraded via meta_governor");
    expect(html).toContain("User stream");
  });

  it("renders unsafe degraded state honestly when shield payload is unavailable", () => {
    const html = renderToStaticMarkup(
      React.createElement(ShieldScreen, {
        shield: buildUnavailableShield("shield_payload_missing"),
        controls,
        actionReason: "manual_review",
        onActionReasonChange: () => {},
        onInvokeControl: () => {},
        pendingAction: null,
        lastResponse: null,
      }),
    );

    expect(html).toContain("unsafe");
    expect(html).toContain("runtime_api_unavailable");
    expect(html).toContain("shield_payload_missing");
    expect(html).toContain("no linked artifacts");
  });
});
