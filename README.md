# Autonomous Investment Robot

Kraken-SPOT-doctrine runtime with fail-closed live gating and fully unlocked paper, replay, and readonly analysis surfaces.

Legacy derivative live services remain in source only as readonly/diagnostic compatibility shims. Order-capable derivative execution is explicitly blocked by doctrine.

## Safety invariants (hard fail-closed)
- Live order placement is blocked unless both env flags are true:
  - `ENABLE_LIVE_TRADING=true`
  - `ACK_I_UNDERSTAND_RISKS=true`
- Full-stage `config.kraken_spot.live_profit.yaml` is additionally blocked unless:
  - `ENABLE_FULL_LIVE_STAGE=true`
- Live order placement is blocked unless:
  - `provider_whitelist` includes `kraken_spot`
  - critical risk + TCO limits are explicit (no `UNSPECIFIED`)
  - API key + secret env vars exist and config validates
- Any of stale-data, schema mismatch, cross-feed divergence, reconciliation mismatch, auth errors, reject storm, abnormal latency => kill + safe mode + flatten + cooldown.
- Keys must be trade-only with withdrawals disabled. If API permissions cannot be verified, live is refused unless `execution.binance.allow_unknown_permissions=true` is explicitly set.

## Truth ownership
- Explicit ownership for balance/fill/order/position/fee/realized PnL/unrealized PnL is documented in `docs/truth_ownership_map.md`.
- Runtime emits `TRUTH_OWNER_DECLARED` entries to `events_truth.jsonl` and emits `TRUTH_OWNERSHIP_GAP` risk events for declared ownership gaps.
- Runtime separately emits `TRUTH_CONFIDENCE_SNAPSHOT` to distinguish owner-of-truth from current confidence (`authoritative`, `proxy`, `unavailable`) for the current run.
- Reconciliation reason/severity/action model is documented in `docs/reconciliation_truth.md`.
- Architecture/runtime upgrade details are documented in `docs/architecture_upgrade.md`.
- Operator-facing runtime artifact and risk-mode guidance is documented in `docs/operator_runtime.md`.
- Live authority, release baseline, promotion discipline, and operator runtime review are defined in:
  - `LIVE_AUTHORITY_BOUNDARY.md`
  - `RELEASE_BASELINE.md`
  - `PROMOTION_GATES.md`
  - `RUN_REVIEW_TEMPLATE.md`
  - `OPERATOR_RUNTIME_CHECKLIST.md`

