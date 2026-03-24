# Autonomous Investment Robot (Perps Intraday)

Offline-deterministic paper/replay robot with fail-closed Binance USD-M live execution path.

## Safety invariants (hard fail-closed)
- Live order placement is blocked unless both env flags are true:
  - `ENABLE_LIVE_TRADING=true`
  - `ACK_I_UNDERSTAND_RISKS=true`
- Live order placement is blocked unless:
  - `provider_whitelist` includes `binance_um_perps`
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

## Profiles
- Paper baseline: `config.paper.yaml`
- Paper perps intraday: `config.perps_intraday.paper.yaml`
- Live readonly (no order placement): `config.perps_intraday.live_readonly.yaml`
- Testnet tiny risk: `config.perps_intraday.testnet.yaml`
- Live canary: `config.perps_intraday.live_canary.yaml`
- Live full strict: `config.perps_intraday.live.yaml`
- Kraken derivatives live readonly (scaffold): `config.kraken_derivatives.live_readonly.yaml`
- Kraken derivatives testnet (signed adapter implemented; validate with small size first): `config.kraken_derivatives.testnet.yaml`
- Kraken derivatives live canary (signed adapter implemented; keep strict limits): `config.kraken_derivatives.live_canary.yaml`
- Kraken derivatives live full (signed adapter implemented; use only after canary stability): `config.kraken_derivatives.live.yaml`

## Binance setup (step-by-step)
1. Create Binance Futures API key:
- Futures enabled.
- Withdrawals disabled.
- IP allowlist strongly recommended.

2. Configure `.env`:
```bash
EXCHANGE_API_KEY=...
EXCHANGE_API_SECRET=...
ENABLE_LIVE_TRADING=false
ACK_I_UNDERSTAND_RISKS=false
TESTNET_VALIDATED=false
```

3. Rollout path (must be sequential):
1. `live-readonly` for 24-72h with recordings.
2. `live_testnet` for 3-7 days with tiny notionals.
3. `live_canary` for 1-2 weeks at 1-5% risk.
4. `live` full strict after stability.

## Create a new local environment
```bash
make env
source .venv/bin/activate
```

`make env` creates `.venv` and creates `.env` from `.env.example` if missing. Install dependencies afterwards with `pip install -e .`.

## Commands
```bash
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.perps_intraday.paper.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.perps_intraday.live_readonly.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.testnet.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.live_canary.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.live.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot record --config config.perps_intraday.live_readonly.yaml --duration-seconds 60
PYTHONPATH=src python3 -m autonomous_investment_robot replay --config config.perps_intraday.live_readonly.yaml --source recordings
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.perps_intraday.live.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot ack-review --run-dir runs/<run_id> --reviewer ops --notes "manual review approved"
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_derivatives.live_readonly.yaml
```

## Kraken (EEA-friendly alternative) integration status
- `live-readonly` preflight path is supported via Kraken derivatives provider (`kraken_derivatives`).
- Core signed REST execution path is implemented for Kraken futures v3 endpoints (`sendorder`, `cancelorder`, `orders/status`, `openorders`, `openpositions`) with fail-closed safety guards in `LiveKrakenService`.
- `record` is currently implemented only for Binance USDT-M market recorder; Kraken recording path is not yet implemented and fails closed.
- Exchange response schemas can vary by account/entity; run `testnet -> canary` first and verify order/position reconciliation before any live usage.
- Helper scripts:
  - `./scripts/run_kraken_live_readonly.sh`
  - `./scripts/run_kraken_testnet.sh`
  - `./scripts/run_kraken_live_canary.sh`
  - `./scripts/run_kraken_live.sh`
  - `./scripts/instant_validate_kraken.sh` (pytest + readonly smoke)

## Emergency stop
- Soft stop: run with `--kill`.
- Hard stop file: create `runs/<run_id>/KILL`.
- Emergency flatten path uses reduce-only market close (if enabled in config).

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
- GitHub Actions workflow: `.github/workflows/ci.yml`
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
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.perps_intraday.paper.yaml

# live readonly preflight / preview (no order placement)
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.perps_intraday.live_readonly.yaml
```

If `python` command does not exist on macOS, use `python3` everywhere (all commands above already do).

If you need Python 3.12+ and Homebrew install fails, install Python directly from `python.org` and rerun the same `python3 ...` commands.

## Amateur runbook (safe rollout + emergency)
```bash
# 1) live-readonly (24-72h) + short recording sample
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.perps_intraday.live_readonly.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot record --config config.perps_intraday.live_readonly.yaml --duration-seconds 60

# 2) replay recorded market data offline
PYTHONPATH=src python3 -m autonomous_investment_robot replay --config config.perps_intraday.live_readonly.yaml --source recordings

# 3) testnet (opt-in real exchange interaction)
RUN_TESTNET=1 PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.testnet.yaml

# 4) canary (strict limits)
TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.live_canary.yaml

# 5) full live (after canary stability)
TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.live.yaml

# emergency kill / flatten
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.perps_intraday.live.yaml --kill
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.perps_intraday.live.yaml
```

Rollout stage mapping used by the runtime:
- `paper` -> offline deterministic
- `shadow` -> `live_readonly`
- `tiny_live` -> `live_testnet`
- `canary_live` -> additive alias for a canary-style `live` profile
- `limited_live` -> `live` canary profile
- `normal_live` -> full `live`

Automatic promotion does not exist. Automatic downgrade does exist when preflight, restart-state confidence, reconciliation, or health checks degrade.

## Security hygiene
- Secrets via env vars only.
- Never commit API keys.
