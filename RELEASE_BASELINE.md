# Release Baseline

## Supported stages

| Stage | Runtime mode / config truth | Supported purpose | Required artifact bundle |
|---|---|---|---|
| `readonly` | `execution.mode=live_readonly`, `rollout_stage=shadow` | live data + full analytics without orders | operator summary, harmony reports, live safety summary, replay summary, performance architecture bundle |
| `shadow` | readonly runtime plus decision comparison / additive shadow artifacts | compare additive systems without routing authority | readonly bundle plus pair/playbook/opportunity/expectancy/experiment artifacts |
| `tiny_live` | `execution.mode=live`, `rollout_stage=tiny_live` | bounded first-money evidence collection | readonly bundle plus live lifecycle, reconciliation, fill/account truth, tiny-live readiness, envelope, promotion evidence |
| `limited_live` | `execution.mode=live`, `rollout_stage=limited_live` | conservative post-tiny live with existing authoritative path | tiny-live bundle plus stable live account/fill/reconciliation truth |
| `normal_live` | `execution.mode=live`, full stage unlock required | full doctrine-safe live envelope on the existing authoritative path | limited-live bundle plus full-stage unlock evidence |

## Required validation commands

```bash
./scripts/bootstrap_validation_env.sh
python3 scripts/validate_config_matrix.py
python3 -m compileall src scripts tests
./.venv/bin/python -m pytest -q \
  tests/test_config_truthfulness.py \
  tests/test_launch_path_safety.py \
  tests/test_live_coordination.py \
  tests/test_live_kraken_spot_service.py \
  tests/test_orchestrator_observability.py \
  tests/test_runtime_api_service.py \
  tests/test_runtime_api_screens.py
./scripts/run_kraken_spot_readonly_analysis.sh
./scripts/run_kraken_spot_shadow_multi_pair.sh
```

Run `npm run typecheck` under [`apps/robot-control-center`](/Users/martinholik/Projects/fakturacny_system/apps/robot-control-center) when RCC contract or runtime mapping changes.

## Non-negotiable safety invariants

- Kraken SPOT only, long-only only.
- Double live unlock remains mandatory.
- `ENABLE_FULL_LIVE_STAGE=true` remains mandatory for full-stage normal live.
- Hard SELL fences remain intact:
  - no sell below cost basis
  - no sell below modeled net profit floor
  - profit floor never below `120 bps`
- Invalid auth, symbol mapping, exchange constraints, NaN/<=0 bid/ask, idempotency failure, persistent rate-limit storm, truth gaps, and lifecycle ambiguity remain fail-closed conditions.

## Not live-authoritative yet

- Multi-pair ranking
- Playbook framework
- Opportunity auction
- Allocator sizing
- Expectancy-driven promotion
- Adaptive cadence
- Entry timing optimizer
- Self-throttling
- Exit-intelligence cleanup families

Those systems may emit telemetry in live runs. They do not currently own live order-routing.

## What production-complete means here

For this repository, `production-complete` means:

- authoritative live routing remains bounded, explicit, and reversible
- readonly/shadow/tiny_live evidence collection is complete enough for disciplined review
- runtime metadata, runtime API, and RCC stay coherent under missing or partial artifacts
- operator docs, rollout docs, and machine-readable promotion evidence agree with code

It does not mean:

- autonomous promotion exists
- additive performance subsystems are already routing live orders
- target returns are proven
