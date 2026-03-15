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

## 2026-03-08 ULTRA Profit Full Throttle Pass

### Architecture Map (Current Runtime)

Runtime flow wired in code:
1. Discovery + universe classification
- `src/autonomous_investment_robot/services/market_discovery/service.py`
- `src/autonomous_investment_robot/services/universe/kraken_universe.py`

2. Orchestration + config truth + market-class filtering
- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/ops/harmony.py`

3. Decision brain (probabilistic/UQ/conformal/regime/drift/execution/risk)
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`

4. Execution routing + session-aware live guardrails
- `src/autonomous_investment_robot/services/execution/live_kraken_router_service.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`

5. Advisory/provider + runtime audit
- `src/autonomous_investment_robot/services/llm/provider.py`
- `src/autonomous_investment_robot/services/research/self_improvement.py`
- `scripts/runtime_audit.py`

### Runtime Flow Map

`ingestion -> features -> probabilistic forecast/UQ/conformal -> market regime + market state + nowcast -> alpha ensemble + confidence -> risk/execution gating -> position sizing + allocation -> execution routing/session checks -> audit/events/dashboard`

### Blocker Map (Reason -> File:Line -> Exact Fix)

| Reason | Source | Exact fix |
|---|---|---|
| xStocks were not first-class in discovery payload | `src/autonomous_investment_robot/services/market_discovery/service.py:107` | Added spot/perp market-class classification and explicit `xstocks_symbols`, `xstocks_etf_symbols`, `market_class_counts` outputs. |
| Universe selection did not enforce market-class toggles/allow-deny | `src/autonomous_investment_robot/services/universe/kraken_universe.py:203` | Added `enable_xstocks`, `enable_xstocks_etf`, allow/deny filters, diagnostics persistence (`universe_diagnostics.json`). |
| Router did not expose market class to downstream runtime | `src/autonomous_investment_robot/services/execution/live_kraken_router_service.py:64` | Added market-class map, `market_class_for_symbol()`, `market_classes_summary()`, and `session_state_for_symbol()`. |
| Live execution session adapter treated all symbols as 24/7 | `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py:184` | Added xStocks weekday session awareness, explicit `session_closed` blocking for entry intents, diagnostics fields. |
| Decision brain was not market-class/session aware | `src/autonomous_investment_robot/services/autonomous_decision/engine.py:39` | Added `market_class` modifiers + `market_session` guard integration into slippage/cadence thresholds and sizing/gating diagnostics. |
| Orchestrator did not propagate market class/session into central brain | `src/autonomous_investment_robot/core/orchestrator.py:3271` | Added market-class map lifecycle, universe market-class filtering, and `DecisionContext.market_class/market_session` wiring. |
| LLM model fallback not propagated through runtime constructor | `src/autonomous_investment_robot/core/orchestrator.py:192` | Added `model_primary`/`model_fallback` handoff to `LLMSelfImprovementAdvisor`. |
| Runtime audit lacked provider/xStocks diagnostics | `scripts/runtime_audit.py:286` | Added `provider_diagnostics` and `xstocks` sections sourced from run artifacts. |

### Weak-Point Map

- External live dependency remains the dominant blocker: Kraken credentials/scopes/lockout state are external to code execution environment.
- xStocks data availability still depends on account-level market availability and exchange metadata completeness.
- LLM advisory is optional by design; when keys are missing, core trading remains operational and advisory is disabled safely.

### Remaining Partial/Scaffolded Areas

- Multimodal external feeds (news/macro/fundamental/sentiment) are fully wired as ingestion interfaces but remain partially active when external feeds are absent.
- Transformer/foundation backend support is production-ready abstraction with optional plugin backend; heavy model backends remain scaffolded-by-plugin unless explicitly installed.
- SelfOptimizationEngine is bounded and active for threshold tuning, but still intentionally conservative (safe-range only).

### Before / After Expected Behavior

Before:
- xStocks not consistently classified and not surfaced in runtime diagnostics.
- Session awareness for xStocks not enforced in live entry path.
- Runtime audit did not report provider/xStocks health context.

After:
- xStocks market class is detected, filtered, routed, audited, and propagated into decision/execution context.
- Session-aware xStocks gating blocks entries when market session is closed.
- Runtime audit includes provider diagnostics + xStocks eligibility/filtering telemetry.
- ULTRA script exists and sets safe throughput + Groq/OpenAI-compatible advisory defaults.

### Safe Path vs Live Path Differences

