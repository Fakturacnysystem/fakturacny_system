# Cloud Deployment Guide (Variant A + Practical Variant 1)

This repository supports a two-node runtime split:

- **Live node**: execution-critical loop (watchdog, risk, execution, audit).
- **Compute node**: heavy scan/ranking/optimization/advisory workloads.

Shared services:

- Redis Streams for task/result coordination.
- Postgres mirror sink for distributed analytics snapshots.

## 1. Prepare Environment Files

Use templates:

- `deploy/live-node.env.example`
- `deploy/compute-node.env.example`

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

## 5. Validation Commands

```bash
docker compose -f docker-compose.live.yml config
docker compose -f docker-compose.compute.yml config
docker compose -f docker-compose.full.yml config
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
