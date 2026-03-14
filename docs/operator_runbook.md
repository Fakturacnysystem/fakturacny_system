# Operator Runbook (Cloud/Distributed)

## Core startup paths

- Live node: `./scripts/start_live_node.sh`
- Compute node: `./scripts/start_compute_node.sh`
- Full cluster: `./scripts/start_ultra_profit_cluster.sh`

## Safety gate

Live mode remains manually gated:

- `AUTONOMOUS_LIVE_GO=1`
- confirmation artifact exists at `AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE`
- typed operator approval artifact exists at `AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE`

If gate is not satisfied, launcher falls back to paper-safe path.

## Universe Core shadow adapter (Phase 11)

Optional additive observability bridge in orchestrator runtime:

- `AUTONOMOUS_UNIVERSE_SHADOW_ENABLED=1` enables per-cycle shadow `UniverseMind` packet emission.
- `AUTONOMOUS_UNIVERSE_SHADOW_FAIL_OPEN=1` keeps adapter fail-open (recommended for live safety).
- `AUTONOMOUS_UNIVERSE_SHADOW_EVERY_N_STEPS=<N>` controls emission cadence (default `1`).

Shadow artifacts are written under `run_dir/universe_shadow/*` and do not change order-placement authority.

## Universe Core legacy event adapter (Phase 12)

Optional additive canonical-envelope mirror for selected legacy producer events:

- `AUTONOMOUS_UNIVERSE_EVENT_ADAPTER_ENABLED=1` enables legacy-to-canonical mirror (default on).
- `AUTONOMOUS_UNIVERSE_EVENT_ADAPTER_FAIL_OPEN=1` keeps mirror fail-open (recommended).

When enabled, legacy `EventStore` writes are preserved and additionally mirrored to canonical Universe events under `run_dir/universe_events/*`.
This adapter does not change order authority, hard safety doctrine, or manual live gate behavior.

## Validation before startup

- `./.venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper --output runs/<run_dir>/rollback_preflight.json`
- `./.venv/bin/python scripts/validate_deployment_manifests.py`
- `./.venv/bin/python scripts/runtime_audit.py --runs-root runs --event-limit 3000 --output runs/<run_dir>/rollback_runtime_audit.json`
- `./scripts/validate_compose_runtime.sh`

## Distributed smoke checks

- `./scripts/smoke_test_live_compute_roundtrip.sh`
- `./scripts/smoke_test_distributed_cluster.sh` (docker required)

## Post-start audit

- `./.venv/bin/python scripts/runtime_audit.py --run-dir runs/kraken_ultra_profit_full_throttle --event-limit 3000 --output runs/kraken_ultra_profit_full_throttle/rollback_runtime_audit.json`
- Verify:
  - hard invariants remain zero
  - `sell_min_profit_bps >= 120`
  - execution topics present
  - blocker categories are expected and explainable
  - `rollback_dry_run.validated == true`