- Safe path (`./scripts/run_paper.sh`): validated and green in this environment.
- Live path (`./scripts/run_kraken_ultra_profit_full_throttle.sh`): blocked in this shell by missing Kraken env credentials before startup.
- Therefore live readiness is code-ready but environment-blocked at credential gate in this execution context.

## 2026-03-08 Ultra Throughput Repair Pass (Current)

### Launch/Runtime Fixes Applied

1. False private budget depletion removed:
- `src/autonomous_investment_robot/services/reliability/rate_budget.py`
- `src/autonomous_investment_robot/core/orchestrator.py`
- Private rate-budget tokens are now refunded when `request_sent=false` (guard/no-op path), preventing synthetic `rate_budget_exhausted`.

2. Missing-depth microstructure overblock removed:
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
- Added `AUTONOMOUS_MICROSTRUCTURE_REQUIRE_DEPTH` (default `false`) and pass-through behavior when depth signal is unavailable.

3. Dynamic universe quote-currency mismatch fixed:
- `src/autonomous_investment_robot/core/orchestrator.py`
- Added quote-aware market filter (`AUTONOMOUS_UNIVERSE_QUOTE_ALLOWLIST`) for crypto spot so dynamic universe does not keep selecting unsupported quote currencies (e.g., `*XBT`) for USD-funded runtime.

4. ULTRA profile tightening:
- `scripts/run_kraken_ultra_profit_full_throttle.sh`
- Added explicit throughput/safety envs:
  - `AUTONOMOUS_MAX_ORDERS_PER_MIN=30`
  - `AUTONOMOUS_MAX_PUBLIC_CALLS_PER_MIN=240`
  - `AUTONOMOUS_NO_TRADE_ZONE_REQUIRE_DEPTH=false`
  - `AUTONOMOUS_EXPECTED_FILL_REQUIRE_DEPTH=false`
  - `AUTONOMOUS_MICROSTRUCTURE_REQUIRE_DEPTH=false`
  - `AUTONOMOUS_UNIVERSE_QUOTE_ALLOWLIST=USD,EUR,USDT`
  - `AUTONOMOUS_QUOTE_RESERVE_RATIO=0.90`
  - `AUTONOMOUS_PROBE_QUOTE_RESERVE_RATIO=0.65`

### Current Runtime Truth (after restart)

- Run dir: `runs/kraken_ultra_profit_full_throttle`
- Live startup preflight: `ok`
- Harmony: `guards_mode=fatal_only`, `order_cadence_s=9`, `sell_min_profit_bps=120`
- Hard invariants: no sell-below-entry, no sell-below-min-profit violations
- `rate_budget_exhausted`: eliminated from current-window top blockers
- Market-class filter now reports `quote_not_allowed:XBT` blocks instead of attempting those pairs

### Current Remaining Blockers

Valid blockers still active:
- `liquidity_map` / `spread_spike` (market condition guards)
- `no_intent` / `fee_aware_no_edge` (decision-quality guards)
- `insufficient_balance` on small quote balance (account-level constraint)

Not retained as unresolved internal blocker:
- synthetic private budget depletion
- quote-currency universe mismatch selecting `*XBT` pairs in USD profile

## 2026-03-09 Fatal-Only Mastermind De-Block Pass

### Launch-Chain / Runtime Repairs

1. `fatal_only` now treats non-fatal Mastermind stress as warn-only:
- `src/autonomous_investment_robot/services/mastermind/service.py`
- `observe_runtime(..., guards_mode=...)` now keeps `pause_buy=false` for non-fatal stress in `fatal_only` mode (`insufficient_balance_warn`, `rate_stress_warn`).

2. Orchestrator now passes resolved guards mode into Mastermind runtime evaluation:
- `src/autonomous_investment_robot/core/orchestrator.py`
- `self.mastermind_supervisor.observe_runtime(..., guards_mode=str(guards_mode))`

3. Test coverage added for warn-only behavior in `fatal_only`:
- `tests/test_mastermind_supervisor.py`
- Added:
  - `test_runtime_insufficient_balance_is_warn_only_in_fatal_only_mode`
  - `test_runtime_rate_stress_is_warn_only_in_fatal_only_mode`

### Post-Restart Runtime Truth

- Script used: `./scripts/run_kraken_ultra_profit_full_throttle.sh`
- Run dir: `runs/kraken_ultra_profit_full_throttle`
- Continuous runtime: `running` (`cli.run` + `cli.worker` active)
- Mastermind runtime state now shows:
  - `pause_buy=false`
  - reason `insufficient_balance_warn` (warn-only, no hard pause)
