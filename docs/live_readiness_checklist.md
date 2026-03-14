# Live Readiness Checklist

Use this checklist before declaring live readiness.

## Configuration and guards

- Harmony resolves with no invariant failures:
  - `./.venv/bin/python scripts/audit_config_matrix.py --json-output /tmp/config_matrix_audit.json --md-output /tmp/config_matrix_audit.md`
- config freeze contract has zero drift failures (`drift_failures == 0`) and each config row has deterministic `resolved_config_fingerprint`
- `sell_min_profit_bps >= 120` in effective harmony output
- guards mode and drawdown/exposure constraints remain enabled

## Runtime integrity

- `pytest -q` passes
- `./.venv/bin/python -m py_compile` on changed critical modules passes
- `./.venv/bin/python scripts/runtime_audit.py --runs-root runs --event-limit 3000` executes successfully
- promotion-governance review includes replay determinism evidence (`replay_contract_id`, `replay_determinism_gate_passed`) when promotion stage changes are proposed

## Rollback Dry-Run Evidence

- `./.venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper --output runs/<run_dir>/rollback_preflight.json`
- `./.venv/bin/python scripts/runtime_audit.py --run-dir runs/<run_dir> --event-limit 3000 --output runs/<run_dir>/rollback_runtime_audit.json`
- verify both artifacts include `rollback_dry_run.validated == true` before claiming rollback readiness

## Manual Live Dual-Control

- `AUTONOMOUS_LIVE_GO=1`
- confirmation file at `AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE` exists
- typed approval artifact file at `AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE` exists and includes an approved operator payload

## Distributed/cloud integrity

- `./scripts/validate_compose_runtime.sh` returns 0, or classify as blocked by host infra if docker unavailable
- `./scripts/smoke_test_live_compute_roundtrip.sh` passes
- `./scripts/smoke_test_distributed_cluster.sh` passes when docker is available

## Trading safety

- no `profit_lock_sell_below_entry` events
- no `profit_lock_sell_below_min_profit` events
- no fatal invariant breaches in runtime artifacts
