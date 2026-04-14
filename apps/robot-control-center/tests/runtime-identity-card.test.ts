import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RuntimeIdentityCard } from "@/components/runtime-identity-card";
import type { RuntimeIdentityContract } from "@/types/contracts";
import type { RuntimeRunCatalog } from "@/types/runtime";

const baseIdentity: RuntimeIdentityContract = {
  runId: "kraken_spot_live_profit09",
  selectionMode: "pinned",
  resolutionSource: "explicit_run_id",
  runPath: "/runs/kraken_spot_live_profit09",
  providerId: "kraken_spot",
  mode: "live",
  stateKind: "healthy",
  reasonCode: "ok",
  driftStatus: "locked",
  pinIntegrityStatus: "ok",
  freshnessStatus: "fresh",
  freshnessAgeLabel: "12s",
  lastArtifactUpdateAt: "2026-03-31T15:20:23.048455+00:00",
  schemaVersion: "2",
  endpointConsistencyStatus: "consistent",
  replayAlignmentStatus: "aligned",
  issues: [],
};

const runCatalog: RuntimeRunCatalog = {
  items: [
    {
      runId: "kraken_spot_live_profit09",
      runPath: "/runs/kraken_spot_live_profit09",
      providerId: "kraken_spot",
      mode: "live",
      stateKind: "healthy",
      reasonCode: "ok",
      startedAt: "2026-03-31T14:20:23.048455+00:00",
      lastArtifactUpdateAt: "2026-03-31T15:20:23.048455+00:00",
      artifactFreshnessStatus: "fresh",
      equity: 12.4,
      current: true,
      latest: true,
    },
  ],
  selectionMode: "pinned",
  selectionTarget: "runs/kraken_spot_live_profit09",
  resolvedRunId: "kraken_spot_live_profit09",
  resolvedRunPath: "/runs/kraken_spot_live_profit09",
  latestRunId: "kraken_spot_live_profit09",
  latestRunPath: "/runs/kraken_spot_live_profit09",
  unresolvedSelection: false,
  runtimeIdentity: undefined,
  lastUpdatedAt: "2026-03-31T15:20:23.048455+00:00",
};

describe("RuntimeIdentityCard", () => {
  it("renders unresolved pinned run state explicitly", () => {
    const html = renderToStaticMarkup(
      React.createElement(RuntimeIdentityCard, {
        identity: {
          ...baseIdentity,
          pinIntegrityStatus: "unresolved",
          driftStatus: "unresolved",
          reasonCode: "run_not_found",
          runPath: "",
          issues: ["pin_integrity:unresolved", "runtime_drift:unresolved"],
        },
      }),
    );

    expect(html).toContain("Pripnutý beh sa nepodarilo spoľahlivo nájsť alebo neprešiel kontrolou");
    expect(html).toContain("run_not_found");
    expect(html).toContain("unresolved");
  });

  it("renders endpoint and replay mismatch loudly", () => {
    const html = renderToStaticMarkup(
      React.createElement(RuntimeIdentityCard, {
        identity: {
          ...baseIdentity,
          endpointConsistencyStatus: "mismatch",
          replayAlignmentStatus: "mismatch",
          issues: ["runtime_identity_mismatch:replay", "replay_run_mismatch:another-run"],
        },
      }),
    );

    expect(html).toContain("Niektoré časti aplikácie ukazujú iný beh alebo inú históriu");
    expect(html).toContain("runtime_identity_mismatch:replay");
    expect(html).toContain("replay_run_mismatch:another-run");
  });

  it("renders exact pin command when tracking latest", () => {
    const html = renderToStaticMarkup(
      React.createElement(RuntimeIdentityCard, {
        identity: {
          ...baseIdentity,
          selectionMode: "latest",
          driftStatus: "tracking_latest",
          pinIntegrityStatus: "not_pinned",
          issues: ["runtime_tracking_latest"],
        },
        pinCommand: "RUNTIME_API_RUN_ID=kraken_spot_live_profit09 npm run runtime:api",
      }),
    );

    expect(html).toContain("runtime_tracking_latest");
    expect(html).toContain("RUNTIME_API_RUN_ID=kraken_spot_live_profit09 npm run runtime:api");
  });

  it("renders run selector with explicit available runs", () => {
    const html = renderToStaticMarkup(
      React.createElement(RuntimeIdentityCard, {
        identity: baseIdentity,
        runs: runCatalog,
      }),
    );

    expect(html).toContain("Vyber sledovaný beh");
    expect(html).toContain("Pripnúť vybraný beh");
    expect(html).toContain("Sledovať najnovší");
    expect(html).toContain("kraken_spot_live_profit09 · live · healthy");
  });
});