- Hard invariants remain intact (no sell-below-entry / no sell-below-min-profit violations).

### Current Remaining Real Blockers (Valid)

- `insufficient_balance_block` (available quote below effective minimum for current symbol path)
- `fee_aware_no_edge` (net edge after modeled costs below threshold)
- `no_intent` episodes during compression regime

These are valid safety/economic blockers, not false launch-chain or supervisor pause blockers.

## 2026-03-09 Cloud Distributed Upgrade (Variant A / Practical Variant 1)

### Architecture Map (Implemented)

- Live node runtime:
  - `cli.run` (`AUTONOMOUS_NODE_ROLE=live`) + watchdog + `cli.worker`
  - execution/risk/guardrails/audit loop remains in `RobotOrchestrator`
  - distributed compute bridge integration with strict timeout + local fallback
- Compute node runtime:
  - `cli.compute_node` (`AUTONOMOUS_NODE_ROLE=compute`)
  - consumes scan tasks from Redis Streams and publishes ranking results
- Shared infra contracts:
  - Redis Streams tasks/results/audit envelopes
  - optional Postgres mirror sink for decision/execution/audit snapshots

### Runtime Flow (Current)

`live orchestrator` -> `distributed ranking request` -> `compute bridge (redis or local fallback)` -> `decision/risk/execution` -> `audit + event bus + optional Postgres mirror`.

### Blocker Matrix (Current)

| Reason | Source | Exact fix |
|---|---|---|
| Docker CLI unavailable on host (`docker: command not found`) | local execution environment | Install Docker Desktop/Engine on deployment host before compose validation/startup. |
| Compute node Redis connection refused (no Redis service running locally) | `cli.compute_node` / `RedisComputeWorker.connect()` | Start Redis (`docker compose -f docker-compose.compute.yml up -d redis`) or point `AUTONOMOUS_REDIS_URL` to reachable Redis endpoint. |
| Live trading remains economically blocked (`no_intent`, `insufficient_balance`, `cooldown_active`) | runtime audit `runs/kraken_ultra_profit_full_throttle/audit.log` | Keep hard guards; tune cadence/affordability and increase effective free quote balance per symbol path. |

### Knob Collision Matrix (Cloud Runtime)

| Setting | Winner | Losers | Final precedence |
|---|---|---|---|
| node role | `AUTONOMOUS_NODE_ROLE` env | `distributed.node_role` config | env wins for launcher/deploy explicit role |
| distributed enable | `AUTONOMOUS_DISTRIBUTED_ENABLED` env | `distributed.enabled` config | env wins |
| compute bridge backend | `AUTONOMOUS_COMPUTE_BRIDGE` env | `distributed.compute_bridge` config | env wins |
| redis URL | `AUTONOMOUS_REDIS_URL` env (fallback `REDIS_URL`) | `distributed.redis_url` config | env wins |
| postgres mirror dsn | `AUTONOMOUS_POSTGRES_DSN` env (fallback `POSTGRES_DSN`) | `distributed.postgres_dsn` config | env wins |
| advisory on live node | `AUTONOMOUS_DISABLE_ADVISORY_ON_LIVE_NODE` env | `distributed.disable_advisory_on_live` config | env wins |

### Before / After (Cloud Readiness)

Before:
- no Redis-stream compute bridge in runtime path
- no compute-node executable role
- no optional Postgres mirror sink
- no dedicated live/compute/full cloud compose bundles

After:
- distributed bridge + compute worker + envelope contracts implemented
- live runtime wired with timeout/fallback distributed ranking path
- optional Postgres mirror sink integrated (non-fatal on failure)
- deployment artifacts added (`docker-compose.live/compute/full.yml`, deploy env templates, start/deploy scripts, cloud docs)

### Remaining Blockers / Classification

- Variant A: **partially implemented** (code and artifacts ready; host docker/runtime infra still required externally).
- Practical Variant 1: **partially implemented** (live/compute separation and contracts implemented; full cluster runtime blocked in this host by missing docker/redis service runtime).
- Variant 2: **scaffolded** (service boundaries/contracts prepared; full microservice extraction intentionally deferred).

## 2026-03-09 Distributed Contract Hardening Pass

### What Changed

- Added Redis Streams consumer-group contracts:
  - `live_node`
  - `compute_node`
- Hardened `RedisComputeBridge` to:
  - initialize stream groups
  - read result stream via `XREADGROUP`
  - ACK consumed ranking results
  - expose consumer-group diagnostics
