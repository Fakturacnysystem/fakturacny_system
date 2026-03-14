# Runtime Topology and Service Boundaries

## Live Node Boundaries

Live node keeps only execution-critical responsibilities:

- market ingestion (lightweight)
- central decision finalize
- risk enforcement and guardrails
- order submission and execution reconciliation
- watchdog + harmony + mastermind + runtime audit

Live node does **not** block on long compute tasks or LLM calls.

## Compute Node Boundaries

Compute node runs asynchronous heavy workloads:

- market scan/ranking
- probabilistic ranking expansion
- xStocks-heavy universe scoring
- bounded optimization/advisory proposals

Compute node never submits live orders directly.

## Shared State and Event Paths

### Redis Streams

Live node publishes compute tasks to:

- `autobot.tasks.scan`
- `autobot.tasks.forecast`
- `autobot.tasks.optimize`

Compute node publishes results to:

- `autobot.results.rankings`
- `autobot.results.signals`

Both nodes can emit audit envelope events to:

- `autobot.events.audit`

Consumer groups:

- `compute_node` consumes task streams.
- `live_node` consumes result/audit streams.

### Cross-Asset Class Normalization (Phase 20)

- Live and local-compute ranking now normalize market-class aliases to canonical classes before scoring:
  - `crypto_spot`, `crypto_perp`, `futures`, `xstock`, `xstock_etf`, `xstock_perp`, `xstock_etf_perp`, `fx`.
- Universe Core cross-asset allocator applies deterministic class-aware scoring and class caps on canonical classes.
- This normalization is additive and does not bypass existing risk/exposure gates in orchestrator/risk-engine paths.

### Postgres Mirror Sink

Live node mirrors runtime snapshots:

- decision snapshots
- execution summaries
- module events / violations

Mirror failures are non-fatal and do not halt live loop.

## Prepared Variant 2 Service Extraction

Current code now has extraction-ready boundaries for:

- scanner service
- forecast/ranking service
- optimizer/advisory service
- execution service
- audit/mirror service

These boundaries are contract-first and compatible with later process/container extraction.

## Runtime Truth Criteria

Presence of files or classes alone is insufficient. For distributed runtime proof, verify:

- `runs/<run_dir>/distributed_runtime_diagnostics.json`
  - `compute_bridge.backend == "redis_streams"`
  - `postgres_mirror.enabled == true`
- `runs/<run_dir>/audit.log` includes `distributed_compute_rankings`
- `runs/<run_dir>/event_bus.jsonl` includes execution/decision topics

If these are missing, classify the setup as partial/scaffolded even when docs and tests are present.
