import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ShieldScreen } from "@/components/shield-screen";
import { mockShield } from "@/lib/runtime/mock-data";
import { buildUnavailableShield } from "@/lib/runtime/unavailable-data";
import type { ControlsContract } from "@/types/contracts";

const controls: ControlsContract = {
  statusLine: "operátor je prihlásený",
  provenanceLine: "ops.mh / local",
  canWriteIncidentNotes: true,
  actions: [
    { action: "pause", label: "Pozastaviť", enabled: true, tone: "warn" },
    { action: "freeze", label: "Zmraziť", enabled: true, tone: "danger" },
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

    expect(html).toContain("Dá sa tomuto robotovi práve teraz veriť?");
    expect(html).toContain("caution");
    expect(html).toContain("Max exposure");
    expect(html).toContain("Spread guard");
    expect(html).toContain("Bezpečné ovládanie");
    expect(html).toContain("Čo momentálne platí");
    expect(html).toContain("force_degraded cez meta_governor");
    expect(html).toContain("Používateľský stream");
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
    expect(html).toContain("bez napojených dôkazov");
  });
});
