# Distributed Acceptance Checklist

Use this checklist before claiming distributed/cloud readiness.

## 1. Static and test validation

- `python3 -m py_compile src/autonomous_investment_robot/services/distributed/*.py src/autonomous_investment_robot/core/orchestrator.py cli/compute_node.py cli/run.py`
- `pytest -q tests/test_distributed_services.py tests/test_distributed_e2e.py tests/test_postgres_mirror.py tests/test_parallel_symbol_processing.py`
- `pytest -q`
- `python3 scripts/validate_deployment_manifests.py`
- rollout-claim gate:
  - `python3 scripts/validate_deployment_manifests.py --runtime-evidence-run-dir runs/<run_dir> --require-runtime-evidence`
  - if docker is unavailable on host, classify as `blocked` (not `pass`) and do not claim distributed readiness
- `python3 scripts/audit_config_matrix.py --json-output /tmp/config_matrix_audit.json --md-output /tmp/config_matrix_audit.md`

## 2. Compose/runtime checks

- `./scripts/validate_compose_runtime.sh`
  - exit `0` = compose syntax validated
  - exit `2` = blocked by host infrastructure (docker missing)

## 3. Distributed runtime evidence

Required evidence in run artifacts:

- `runs/<run_dir>/distributed_runtime_diagnostics.json`
  - `compute_bridge.backend` should be `redis_streams` for distributed proof
  - `postgres_mirror.enabled` should be `true` for mirror proof
- `runs/<run_dir>/audit.log` should contain `distributed_compute_rankings`
- `runs/<run_dir>/event_bus.jsonl` should contain execution and decision topics
- `runs/<run_dir>/llm_self_improvement_diagnostics.json` should confirm advisory status (enabled/disabled reason)

## 4. End-to-end smoke

- `./scripts/smoke_test_live_compute_roundtrip.sh` (deterministic in-repo E2E via fake redis contract)
- `./scripts/smoke_test_distributed_cluster.sh` (docker-backed cluster smoke; may be blocked if docker unavailable)

## 5. Non-negotiable runtime checks

- Hard invariant counters remain zero:
  - `profit_lock_sell_below_entry`
  - `profit_lock_sell_below_min_profit`
- `sell_min_profit_bps >= 120` in harmony report
- if live mode used, manual live gate remains required and must be explicitly armed
