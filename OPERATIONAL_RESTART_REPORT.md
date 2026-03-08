# Operational Restart Report

Date: 2026-03-08
Repository: `/Users/martinholik/Projects/fakturacny_system`

## Scope
Hard stop, clean state, deep validation, clean restart, recurring deep health check (10 minutes), post-start runtime audit.

## Startup/Process Map (discovered)
- Main live entry script: `scripts/run_kraken_spot_profit_full_throttle.sh`
- Core runtime process: `python -m cli.run --config config.kraken_spot.live_profit.yaml --nonstop`
- Orchestrator/runtime services via `src/autonomous_investment_robot/core/orchestrator.py`
- Harmony resolver: `src/autonomous_investment_robot/services/ops/harmony.py`
- Mastermind supervisor artifacts: `runs/<run_dir>/mastermind_status.json`
- Runtime audit tooling: `scripts/runtime_audit.py`
- Deep health check tooling (added): `scripts/deep_system_health_check.py`
- Recurring scheduler mechanism: macOS `launchd` agent (`codex.autonomous.deephealth`)

## Stop/Cleanup Performed
- Stopped respawn source job `codex.kraken.live` via `launchctl bootout` (to prevent zombie/auto-respawn during hard stop).
- Terminated robot runtime processes for clean restart.
- Archived stale runtime debris (non-business-critical temp artifacts) under:
  - `runs/_stale_archive/20260308_094354/`
  - `runs/_stale_archive/20260308_094400/`
- Archived stale cache artifacts (`__pycache__`, `.pytest_cache`) rather than destructive deletion.
- Preserved persistent runtime/business artifacts (`trading.db`, governance/event logs, ledgers).

## Repairs/Implementations
- Added deep deterministic health checker:
  - `scripts/deep_system_health_check.py`
  - Validates process health, Harmony presence, Mastermind presence, stale runtime markers, reject-rate, profit-lock violations.
  - Writes:
    - `runs/<run_dir>/deep_health_check.json`
    - `runs/<run_dir>/deep_health_check.log`
- Added launchd installer for recurring checks:
  - `scripts/install_deep_healthcheck_launchd.sh`
  - Installs 600-second recurring health check with run-at-load.

## Validation Executed
1. Compile check:
- `python3 -m py_compile scripts/deep_system_health_check.py scripts/runtime_audit.py`
- Result: PASS

2. Full tests:
- `.venv/bin/pytest -q`
- Result: `270 passed, 1 skipped`

3. Harmony/config validation:
- `bash scripts/verify_harmony.sh`
- Result: PASS

4. Config matrix dry-run:
- `.venv/bin/python scripts/audit_config_matrix.py --json-output docs/config_matrix.json --md-output docs/config_matrix.md`
- Result: PASS (`configs=13`, `errors=0`)

5. Post-start runtime audit (3000 events):
- `.venv/bin/python scripts/runtime_audit.py --run-dir runs/kraken_spot_live_profit09 --event-limit 3000 --output runs/kraken_spot_live_profit09/runtime_audit_3000.json`
- Result: PASS (script exit code 0), system verdict `BLOCKED`

## Clean Restart Result
- Restart command path used: `./scripts/run_kraken_spot_profit_full_throttle.sh`
- Active runtime process observed:
  - `python -m cli.run --config config.kraken_spot.live_profit.yaml --nonstop`
- Active run directory:
  - `runs/kraken_spot_live_profit09`
- Runtime health artifact:
  - `runs/kraken_spot_live_profit09/health.json` => `status=running`

## Harmony/Mastermind Verification
- Harmony active (`runs/kraken_spot_live_profit09/harmony_report.json`):
  - `guards_mode = fatal_only`
  - `order_cadence_s = 3.0`
  - `effective_min_order_quote = 2.0`
  - `sell_min_profit_bps = 120.0`
  - `sell_target_profit_bps = 200.0`
- Mastermind active (`runs/kraken_spot_live_profit09/mastermind_status.json`): present + populated

## Recurring Deep Health Check Installation (10 minutes)
- Launchd label: `codex.autonomous.deephealth`
- Plist: `/Users/martinholik/Library/LaunchAgents/codex.autonomous.deephealth.plist`
- Interval: `600` seconds
- Output artifacts:
  - `runs/kraken_spot_live_profit09/deep_health_launchd.out`
  - `runs/kraken_spot_live_profit09/deep_health_launchd.err`
  - `runs/kraken_spot_live_profit09/deep_health_check.json`
  - `runs/kraken_spot_live_profit09/deep_health_check.log`
- Latest deep-check result: `ok`

## Post-Start Audit Evidence (last 3000 events)
Source: `runs/kraken_spot_live_profit09/runtime_audit_3000.json`

- `SYSTEM_STATE = BLOCKED`
- Order stats:
  - `submitted_orders=0`
  - `blocked_orders=12`
  - `rejected_orders=0`
  - `killed_orders=0`
  - `sell_submitted=0`
  - `buy_submitted=0`
- Top blocker categories:
  - `no_intent`: 33 (symbol: `ADAUSD`)
  - `liquidity_filter`: 12 (symbol: `ADAUSD`)
- Top reasons include:
  - `EGeneral:Temporary lockout` (14)
  - `no_intent` (33)
  - `liquidity_map` (12)
- Event bus topics:
  - `execution=29` (present)
  - `market_data=0`, `signal=0`, `decision=0`, `risk=0`, `portfolio=0`
- Hard invariants:
  - `profit_lock_sell_below_entry = 0`
  - `profit_lock_sell_below_min_profit = 0`
- Dashboard metrics:
  - `execution.orders_submitted_total = 0.0`
  - `execution.orders_rejected_total = 36.0`
  - `execution.fill_rate = 0.0`
  - `execution.reject_rate = 1.0`

## Current Blockers
- Exchange-side private API lockout events (`EGeneral:Temporary lockout`) intermittently block meaningful execution throughput.
- Strategy/runtime gates currently produce `no_intent` and `liquidity_filter` blockers in the observed window.

## Files Changed (this restart cycle)
- Added: `scripts/deep_system_health_check.py`
- Added: `scripts/install_deep_healthcheck_launchd.sh`
- Added: `OPERATIONAL_RESTART_REPORT.md`
- Generated runtime artifacts under `runs/kraken_spot_live_profit09/` and archived stale runtime files under `runs/_stale_archive/...`

## Final Summary
- FINAL STATUS: FAIL
- RESTART: CLEAN
- MASTERMIND: ACTIVE
- HARMONY: ACTIVE
- HEALTH CHECK: INSTALLED
- TESTS: 270 passed / 0 failed / 1 skipped
- FILES CHANGED: `scripts/deep_system_health_check.py`, `scripts/install_deep_healthcheck_launchd.sh`, `OPERATIONAL_RESTART_REPORT.md`

Interpretation: infrastructure restart and safety stack are healthy and active, but trading throughput is currently blocked by exchange lockout + gating (`no_intent`/`liquidity_filter`), therefore full operational success is not yet achieved.