## Architecture highlights
- `RobotOrchestrator` now coordinates explicit bounded contexts for market data, regime, alpha, portfolio, health, learning, and observability while preserving existing entrypoints.
- Live execution now ingests exchange-native trade history for fill/fee/realized-PnL truth and uses dedicated live-runtime coordinators for restart rehydration, market sensing, decisioning, and ledger updates.
- Recovery, reconciliation, runtime control, and downgrade routing are now split into dedicated live coordinators so the live loop is a thin sequencer instead of a single inlined control block.
- `PolicyService.make_intent()` remains backward-compatible, but richer `evaluate_decision()` output now exists for explicit no-trade decisions.
- Live policy now also consumes heuristic probabilistic `quantum_state_service` output and `edge_immunity_service` stress output as additive evidence before trading.
- Live policy now also consumes heuristic `spre_service` and `shadow_rival_service` outputs for richer parallel-reality dominance, probe-vs-wait optionality, and adversarial veto/throttle before risk.
- `RiskEngineService` now exposes explicit risk modes and additional fail-closed inputs.
- `ExecutionService` now has execution-quality forecasting and execution planning alongside existing execution methods.
- `ExecutionService` now also exposes venue-constraint normalization and a provider capability matrix journal so lifecycle, truth, and order semantics stay explicit per venue.
- `MarketIntegrityService` and `SharedVenueLimitGovernor` now evaluate feed/book integrity plus provider capability truth before live decisioning and emit dedicated journals for operator review.
- `CapitalSovereigntyService`, `PositionMorphingEngine`, and `AdaptiveExitAllocator` now sit on the live decision path and emit dedicated capital/exit evidence without breaking legacy execution contracts.
- `SyntheticAffectEngine` now modulates aggression, pacing, wait-vs-trade preference, and de-risking as a synthetic regulatory layer that cannot bypass truth, rollout, or risk gates.
- `EventIntelligenceService` now wires source trust, freshness/novelty, asset relevance, market impact, priced-in probability, adversarial narrative filtering, and provenance into live and paper evidence paths.
- Event intelligence now also emits decomposed evidence journals (`source_trust`, `freshness_novelty`, `asset_relevance`, `market_impact`, `priced_in`, `adversarial_narrative`, `data_provenance`) instead of only the aggregate report.
- `ExecutionSimulationSandbox`, `HumanEscalationLayer`, `EpisodicTradeMemory`, `AnalogTradeLookup`, `CounterfactualEvaluator`, and `ObservabilityFacade` are now wired so execution-stress, escalation, memory, analog reasoning, and counterfactual evidence have dedicated channels.
- `DecisionDoctrineService` now synthesizes truth strength, market/provider integrity, execution survivability, robustness, capital freedom, uncertainty pressure, and regret pressure into one top-level doctrine gate before final risk permissioning.
- `MastermindService` is no longer a noop stub on the live path. It now acts as a bounded-safe advisory layer that can only shrink, probe, wait, or veto based on truth weakness, integrity weakness, execution toxicity, event hostility, and regime fragility.
- `ExecutionService` now also consumes doctrine context from the final decision path so execution style, participation, probe sizing, and forced-exit aggressiveness follow the same top-level doctrine instead of using isolated local heuristics.
- `HumanEscalationLayer` now also writes `MANUAL_REVIEW_REQUIRED.json` into the run directory when runtime disagreement is severe enough to require manual review or flatten-only posture.
- `forensics_service` now emits `pnl_attribution.jsonl` and `loss_autopsy.jsonl` artifacts for structured post-trade and runtime anomaly review.
- `forensics_service` now also emits `post_trade_summary.jsonl` and `loss_review_summary.jsonl` for operator-facing trade and incident review.
- `inventory_service` and `profitability_service` now enforce inventory-pressure, reserve, and round-trip profitability evidence before new opens.
- Paper runs now emit structured journals: `config_manifest.jsonl`, `signal_journal.jsonl`, `policy_journal.jsonl`, `execution_journal.jsonl`, and `learning_records.jsonl`.
- Live runs additionally emit `truth_confidence_journal.jsonl`, `fills_journal.jsonl`, `accounting_truth_journal.jsonl`, `recovery_journal.jsonl`, `reconciliation_journal.jsonl`, `meta_governor_journal.jsonl`, `control_journal.jsonl`, `market_integrity_journal.jsonl`, `market_integrity_evidence_journal.jsonl`, `venue_limit_journal.jsonl`, and `provider_capability_journal.jsonl`.
- Live and paper runs now emit `quantum_state_journal.jsonl`, `edge_immunity_journal.jsonl`, `mastermind_journal.jsonl`, `spre_journal.jsonl`, `shadow_rival_journal.jsonl`, `decision_doctrine_journal.jsonl`, `execution_simulation_journal.jsonl`, `human_escalation_journal.jsonl`, `analog_trade_lookup.jsonl`, and `counterfactual_review.jsonl`; SPRE/shadow/doctrine/mastermind journals now include action rankings, survival ratio, dominance gap, failure clusters, kill-path evidence, truth strength, partial-truth penalty, regret pressure, or bounded-safe advisory rationale depending on the channel. Paper and live runs can emit `pnl_attribution.jsonl`, `loss_autopsy.jsonl`, `post_trade_summary.jsonl`, `loss_review_summary.jsonl`, `decision_doctrine_summary.jsonl`, and `mastermind_summary.jsonl`.
- Live runs now also refresh `kraken_spot_operator_summary.json`, `live_capability_matrix.json`, `live_activated_capabilities.json`, `live_still_gated_capabilities.json`, `live_doctrine_blocked_capabilities.json`, and `live_artifact_index.json` during the actual live loop.

