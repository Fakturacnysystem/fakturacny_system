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

Compute node publishes results to:

- `autobot.results.rankings`

Both nodes can emit audit envelope events to:

- `autobot.events.audit`

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
