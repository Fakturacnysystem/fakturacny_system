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

    expect(html).toContain("Order, position, and venue observability");
    expect(html).toContain("partially filled");
    expect(html).toContain("BTC/EUR");
    expect(html).toContain("Account Truth");
    expect(html).toContain("Venue / Lifecycle Truth");
    expect(html).toContain("openOrders");
    expect(html).toContain("Execution Timeline");
    expect(html).toContain("events_orders.jsonl");
  });

  it("renders missing execution telemetry honestly", () => {
    const html = renderToStaticMarkup(
      React.createElement(ExecutionScreen, { execution: buildUnavailableExecution("execution_payload_missing") }),
    );

    expect(html).toContain("execution_payload_missing");
    expect(html).toContain("No execution order lifecycle payload is available.");
    expect(html).toContain("No open positions are observable from the active run.");
    expect(html).toContain("No order is available to anchor a focused execution timeline.");
  });
});