## Kraken SPOT doctrine profiles
- Paper baseline: `config.kraken_spot.paper.yaml`
- Paper full analysis: `config.kraken_spot.paper_full_analysis.yaml`
- Replay full analysis: `config.kraken_spot.replay_full_analysis.yaml`
- Readonly full analysis (no order placement): `config.kraken_spot.readonly_analysis.yaml`
- Kraken SPOT guarded live: `config.kraken_spot.live.yaml`
- Kraken SPOT higher-notional guarded live: `config.kraken_spot.live_profit.yaml`
- Both supported Kraken SPOT live configs start in normal risk mode. Hard doctrine, reconciliation, market-integrity, market-watch, and pre-submit capital-protection gates remain authoritative.
- Doctrine-incompatible derivatives/perps configs remain in the repo, but config-file launch is intentionally blocked.

## Capability activation map
- Active for Kraken SPOT paper / replay / readonly full analysis:
  - `MarketIntegrityService`
  - `VenueCapabilityRegistry`
  - `HarmonyConfigResolver`
  - `MarketWatchService`
  - `QuantumScenarioService`
  - `SignalInterferenceEngine`
  - `EdgeImmunityService`
  - `SPREEngine`
  - `ShadowRivalService`
  - `CapitalSovereigntyService`
  - `PositionMorphingEngine` in spot-compatible entry/de-risk/reduce-only shapes
  - `AdaptiveExitAllocator`
  - `SyntheticAffectEngine`
  - `ExecutionSimulationSandbox`
  - `HumanEscalationLayer`
  - `ReplayReportingCoordinator`
  - `OperatorSummaryCoordinator`
  - `PnL attribution`, `loss autopsy`, `episodic memory`, `analog lookup`, `counterfactual review`
- Active but partial unless external event evidence is supplied:
  - `EventIntelligenceService`
  - `SourceTrustService`
  - `FreshnessNoveltyEngine`
  - `AssetRelevanceMapper`
  - `MarketImpactInterpreter`
  - `PricedInProbabilityEngine`
  - `AdversarialNewsFilter`
  - `DataProvenanceLedger`
- Explicitly blocked by doctrine:
  - derivatives/perps configs and launchers
  - `DeltaNeutralCarryStrategy`
  - `BasisStrategy`
  - `PairsStatArbStrategy`
  - `CarryStrategy`
  - negative-direction fresh entries from directional strategies
  - any non-reduce SELL that is not inventory-backed

## Kraken SPOT live setup
1. Create Kraken SPOT API credentials:
- Spot trading enabled.
- Withdrawals disabled.
- IP allowlist strongly recommended.

2. Configure runtime env:
```bash
KRAKEN_SPOT_API_KEY=...
KRAKEN_SPOT_API_SECRET=...
ENABLE_LIVE_TRADING=false
ACK_I_UNDERSTAND_RISKS=false
ENABLE_FULL_LIVE_STAGE=false
ROBOT_ROLLOUT_STAGE_OVERRIDE=
KRAKEN_SPOT_EVENT_FEED_PATH=
```

Supported runtime env sources:
- `TRADING_ENV_FILE=/absolute/path/to/runtime.env`
- `${SECRETS_DIR}/trading-engine.env`
- `~/.config/trading-bot/runtime.env`
- `~/.config/trading-bot/trading-engine.env`
- `./secrets/trading-engine.env`

