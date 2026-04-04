import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BrainScreen } from "@/components/brain-screen";
import { mockBrain } from "@/lib/runtime/mock-data";
import { buildUnavailableBrain } from "@/lib/runtime/unavailable-data";

describe("BrainScreen", () => {
  it("renders evidence-driven decision state from complete payload", () => {
    const html = renderToStaticMarkup(
      React.createElement(BrainScreen, { brain: mockBrain }),
    );

    expect(html).toContain("Decision evidence graph");
    expect(html).toContain("BTC/EUR");
    expect(html).toContain("trade_smaller");
    expect(html).toContain("Decision Pipeline Map");
    expect(html).toContain("nextEligibleAction derived from decision intent plus live ordering gate");
  });

  it("renders unavailable and empty states honestly", () => {
    const html = renderToStaticMarkup(
      React.createElement(BrainScreen, { brain: buildUnavailableBrain("brain_payload_missing") }),
    );

    expect(html).toContain("brain_payload_missing");
    expect(html).toContain("No decision pipeline evidence is available for the active run.");
    expect(html).toContain("No symbol brain payload is available.");
    expect(html).toContain("unavailable");
  });
});
