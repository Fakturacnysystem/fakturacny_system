# Redis and Postgres Validation Guide

This guide separates three levels of proof:

- **Code-level support**: classes, contracts, and tests exist.
- **Host-level support**: compose/runtime checks pass on the current machine.
- **Runtime-level support**: live artifacts prove redis/postgres paths are active.

## Redis Streams backbone

### Code-level checks

- `src/autonomous_investment_robot/services/distributed/contracts.py`
- `src/autonomous_investment_robot/services/distributed/compute_bridge.py`
- `src/autonomous_investment_robot/services/distributed/compute_worker.py`

### Test-level checks

- `pytest -q tests/test_distributed_services.py tests/test_distributed_e2e.py`

### Runtime-level proof

Inspect `runs/<run_dir>/distributed_runtime_diagnostics.json`:

- `compute_bridge.backend == "redis_streams"` (proof)
- `compute_bridge.backend == "local"` (fallback mode, not full distributed proof)

Inspect `runs/<run_dir>/audit.log`:

- events for `distributed_compute_rankings` with `source=redis_streams`

## Postgres mirror strategy

### Code-level checks

- `src/autonomous_investment_robot/services/distributed/postgres_mirror.py`

### Test-level checks

- `pytest -q tests/test_postgres_mirror.py`

### Runtime-level proof

Inspect `runs/<run_dir>/distributed_runtime_diagnostics.json`:

- `postgres_mirror.enabled == true`
- `postgres_mirror.ok == true`

If disabled or no DSN, mirror is scaffolded/optional in that run, not runtime-proven.

## Host limitations

If docker is missing:

- compose runtime checks are blocked by infrastructure
- classify docker-backed deployment proof as blocked (not failed, not passed)

## Rollout-claim gate (Phase 21)

For distributed rollout claims (not static scaffold validation), run:

- `python3 scripts/validate_deployment_manifests.py --runtime-evidence-run-dir runs/<run_dir> --require-runtime-evidence`

Expected behavior:

- `rollout_claim_ready == true` only when runtime evidence bundle checks pass.
- missing runtime evidence is classified `blocked`, never `pass`.
- host docker unavailability is classified as `blocked` for host-level proof paths.
