import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ExecutionScreen } from "@/components/execution-screen";
import { mockExecution } from "@/lib/runtime/mock-data";
import { buildUnavailableExecution } from "@/lib/runtime/unavailable-data";

describe("ExecutionScreen", () => {
  it("renders order and position observability from full payload", () => {
    const html = renderToStaticMarkup(
      React.createElement(ExecutionScreen, { execution: mockExecution }),
    );

    expect(html).toContain("Čo sa naozaj stalo pri pokynoch a obchodoch");
    expect(html).toContain("partially filled");
    expect(html).toContain("BTC/EUR");
    expect(html).toContain("Skutočný stav účtu");
    expect(html).toContain("Pravda o burze a priebehu");
    expect(html).toContain("openOrders");
    expect(html).toContain("Časový priebeh obchodov");
    expect(html).toContain("events_orders.jsonl");
  });

  it("renders missing execution telemetry honestly", () => {
    const html = renderToStaticMarkup(
      React.createElement(ExecutionScreen, { execution: buildUnavailableExecution("execution_payload_missing") }),
    );

    expect(html).toContain("execution_payload_missing");
    expect(html).toContain("Zatiaľ nie je k dispozícii priebeh pokynov.");
    expect(html).toContain("Z tohto behu zatiaľ nie sú pozorovateľné žiadne otvorené pozície.");
    expect(html).toContain("Nie je k dispozícii pokyn, na ktorom by sa dal ukázať detailný priebeh.");
  });
});