- Hardened `RedisComputeWorker` to:
  - consume `scan`, `forecast`, and `optimize` tasks via `XREADGROUP`
  - ACK processed/skipped tasks
  - publish ranking/signal/audit envelopes
  - keep compute errors non-fatal to live safety path
- Added non-blocking distributed audit publish path:
  - `OpsService.audit_event()` writes local audit log and best-effort publishes to `autobot.events.audit`
- Added deployment manifest validator:
  - `scripts/validate_deployment_manifests.py`
  - validates compose/env templates even when Docker CLI is unavailable

### Validation Snapshot

- Compile: pass
- Targeted tests: `tests/test_distributed_services.py` => `9 passed`
- Full tests: `335 passed, 1 skipped`
- Deploy manifest validation: pass
- Config matrix audit: pass (`13 configs, 0 errors`)
- Live runtime relaunched in ultra mode and audited:
  - run dir: `runs/kraken_ultra_profit_full_throttle`
  - `SYSTEM_STATE=BLOCKED`
  - hard invariants: no violations
  - dominant blockers: `cooldown_active`, `no_intent`, `insufficient_balance`

### Remaining Truth

- Distributed architecture is materially improved and wired into the real runtime path.
- Full distributed cluster validation in this machine remains externally constrained by missing Docker/Redis daemon availability.
- Live trading throughput remains economically/risk blocked by valid runtime guards, not by broken distributed wiring.

## 2026-03-09 Causal Market Twin Engine Pass

### Architecture Upgrade

Implemented a real runtime `CausalMarketTwinEngine` in:
- `src/autonomous_investment_robot/services/autonomous_decision/causal_market_twin.py`

Implemented submodules:
- `RealityStateBuilder`
- `CausalDriverEstimator`
- `CounterfactualScenarioEngine`
- `PathForecastEngine`
- `ExecutionTwinEngine`
- `DecisionArbitrationEngine`

Implemented key data models:
- `MarketTwinSnapshot`
- `CausalExplanation`
- `DecisionScenario`
- `ExecutionScenario`
- `PathRiskProfile`

### Runtime Integration Points

Wired into real decision runtime:
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
  - inside `run_decision_algorithm()` before risk finalization / route selection
  - affects:
    - entry gating (`counterfactual_no_edge`, `counterfactual_wait_preferred`)
    - route preference (`maker`/`taker`)
    - bounded position sizing scale
    - optional exit override (`partial_close`/`full_close`)
  - persists bounded snapshots into `engine.model_state`
  - attaches structured diagnostics via `diagnostics.market_twin`

Orchestrator audit wiring:
- `src/autonomous_investment_robot/core/orchestrator.py`
  - adds `signal_age_s` into `DecisionContext`
  - emits `market_twin_*` fields in `decision_brain_tick`

### Counterfactual MVP Status

Counterfactual Entry Engine MVP is implemented and runtime-active:
- market entry now
- limit entry now
- wait one cadence
- skip

Per-scenario evaluation includes:
- expected net edge after costs
- fill probability
- slippage/adverse selection proxies
- interim drawdown/false-breakout/signal-decay risk
- path quality

### Validation Snapshot

- `python3 -m py_compile` on changed files: pass
- targeted tests:
  - `tests/test_causal_market_twin_engine.py`
  - `tests/test_autonomous_decision_engine.py`
  - result: pass
- full suite: `348 passed, 1 skipped`
- repo validations:
  - `scripts/verify_harmony.sh`: pass
  - `scripts/audit_config_matrix.py`: pass
  - `scripts/validate_deployment_manifests.py`: pass
- safe runtime path:
  - `scripts/run_paper.sh`: pass
  - runtime audit output: `runs/latest_runtime_audit_market_twin.json`

### Known Data Limits (Truthful)

- Causal attribution is probabilistic/heuristic, not deterministic proof.
- Optional modalities (news/macro/fundamentals/sentiment) are used only when present.
- Queue-position level execution modeling remains approximate because full L2 queue data is not always available.