3. Controlled rollout ladder:
1. `readonly` via `config.kraken_spot.readonly_analysis.yaml` with `execution.mode=live_readonly` and resolved `rollout_stage=shadow`
2. `shadow` via readonly analysis plus additive decision-comparison artifacts
3. `tiny_live` via `config.kraken_spot.tiny_live.yaml` with `execution.mode=live` and explicit `rollout_stage=tiny_live`
4. `limited_live` via `config.kraken_spot.live.yaml`
5. `normal_live` via `config.kraken_spot.live_profit.yaml` with `ENABLE_FULL_LIVE_STAGE=true`

## Create a new local environment
```bash
make env
source .venv/bin/activate
```

`make env` creates `.venv` and creates `.env` from `.env.example` if missing. Install dependencies afterwards with `pip install -e .`.

## Commands
```bash
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.kraken_spot.paper.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.kraken_spot.paper_full_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot replay-report --config config.kraken_spot.replay_full_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot ack-review --run-dir runs/<run_id> --reviewer ops --notes "manual review approved"
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live_profit.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.kraken_spot.live.yaml
python3 scripts/deployment_preflight.py
python3 scripts/runtime_status.py --run-dir runs/<run_id>
python3 scripts/runtime_healthcheck.py --run-dir runs/<run_id>
python3 scripts/collect_diagnostics_bundle.py --run-dir runs/<run_id>
python3 scripts/verify_server_parity.py --runtime-path /opt/trading-bot/core
```

## Deployment truth
- `infra/docker-compose.yml` is the only supported compose manifest in this repo, and only for infra dependencies.
- Root `docker-compose.yml` is an explicit `legacy_blocked` manifest. It is not a supported live runtime source.
- `src/autonomous-investment-robot/` is an archival duplicate snapshot and is excluded from the supported build/deploy surface.
- `apps/`, `tools/`, `bootstrap_mac.sh`, and `codex_ultra_master_prompt.md` are excluded from the supported deploy context.
- Use `python3 scripts/deployment_preflight.py` before any deploy or restart decision.
- Use `python3 scripts/verify_server_parity.py --runtime-path <path>` after sync/deploy to prove local/runtime parity.
- Use `python3 scripts/tiny_live_promotion_readiness.py --run-dir <run_dir> --secrets-dir <secrets_dir>` before any readonly/shadow -> tiny_live promotion.

## Requested doctrine status
- Launch-gated live target: `kraken_spot` only.
- Product doctrine: `spot` only.
- Position doctrine: `long_only`.
- Hard live sell gates:
  - no non-reduce sell
  - no sell below authoritative FIFO cost basis
  - no sell below modeled net profit floor `>= 120 bps`
- Harmony config resolution and `harmony_report.json` / `harmony_boot_report.json` are emitted into the run directory.
- MarketWatch blocks or degrades entries on blackout, spread, and liquidity failures.
- Legacy derivatives `live` / `live_testnet` launch configs remain in the repo for reference and readonly compatibility, but config-file launch is intentionally blocked for this doctrine.
- Helper scripts:
  - `./scripts/run_kraken_spot_paper.sh`
  - `./scripts/run_kraken_spot_paper_full_analysis.sh`
  - `./scripts/run_kraken_spot_replay_full_analysis.sh`
  - `./scripts/run_kraken_spot_readonly_analysis.sh`
  - `./scripts/run_kraken_spot_tiny_live.sh`
  - `./scripts/run_kraken_spot_profit_full_throttle.sh`
  - `./scripts/run_kraken_ultra_profit_full_throttle.sh`
  - `./scripts/instant_validate_kraken.sh`

## Emergency stop
- Soft stop: run with `--kill`.
- Hard stop file: create `runs/<run_id>/KILL`.
- Emergency flatten supports:
  - full portfolio flatten
  - symbol-only flatten via `flatten --symbol <SYMBOL> --scope symbol`
  - freeze-only mode via `flatten --freeze-only --reason "<reason>"`
- Emergency flatten remains reduce-only and inventory-backed.

