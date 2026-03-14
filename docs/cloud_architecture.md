# Cloud Architecture (Variant A + Practical Variant 1)

## Goals

- Move 24/7 execution away from operator Mac.
- Keep live execution responsive under heavy analytics load.
- Use shared Redis/Postgres for distributed coordination and observability.

## Runtime Topology

- **Mac (operator console only)**:
  - monitoring, logs, Codex/dev workflow
  - not required for continuous live runtime
- **Live Node (VPS)**:
  - watchdog + live execution loop
  - risk/guardrails, order routing, runtime audit
  - reads compute outputs with strict timeout and safe fallback
- **Compute Node**:
  - heavy scan/ranking tasks
  - optional advisory/optimization analysis
  - publishes ranked candidates back to live node
- **Shared Infra**:
  - Redis Streams: task/result exchange
  - Postgres mirror sink: decision/execution/audit snapshots

## Stream Contract

Default stream prefix: `autobot`

- tasks:
  - `autobot.tasks.scan`
  - `autobot.tasks.forecast`
  - `autobot.tasks.optimize`
- results:
  - `autobot.results.signals`
  - `autobot.results.rankings`
- audit:
  - `autobot.events.audit`

Consumer groups:

- `live_node` (live runtime consumers)
- `compute_node` (compute workers)

Envelope fields:

- `task_id`
- `run_id`
- `symbol`
- `market_class`
- `ts`
- `ttl_s`
- `payload_version`
- `idempotency_key`
- `payload`

## Safety Model

Hard invariants remain unchanged:

- never submit sell below entry/cost basis
- never submit sell below configured hard net-profit floor
- no weakening of fatal/drawdown/exposure/profit-lock guards

Distributed compute is optional at runtime:

- if remote compute is unavailable, live node can use local fallback (configurable)
- fallback never bypasses risk gates or execution guardrails
- live mode is manually gated (operator confirmation artifact + `AUTONOMOUS_LIVE_GO=1`)
- default launcher behavior is paper-safe when manual live gate is not satisfied

## Deployment Artifacts

- `docker-compose.live.yml`
- `docker-compose.compute.yml`
- `docker-compose.full.yml`
- `deploy/live-node.env.example`
- `deploy/compute-node.env.example`
- `scripts/start_live_node.sh`
- `scripts/start_compute_node.sh`
- `scripts/start_ultra_profit_cluster.sh`
- `scripts/validate_deployment_manifests.py`

## Verification Boundaries

Distributed/cloud readiness must be proven in three layers:

- **code/test proof**: contracts and tests pass
- **host proof**: docker/compose validation succeeds on the current machine
- **runtime proof**: run artifacts show `compute_bridge.backend=redis_streams` and postgres mirror enabled/healthy

If runtime diagnostics show `backend=local`, the system is in safe fallback mode, not fully proven distributed mode.