class AutonomousMarketPredictionAndDecisionEngine:
    # ...existing code...

    def analyze_order_flow_imbalance(self, ctx) -> float:
        """
        Estimate order flow imbalance (OFI) as a proxy for buy/sell pressure.
        Returns value in [-1, 1], where positive = buy pressure.
        """
        buy_vol = ctx.features.get("buy_volume", 0.0)
        sell_vol = ctx.features.get("sell_volume", 0.0)
        total = buy_vol + sell_vol
        if total == 0:
            return 0.0
        return (buy_vol - sell_vol) / total

    def model_limit_order_book(self, ctx) -> dict:
        """
        Return basic limit order book state.
        """
        return {
            "bid_depth": ctx.features.get("bid_depth", 0.0),
            "ask_depth": ctx.features.get("ask_depth", 0.0),
            "spread": ctx.spread_bps,
        }

    def estimate_liquidity_pressure(self, ctx) -> float:
        """
        Estimate liquidity pressure (0=loose, 1=tight).
        """
        bid = ctx.features.get("bid_depth", 1.0)
        ask = ctx.features.get("ask_depth", 1.0)
        spread = ctx.spread_bps
        # Simple proxy: higher spread and lower depth = tighter
        return min(1.0, max(0.0, (spread / 100.0) + (1.0 - min(bid, ask))))

    def estimate_execution_latency_risk(self, ctx) -> float:
        """
        Estimate risk from execution latency (0=low, 1=high).
        """
        latency_ms = ctx.features.get("latency_ms", 100)
        return min(1.0, latency_ms / 1000.0)

    def estimate_transaction_costs(self, ctx) -> float:
        """
        Estimate transaction costs in bps.
        """
        spread = ctx.spread_bps
        fee = ctx.features.get("fee_bps", 10.0)
        slippage = ctx.features.get("slippage_bps", 2.0)
        return spread + fee + slippage

    def control_slippage(self, ctx, intended_size: float) -> float:
        """
        Control slippage by adjusting order size if liquidity is tight.
        """
        liquidity = self.estimate_liquidity_pressure(ctx)
        if liquidity > 0.8:
            return intended_size * 0.5  # reduce size in tight liquidity
        return intended_size

    def detect_concept_drift(self, ctx, recent_metrics: dict) -> bool:
        """
        Detect concept drift based on recent performance metrics.
        Returns True if drift is detected.
        Extended: considers Sharpe, winrate, drawdown, volatility spike, loss streak, regime change, and adaptation fatigue.
        """
        sharpe = recent_metrics.get("rolling_sharpe", 1.0)
        winrate = recent_metrics.get("rolling_winrate", 0.6)
        drawdown = recent_metrics.get("max_drawdown", 0.0)
        vol_spike = recent_metrics.get("volatility_spike", False)
        loss_streak = recent_metrics.get("rolling_loss_streak", 0)
        regime = recent_metrics.get("regime", None)
        prev_regime = ctx.features.get("last_regime", None)
        adaptation_count = ctx.features.get("adaptation_count", 0)
        regime_change = regime is not None and prev_regime is not None and regime != prev_regime
        # Extended: drift if adaptation fatigue (too many adaptations in short window)
        fatigue = adaptation_count >= 5
        if sharpe < 0.2 or winrate < 0.4 or drawdown > 0.25 or vol_spike or loss_streak >= 3 or regime_change or fatigue:
            return True
        return False

    def adapt_model_online(self, ctx, drift_detected: bool) -> None:
        """
        Adapt model parameters online if drift detected (bounded).
        Extended: logs adaptation event, regime change, and adaptation fatigue.
        """
        if drift_detected:
            self.confidence_threshold = min(1.0, self.confidence_threshold + 0.05)
            self.uncertainty_threshold_bps = max(10.0, self.uncertainty_threshold_bps - 5.0)
            ctx.features["rolling_sharpe"] = 1.0
            ctx.features["risk_guard"] = min(1.0, ctx.features.get("risk_guard", 0.5) + 0.1)
            ctx.features["rolling_loss_streak"] = 0
            ctx.features["last_adaptation"] = "drift_detected"
            if "regime" in ctx.features:
                ctx.features["last_regime"] = ctx.features["regime"]
            # Extended: log adaptation fatigue if adaptation_count is high
            if ctx.features.get("adaptation_count", 0) >= 5:
                ctx.features["adaptation_fatigue"] = True

    def update_model_incrementally(self, ctx, new_data: dict) -> None:
        """
        Incrementally update model state with new data (bounded, safe).
        Extended: tracks adaptation count, regime history, and adaptation fatigue reset.
        """
        if "recent_volatility" in new_data:
            ctx.features["expected_volatility"] = 0.9 * ctx.features.get("expected_volatility", 0.01) + 0.1 * new_data["recent_volatility"]
        if "recent_win" in new_data:
            ctx.features["rolling_winrate"] = 0.95 * ctx.features.get("rolling_winrate", 0.6) + 0.05 * new_data["recent_win"]
        if "recent_loss" in new_data:
            if new_data["recent_loss"]:
                ctx.features["rolling_loss_streak"] = ctx.features.get("rolling_loss_streak", 0) + 1
            else:
                ctx.features["rolling_loss_streak"] = 0
        ctx.features["adaptation_count"] = ctx.features.get("adaptation_count", 0)
        if ctx.features.get("last_adaptation") == "drift_detected":
            ctx.features["adaptation_count"] += 1
            ctx.features["last_adaptation"] = None
        if "regime" in new_data:
            history = ctx.features.get("regime_history", [])
            history.append(new_data["regime"])
            ctx.features["regime_history"] = history[-10:]
        # Extended: reset adaptation fatigue if regime stabilizes
        if len(set(ctx.features.get("regime_history", []))) == 1:
            ctx.features["adaptation_fatigue"] = False

