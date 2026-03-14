# Cloud Deployment Guide (Variant A + Practical Variant 1)

This repository supports a two-node runtime split:

- **Live node**: execution-critical loop (watchdog, risk, execution, audit).
- **Compute node**: heavy scan/ranking/optimization/advisory workloads.

Shared services:

- Redis Streams for task/result coordination.
- Postgres mirror sink for distributed analytics snapshots.
- Consumer groups:
  - `compute_node` for task streams
  - `live_node` for result/audit streams

## 1. Prepare Environment Files

Use templates:

- `deploy/live-node.env.example`
- `deploy/compute-node.env.example`
- `deploy/universe-gateway.env.example`
- `deploy/realtime-worker.env.example`
- `deploy/simulation-worker.env.example`

Copy them to deployment-specific env files (for example `deploy/live-node.env`), then inject secrets via your cloud secret manager or runtime shell.

Do not store real API keys in git-tracked files.

## 2. Start Topologies

Live-only:

```bash
./scripts/start_live_node.sh
```

Compute-only:

```bash
./scripts/start_compute_node.sh
```

Full cluster:

```bash
./scripts/start_ultra_profit_cluster.sh
```

Universe Control Center (profiled compose):

```bash
# storage first
docker compose -f docker-compose.universe.yml --profile storage up -d

# runtime + api + realtime + monitoring
docker compose -f docker-compose.universe.yml \
  --profile runtime \
  --profile api \
  --profile realtime \
  --profile monitoring up -d
```

Distributed smoke checks:

```bash
./scripts/smoke_test_live_compute_roundtrip.sh
./scripts/smoke_test_distributed_cluster.sh
```

Run safety preflight before startup:

```bash
python3 scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper
```

## 3. Node Roles

- `AUTONOMOUS_NODE_ROLE=live` runs the trading runtime path.
- `AUTONOMOUS_NODE_ROLE=compute` runs the distributed compute worker.

`cli.run` auto-dispatches to compute worker when role is `compute`.

## 4. Runtime Safety

Hard invariants remain unchanged:

- never sell below entry/cost basis
- never sell below configured hard minimum net-profit floor
- no weakening of drawdown/exposure/fatal guards

Distributed compute is non-blocking by default (`AUTONOMOUS_COMPUTE_ALLOW_LOCAL_FALLBACK=1`).
If remote compute is unavailable, runtime can continue with local fallback under stricter gating.

Live startup is manually gated:

- `AUTONOMOUS_LIVE_GO=1`
- `AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE` must exist

Without manual gate, launchers default to paper-safe mode.

## 5. Validation Commands

```bash
docker compose -f docker-compose.live.yml config
docker compose -f docker-compose.compute.yml config
docker compose -f docker-compose.full.yml config
python3 scripts/validate_deployment_manifests.py
./scripts/validate_compose_runtime.sh
```

## 6. Operational Artifacts

Live node writes:

- `runs/<run_dir>/audit.log`
- `runs/<run_dir>/event_bus.jsonl`
- `runs/<run_dir>/harmony_report.json`
- `runs/<run_dir>/mastermind_status.json`
- `runs/<run_dir>/distributed_runtime_diagnostics.json`

Compute node writes:

- `runs/<run_dir>/compute_worker.log`
