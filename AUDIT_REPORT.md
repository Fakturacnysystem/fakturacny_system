# AUDIT REPORT

## Architecture Map

Flow map (runtime wired):

1. Ingestion and market microstructure:
- `src/autonomous_investment_robot/services/data_ingestion/service.py`
- `src/autonomous_investment_robot/services/data_ingestion/multi_venue_engine.py`
- `src/autonomous_investment_robot/services/market_watch/service.py`
- `src/autonomous_investment_robot/services/microstructure/spread_spike.py`
- `src/autonomous_investment_robot/services/liquidity_map/service.py`

2. Feature generation and forecasting:
- `src/autonomous_investment_robot/services/feature_store/service.py`
- `src/autonomous_investment_robot/services/models/service.py`
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`

3. Central decision brain (new):
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
  - `AutonomousMarketPredictionAndDecisionEngine`
  - probabilistic forecasting, UQ, conformal, regime, drift, multimodal fusion, order-flow/LOB, execution-risk, trade management, self-optimization hooks

4. Policy, risk, governance, execution:
- `src/autonomous_investment_robot/services/policy/service.py`
- `src/autonomous_investment_robot/services/risk_engine/service.py`
- `src/autonomous_investment_robot/services/governance/service.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`

5. Orchestration and observability:
- `src/autonomous_investment_robot/core/orchestrator.py`
  - wired central decision brain into live decision path
  - maintained hard sell-invariant checks in orchestrator and live execution layer
- `src/autonomous_investment_robot/services/ops/harmony.py`
- `src/autonomous_investment_robot/services/mastermind/service.py`

6. Audit tooling:
- `scripts/audit_config_matrix.py` (resolved harmony matrix)
- `scripts/runtime_audit.py` (post-start runtime audit)
- `docs/config_matrix.json`, `docs/config_matrix.md`

## Blocker Matrix

| Reason | Source file:line | Exact fix |
|---|---|---|
| Required function-level autonomous APIs were missing from runtime | `src/autonomous_investment_robot/services/autonomous_decision/engine.py:1402`, `:1716` | Implemented all required named functions and integrated class graph; added central `run_decision_algorithm()` used by orchestrator. |
| Decision brain not connected to real runtime decision path | `src/autonomous_investment_robot/core/orchestrator.py:226`, `:2974`, `:3013` | Instantiated decision engine in orchestrator, built `DecisionContext` per tick, emitted decision brain audit/metrics, and advisory/enforceable intent shaping. |
| Mastermind supervisor preflight/runtime state existed but was not operationally enforced | `src/autonomous_investment_robot/core/orchestrator.py:1829`, `:1840`; `src/autonomous_investment_robot/services/mastermind/service.py:71` | Wired runtime `observe_runtime()` call, wrote metrics/overrides, added invariant-breach fatal handling and richer status schema (`health/guardrails/conflicts/overrides`). |
| Harmony dry-run matrix audit did not resolve configs via HarmonyResolver and produced weak audit output | `scripts/audit_config_matrix.py:105`, `:134`; `src/autonomous_investment_robot/services/ops/harmony.py:262` | Rebuilt matrix script to resolve every config through Harmony in dry-run mode and generate `docs/config_matrix.json` + `docs/config_matrix.md`. |
| Full-throttle script used conflicting legacy cadence knobs and incompatible fallback allowlist | `scripts/run_kraken_spot_profit_full_throttle.sh:33`, `:52` | Removed legacy cadence exports (`unset ...`) and aligned default allowlist with live-profit symbols. |
| Run-dir override from launcher was ignored by runtime config loader | `src/autonomous_investment_robot/cli_runtime_config.py:29`; `cli/run.py:39` | Added `AUTONOMOUS_RUN_DIR` precedence so launcher run-dir and watchdog run-dir align. |
| Remaining runtime blocker: live child can start without producing downstream artifacts in this environment | `runs/kraken_spot_live_profit_full_throttle/watchdog_state.json` | Not fully resolved in this pass; live launch reached child start but runtime artifacts (`audit.log`, `event_bus.jsonl`) were not emitted before blocking/termination in sandbox environment. |

## Knob Collision Matrix

| Setting group | Winner | Losers | Final precedence |
|---|---|---|---|
| Order cadence | `AUTONOMOUS_ORDER_CADENCE_S` | `AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS`, `AUTONOMOUS_TRADE_COOLDOWN_S`, `ORDER_SUBMISSION_INTERVAL_SECONDS` | If primary cadence is set, it wins; otherwise cadence is derived from legacy knobs (`max` with collision recording). |
| Min order quote | `max(exchange_min, user_min, legacy_min)` | lower values among `AUTONOMOUS_EXCHANGE_MIN_ORDER_QUOTE_FALLBACK`, `AUTONOMOUS_USER_MIN_ORDER_QUOTE`, `AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE` | Effective min order quote is always the strictest maximum. |
| Sell minimum profit floor | `max(120, explicit floor, modeled cost floor, configured net target)` | any lower configured value | Hard floor never below 120 bps. |
| Market watch interval | `AUTONOMOUS_MARKET_WATCH_EVERY_S` | legacy `AUTONOMOUS_MARKET_WATCH_INTERVAL_S`, `AUTONOMOUS_MARKET_WATCH_SECONDS` | Primary key wins if set; otherwise legacy fallback applies; collisions recorded. |
| Guards mode | `AUTONOMOUS_GUARDS_MODE` normalized to `strict` or `fatal_only` | invalid values | Invalid inputs normalize to default safe value. |

## Before/After Behavior

Before:
- No explicit central autonomous decision brain API surface with required function names.
- Orchestrator relied on policy/risk path only, without integrated probabilistic/UQ/conformal/drift decision object.
- Mastermind runtime status was preflight-only in orchestrator flow.
- Config matrix audit did not provide Harmony-resolved matrix outputs for all configs.
- Full-throttle script had cadence knob conflicts and allowlist mismatch risk.

After:
- Added modular AutonomousMarketPredictionAndDecisionEngine with required function-level APIs and named engine classes.
- Wired decision brain into live loop with decision tick audits/metrics and optional enforce mode (`AUTONOMOUS_DECISION_BRAIN_ENFORCE`).
- Added runtime mastermind observation wiring and deterministic bounded overrides.
- Hardened Harmony resolver for market-watch collision recording and config-path dry-run resolution.
- Rebuilt config matrix audit tooling and generated resolved matrix docs.
- Added runtime audit script to compute blocker categories, invariants, event bus coverage, and system verdict.
- Harmonized full-throttle launcher cadence and allowlist defaults.

## Remaining Blockers

1. Live artifact generation in current environment remains blocked/intermittent:
- Observed run-dir: `runs/kraken_spot_live_profit_full_throttle`
- State: watchdog child started, but runtime artifacts required for full post-start execution audit were not emitted.
- Immediate safe action: treat live mode as withheld; continue with paper/live-readonly validation in this environment.

2. Runtime audit verdict (latest live launcher attempt):
- `SYSTEM_STATE=BLOCKED`
- Execution topic absent and no submitted/blocked/rejected trade events were emitted.

## 2026-03-08 Upgrade Pass

### Architecture and Runtime Wiring Updates

1. Enhanced central decision brain integration:
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
  - added multimodal payload ingestion for news/macro/fundamental/sentiment (`DecisionContext` payload maps + prefixed extraction)
  - added forecast backend adapters for transformer-ready and foundation-ready forecasting hooks
  - integrated backend forecast adjustments into return/volatility distributions in live decision path
  - integrated signal decay detection into confidence/risk gating
  - integrated liquidity heatmap state, latency-arbitrage protection, execution quality guard
  - integrated dynamic TP expansion + smart hold extension + adaptive hold timing

2. Orchestrator wiring:
- `src/autonomous_investment_robot/core/orchestrator.py`
  - passed new autonomous config knobs into `AutonomousMarketPredictionAndDecisionEngine`
  - passed multimodal prefixed feature payloads into `DecisionContext` for real runtime use

3. Config surface expansion:
- `src/autonomous_investment_robot/config/settings.py`
  - extended `AutonomousDecisionSettings` with sentiment toggle, signal decay threshold, execution quality threshold, liquidity pressure threshold, adaptive hold base, forecast backend selectors
- `config.kraken_spot.live_profit.yaml`
  - added corresponding `autonomous` keys with safe defaults

4. Lockout and gating hardening:
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
  - temporary lockout-specific cooldown path and private API sync throttling
- `src/autonomous_investment_robot/services/execution/rate_limit_governor.py`
  - temporary lockout counted as rate-limit pressure
- `src/autonomous_investment_robot/core/orchestrator.py`
  - normalized rate-limit classification for temporary lockouts
  - neutral liquidity-map sessions no longer appear as blocking gate tags

### Tests and Validation Added

- `tests/test_autonomous_decision_engine.py`
  - transformer backend diagnostics wiring
  - signal decay guard behavior
  - foundation backend + sentiment feature path
- `tests/test_kraken_spot_live_service.py`
  - temporary lockout execution cooldown behavior
  - sync-fill fallback during lockout
- `tests/test_rate_limit_governor.py`
  - temporary lockout classified as rate-limit storm input

### Validation Evidence

- `python3 -m py_compile` on changed Python modules: pass
- targeted decision engine tests: pass
- full suite: `276 passed, 1 skipped`
- config matrix: `docs/config_matrix.json` + `docs/config_matrix.md` regenerated (13 configs, 0 errors)
- safe run path: `./scripts/run_paper.sh` pass
- post-run audit artifact:
  - `runs/kraken_spot_paper/runtime_audit_after_upgrade.json`

### Current External Blockers

1. Live Kraken private API auth/key scope remains environment-dependent and can still hard-block live starts (`EAPI:Invalid key` / temporary lockout waves) until key/scope correctness and cooldown recovery are stable.
2. In this run, safe paper execution is validated; live full-throttle remains gated by exchange-side auth/lockout conditions, not by missing local architecture.

## 2026-03-08 Live-Readiness Closure Pass

### Live Auth/Lockout Diagnostics Hardening

- `src/autonomous_investment_robot/connectors/cex/kraken_spot.py`
  - added deterministic private API diagnostics classifier:
    - `missing_credentials`
    - `invalid_credentials`
    - `invalid_permissions`
    - `temporary_lockout`
    - `invalid_nonce`
    - `network_unreachable`
    - `rate_limit`
  - added `diagnose_private_api_access()` and routed `verify_live_permissions()` through classified outcomes.

- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
  - preflight now consumes structured diagnostics when available.
  - writes `runs/<run_dir>/live_startup_diagnostics.json` with blocker class + permission diagnostics + cooldown snapshots.

- `scripts/run_kraken_spot_profit_full_throttle.sh`
  - startup preflight probe now records JSON diagnostics in run dir (`live_preflight_script_diag.json`).
  - fail-fast only on fatal auth blockers (`missing_credentials`, `invalid_credentials`, `invalid_permissions`, `invalid_nonce`).
  - temporary lockout/rate-limit/network blockers are classified warn-only and handled by runtime cooldown guards.

### Remaining Capability Gaps Closed Further

- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
  - multimodal fusion upgraded with coverage/quality metrics and modality presence accounting.
  - production-grade backend registry added:
    - built-ins: baseline/transformer/foundation
    - plugin path support: `module:ClassOrObject` via `AUTONOMOUS_FORECAST_BACKEND_PLUGIN`
  - SelfOptimizationEngine extended from hint-only to bounded adaptive application:
    - adjusts confidence/uncertainty/slippage/latency/liquidity thresholds within hard safe bounds
    - never touches hard sell invariants
  - added portfolio diversification + dynamic capital rotation scaling hooks into real allocation path.

- `src/autonomous_investment_robot/core/orchestrator.py`
  - wired new backend plugin + self-optimization config knobs into real engine constructor.
  - feeds portfolio scoring/rotation/correlation features into decision context for runtime capital rotation/diversification usage.

- `src/autonomous_investment_robot/services/ops/modifiers.py`
  - liquidity-map reason tags are now emitted only when liquidity map is actually restrictive (removes neutral false blocker tags).

### New/Updated Tests

- `tests/test_kraken_spot_signing.py`
  - temporary lockout classification
  - temporary lockout override path
  - invalid nonce classification

- `tests/test_kraken_spot_live_service.py`
  - preflight temporary-lockout classification + startup diagnostics file write

- `tests/test_autonomous_decision_engine.py`
  - plugin backend wiring test
  - bounded self-optimization application test
  - diversification/capital-rotation diagnostics test

- `tests/test_modifiers_pipeline.py`
  - neutral liquidity-map no longer emits liquidity blocker tag
  - restrictive liquidity-map still emits and applies controls

### Validation Results (This Pass)

- `python3 -m py_compile` on changed/new Python files: pass
- targeted tests: `73 passed`
- full suite: `285 passed, 1 skipped`
- project validation script: `./scripts/verify_harmony.sh` pass
- config matrix audit: 13 configs, 0 errors
- safe execution path: `./scripts/run_paper.sh` pass
- latest runtime audit: `runs/latest_runtime_audit.json` (run dir `runs/kraken_spot_paper`)

### Live Readiness Truth (Current Environment)

- live start command (`./scripts/run_kraken_spot_profit_full_throttle.sh`) is currently blocked in this shell due missing Kraken credentials in environment.
- connector diagnostics classification in this shell:
  - `{"ok": false, "classification": "missing_credentials", "scope": "credentials"}`
- result: internal code-side blockers addressed; remaining live blocker is external environment credential/auth state.