# Rozšírené testy
# filepath: tests/test_autonomous_decision_engine.py

def test_detect_concept_drift_with_regime_change():
    engine = AutonomousMarketPredictionAndDecisionEngine()
    ctx = _base_context()
    ctx.features["last_regime"] = "trend"
    drift = engine.detect_concept_drift(ctx, {"regime": "mean-revert"})
    assert drift is True

def test_adapt_model_online_logs_adaptation_and_regime():
    engine = AutonomousMarketPredictionAndDecisionEngine(confidence_threshold=0.5, uncertainty_threshold_bps=50)
    ctx = _base_context()
    ctx.features["regime"] = "trend"
    engine.adapt_model_online(ctx, drift_detected=True)
    assert ctx.features["last_adaptation"] == "drift_detected"
    assert ctx.features["last_regime"] == "trend"

def test_update_model_incrementally_tracks_adaptation_and_regime_history():
    engine = AutonomousMarketPredictionAndDecisionEngine()
    ctx = _base_context()
    ctx.features["adaptation_count"] = 0
    ctx.features["last_adaptation"] = "drift_detected"
    engine.update_model_incrementally(ctx, {"regime": "trend"})
    assert ctx.features["adaptation_count"] == 1
    assert ctx.features["regime_history"][-1] == "trend"
    # Add more regimes to test history length
    for r in ["mean-revert", "panic", "breakout", "chop", "trend", "bull", "bear", "sideways", "compression", "breakout"]:
        engine.update_model_incrementally(ctx, {"regime": r})
    assert len(ctx.features["regime_history"]) <= 10

def test_detect_concept_drift_with_adaptation_fatigue():
    engine = AutonomousMarketPredictionAndDecisionEngine()
    ctx = _base_context()
    ctx.features["adaptation_count"] = 6
    drift = engine.detect_concept_drift(ctx, {})
    assert drift is True

def test_adapt_model_online_sets_adaptation_fatigue():
    engine = AutonomousMarketPredictionAndDecisionEngine(confidence_threshold=0.5, uncertainty_threshold_bps=50)
    ctx = _base_context()
    ctx.features["adaptation_count"] = 6
    ctx.features["regime"] = "trend"
    engine.adapt_model_online(ctx, drift_detected=True)
    assert ctx.features["adaptation_fatigue"] is True

def test_update_model_incrementally_resets_adaptation_fatigue_on_stable_regime():
    engine = AutonomousMarketPredictionAndDecisionEngine()
    ctx = _base_context()
    ctx.features["regime_history"] = ["trend"] * 10
    ctx.features["adaptation_fatigue"] = True
    engine.update_model_incrementally(ctx, {"regime": "trend"})
    assert ctx.features["adaptation_fatigue"] is False

#### Further Additional Test Coverage (2026-03-14, adaptation fatigue extension)

- **test_detect_concept_drift_with_adaptation_fatigue:**  
  - Overuje, že drift je detekovaný aj pri vysokej hodnote adaptation_count (adaptation fatigue).
- **test_adapt_model_online_sets_adaptation_fatigue:**  
  - Overuje, že adaptácia nastaví adaptation_fatigue na True pri vysokej adaptation_count.
- **test_update_model_incrementally_resets_adaptation_fatigue_on_stable_regime:**  
  - Overuje, že adaptation_fatigue sa resetuje na False, keď je režim stabilný.

**Výsledky:**  
- Všetky nové rozšírené testy prešli.
- Evolučná/adaptačná vrstva teraz pokrýva aj adaptation fatigue a jej reset pri stabilizácii