## Tiny live first-money checklist
1. Run readonly analysis with real credentials:
   - `bash ./scripts/run_kraken_spot_readonly_analysis.sh`
2. Validate readiness artifacts in `runs/<run_id>/`:
   - `tiny_live_readiness_report.json`
   - `safety_preflight_live_target.json`
   - `rollback_preflight_liveprofit_paper.json`
   - `tiny_live_envelope_summary.json`
   - `live_operator_start_procedure.json`
3. Confirm:
   - `tiny_live_readiness_report.json["ready"] == true`
   - `safety_preflight_live_target.json["ready"] == true`
   - `rollback_preflight_liveprofit_paper.json["ready"] == true`
4. Start tiny live:
   - `ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true bash ./scripts/run_kraken_spot_tiny_live.sh`
5. Promote to `limited_live` only after reconciliation, throughput diagnostics, and execution truth remain clean.

## Monitoring (Grafana)
- drawdown (`drawdown`)
- exposure (`exposure_notional`)
- reject count (`orders_rejected_total`)
- ws disconnect storm (`ws_disconnects_5m`)
- reconciliation mismatch (`reconciliation_mismatch_total`)
- execution cost (`cost_total_bps`)

## Offline deterministic workflow
```bash
make up
make init
make paper
python3 -m pytest -q
```

## CI
- Standalone workflow template:
  - `docs/ci_templates/kraken_spot_doctrine_prelive_audit.workflow.yml.template`
- Place it later at:
  - `.github/workflows/kraken_spot_doctrine_prelive_audit.yml`
- Gates:
  - `pytest -q`
  - tracked-file secret signature scan
  - `python -m py_compile $(find src -name '*.py' -print)`
  - `./scripts/validate_config_matrix.py`
  - `./scripts/validate_deployment_syntax.py`
  - `./scripts/run_contradiction_audit.py`

## Quickstart (macOS)
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
python3 -m pip install pytest
python3 -m pytest -q

# paper (offline deterministic)
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.kraken_spot.paper.yaml

# live readonly preflight / preview (no order placement)
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml
```

If `python` command does not exist on macOS, use `python3` everywhere (all commands above already do).

If you need Python 3.12+ and Homebrew install fails, install Python directly from `python.org` and rerun the same `python3 ...` commands.

## Amateur runbook (safe rollout + emergency)
```bash
# 1) Kraken SPOT paper / replay / readonly analysis
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.kraken_spot.paper_full_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot replay-report --config config.kraken_spot.replay_full_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml

# 2) doctrine-safe Kraken SPOT launch gates
ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
KRAKEN_SPOT_API_KEY=... KRAKEN_SPOT_API_SECRET=... \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml

# 3) limited live
ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
KRAKEN_SPOT_API_KEY=... KRAKEN_SPOT_API_SECRET=... \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live.yaml

# 4) higher-notional profile
ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true ENABLE_FULL_LIVE_STAGE=true \
KRAKEN_SPOT_API_KEY=... KRAKEN_SPOT_API_SECRET=... \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live_profit.yaml

# emergency kill / flatten
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live.yaml --kill
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.kraken_spot.live.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.kraken_spot.live.yaml --freeze-only --reason "operator_freeze"
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.kraken_spot.live.yaml --scope symbol --symbol BTC/USD --reason "symbol_flatten"
```

Rollout stage mapping used by the runtime:
- `paper` -> offline deterministic
- `shadow` -> readonly analytics only; no live order authority
- `tiny_live` -> bounded first-money `kraken_spot` profile on the existing authoritative live path
- `limited_live` -> conservative `kraken_spot` live profile
- `normal_live` -> higher-notional `kraken_spot` live profile

Automatic promotion does not exist. Automatic downgrade does exist when preflight, restart-state confidence, reconciliation, or health checks degrade.

## Security hygiene
- Secrets via env vars only.
- Never commit API keys.
