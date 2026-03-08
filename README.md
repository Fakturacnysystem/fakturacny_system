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

## Profiles
- Paper baseline: `config.paper.yaml`
- Paper perps intraday: `config.perps_intraday.paper.yaml`
- Live readonly (no order placement): `config.perps_intraday.live_readonly.yaml`
- Testnet tiny risk: `config.perps_intraday.testnet.yaml`
- Live canary: `config.perps_intraday.live_canary.yaml`
- Live full strict: `config.perps_intraday.live.yaml`

## Kraken setup (step-by-step, private bot model)
1. Create Kraken API key:
- Trading enabled.
- Withdrawals disabled.
- IP allowlist strongly recommended.

### Credential model for private bot operation
- This project is documented for a **private bot running on your own exchange account**.
- You only need standard exchange API credentials for signing requests:
  - `EXCHANGE_API_KEY`
  - `EXCHANGE_API_SECRET`
- Optional extra secret (passphrase) is exchange-specific and only used when a provider requires it.
- You do **not** need OAuth app credentials (`client_id`, `client_secret`) or a separate developer authorization key for this deployment model.

### Required capability envelope (autonomous but fail-closed)
- Data plane: market data ingest + internal feature/analysis pipeline.
- Decision plane: strategy signal + risk-gated decisioning.
- Action plane: order placement/cancel + position management (including emergency flatten).
- Control plane: reconciliation, reporting, and WHY/audit logs.
- Safety profile: conservative, stability-first; risk controls override alpha at all times.

### Minimum exchange permissions
- Enable only what is required: read + trading (order placement/cancel and balance/position reads).
- Keep withdrawals disabled permanently.
- Use IP whitelist whenever the exchange supports it.
- If required permissions are missing/uncertain, the runtime defaults to no-trade/fail-closed behavior.

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
```

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

## Security hygiene
- Secrets via env vars only.
- Never commit API keys.

## Kraken Spot runbook (private bot, no OAuth)
- Credentials: `KRAKEN_API_KEY` + `KRAKEN_API_SECRET` only.
- Do not use developer OAuth/app keys for this private-account bot deployment.
- Required permissions: funds read + trading. Keep withdrawals disabled.
- Prefer IP allowlist.

### Rollout steps
```bash
# 1) preflight readonly
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_spot.live_readonly.yaml

# 2) record 60s market sample
PYTHONPATH=src python3 -m autonomous_investment_robot record --config config.kraken_spot.live_readonly.yaml --duration-seconds 60

# 3) replay recordings offline (must return events>0)
PYTHONPATH=src python3 -m autonomous_investment_robot replay --config config.kraken_spot.live_readonly.yaml --source recordings

# 4) canary
TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live_canary.yaml

# 5) full live
TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live.yaml

# emergency
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live.yaml --kill
PYTHONPATH=src python3 -m autonomous_investment_robot flatten --config config.kraken_spot.live.yaml
```

## Nonstop watchdog runner (Kraken)
- Core close-profit rule is enforced by `ProfitGate` with hard floor `AUTONOMOUS_PROFIT_TARGET_NET >= 0.02`.
- This does not guarantee total account profit. Positions can remain open for long periods; funding/interest/fees can still reduce equity.
- `HealthAudit110` runs every 10 minutes by default (`health_audit_110.interval_s: 600`) and auto-repairs in escalation order:
  - soft repair: reconnect/refresh caches/subsystems
  - hard repair: cancel stale open orders + full reconcile + state snapshot
  - full restart request (watchdog restart), still without forced loss-close
- Multi-venue Kraken live path now routes by discovered instrument type:
  - spot/margin symbols -> `LiveKrakenSpotService`
  - perpetual symbols (including optional xStocks/ETF-style perp symbols if present) -> `LiveKrakenFuturesService`
- For perps execution set futures keys in env: `KRAKEN_FUTURES_KEY`, `KRAKEN_FUTURES_SECRET`.
- Use the watchdog runner for 24/7 self-healing restarts:

```bash
# nonstop supervised live loop
python3 -m cli.run --config config.kraken_spot.live_profit.yaml --nonstop

# status snapshot (orders, submissions, positions)
python3 -m cli.status --config config.kraken_spot.live_profit.yaml

# watchdog health (heartbeat + stall checks)
python3 -m cli.health --config config.kraken_spot.live_profit.yaml

# explicit 110% audit check (with safe repair actions, no forced loss-closes)
python3 -m cli.audit110 --config config.kraken_spot.live_profit.yaml --once

# optional OpenAI-assisted self-improvement report (never sends orders, never edits code)
python3 -m cli.self_improve --config config.kraken_spot.live_profit.yaml --last 24

# paper mode
python3 -m cli.paper --config config.kraken_spot.paper.yaml
```

- Default live script uses watchdog now:
  - `scripts/run_kraken_spot_live.sh`
  - `scripts/run_kraken_spot_main.sh`
- If `OPENAI_API_KEY` is missing, startup prints:
  - `OpenAI self-improvement is disabled because OPENAI_API_KEY is missing. Why are you not using OpenAI API keys for self-improvement? If you want it enabled, set OPENAI_API_KEY and restart.`

### Safety defaults
- Default operation should be paper first.
- Live should be explicitly armed by environment:
  - `LIVE_TRADING=true`
  - `KRAKEN_API_KEY=...`
  - `KRAKEN_API_SECRET=...`
- Helper scripts:
  - `scripts/run_paper.sh [config]`
  - `scripts/run_live.sh [config]`
  - `scripts/healthcheck.sh [config]`

### Profit-lock hardening + profit-upgrade envs
- Core sell lock (never close below +2% net after full costs):
  - `AUTONOMOUS_PROFIT_TARGET_NET=0.02`
  - `AUTONOMOUS_ENTRY_FEE_BPS=30.0`
  - `AUTONOMOUS_EXIT_FEE_BPS=30.0`
  - `AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS=15.0`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_ENABLED=true`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_PCTL=0.95`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_MIN_BPS=10.0`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_MAX_BPS=60.0`
  - `AUTONOMOUS_SPOT_SELL_PROFIT_LOCK=true`
  - `AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS=200`
  - `AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS=200` (or higher)
  - `AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS=false`
  - `AUTONOMOUS_SPOT_SELL_LIMIT_ONLY=true`
  - `AUTONOMOUS_SPOT_SELL_POST_ONLY=true`
  - `AUTONOMOUS_SPOT_SELL_POST_ONLY_RETRY_TICKS=3`
- Stale-data sell hard block:
  - `AUTONOMOUS_STALE_SELL_BLOCK=true`
  - `AUTONOMOUS_SAFE_MODE_BLOCK_STALE_BUY=true`
  - `AUTONOMOUS_BLOCK_BUY_ON_STALE_IN_SAFE_MODE=true`
- Nonstop auto-recover (no panic close):
  - `AUTONOMOUS_AUTO_RECOVER_KILL=true`
  - `AUTONOMOUS_AUTO_RECOVER_KILL_MIN_COOLDOWN_S=300`
  - `AUTONOMOUS_HEALTH_AUDIT110_ENABLED=true`
  - `AUTONOMOUS_HEALTH_AUDIT110_INTERVAL_S=600`
- Entry ladder (maker-first edge improvement):
  - `AUTONOMOUS_ENTRY_LADDER_ENABLED=true`
  - `AUTONOMOUS_ENTRY_LADDER_STEPS=5`
  - `AUTONOMOUS_ENTRY_LADDER_MAX_BPS=25`
  - `AUTONOMOUS_ENTRY_LADDER_MIN_STEP_BPS=3`
  - `AUTONOMOUS_ENTRY_LADDER_MIN_NOTIONAL=250`
  - `AUTONOMOUS_ENTRY_LADDER_ORDER_TTL_S=120`
  - `AUTONOMOUS_ENTRY_LADDER_REFRESH_S=10`
  - `AUTONOMOUS_ENTRY_MAKER_ONLY=true`
- Exit repricing:
  - `AUTONOMOUS_EXIT_REPRICE_INTERVAL_S=30`
  - `AUTONOMOUS_EXIT_MAX_ORDER_AGE_S=1800`
  - `AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS=2`
  - `AUTONOMOUS_EXIT_POST_ONLY=true`
  - `AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S=10`
  - `AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN=20`
  - `AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN=5`
  - `AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL=50`
  - `AUTONOMOUS_MAX_OPEN_ORDERS_PER_SYMBOL=5`
- Volatility regime adaption:
  - `AUTONOMOUS_VOL_REGIME_ENABLED=true`
  - `AUTONOMOUS_REGIME_ENABLED=true`
  - `AUTONOMOUS_VOL_HIGH_Z=2.0`
  - `AUTONOMOUS_VOL_HIGH_THRESHOLD=0.0015`
  - `AUTONOMOUS_VOL_LOW_THRESHOLD=0.0003`
  - `AUTONOMOUS_VOL_HIGH_NOTIONAL_SCALE=0.5`
  - `AUTONOMOUS_VOL_HIGH_SLIPPAGE_MULT=1.5`
  - `AUTONOMOUS_VOL_HIGH_LADDER_SPACING_MULT=1.5`
- Microstructure + fee-aware + no-trade zone:
  - `AUTONOMOUS_MICROSTRUCTURE_ENABLED=true`
  - `AUTONOMOUS_MICROSTRUCTURE_MODE=momentum`
  - `AUTONOMOUS_MICROSTRUCTURE_IMBALANCE_THRESHOLD=0.10`
  - `AUTONOMOUS_FEE_AWARE_SIZING=true`
  - `AUTONOMOUS_FEE_AWARE_EDGE_BUFFER_BPS=15`
  - `AUTONOMOUS_NO_TRADE_ZONE_ENABLED=true`
  - `AUTONOMOUS_NO_TRADE_ZONE_SPREAD_BPS=25`
  - `AUTONOMOUS_SPREAD_HIGH_BPS=25`
  - `AUTONOMOUS_NO_TRADE_ZONE_MIN_TOP_QTY=0.01`
  - `AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE=200.0`
- Symbol rotation (top-K liquidity/score):
  - `AUTONOMOUS_SYMBOL_TOPK=20`
  - `AUTONOMOUS_SYMBOL_SCORE_REFRESH_S=15`
  - `AUTONOMOUS_SYMBOL_QUARANTINE_MIN=15`
- Profile preset (high-volatility / more-trades):
  - `AUTONOMOUS_PROFILE=aggressive_hf`
  - Applies profile defaults (unless env override is set):
  - `AUTONOMOUS_SYMBOL_TOPK=60`
  - `AUTONOMOUS_SYMBOL_SCORE_REFRESH_S=5`
  - `AUTONOMOUS_SYMBOL_QUARANTINE_MIN=5`
  - `ORDER_SUBMISSION_INTERVAL_SECONDS=60`
  - `AUTONOMOUS_EXTRA_SUBMISSIONS_ENABLED=true`
  - `AUTONOMOUS_EXTRA_SUBMISSIONS_MAX_PER_MIN=6`
  - `AUTONOMOUS_PROBE_NOTIONAL_QUOTE=1.50`
  - `AUTONOMOUS_PROBE_DISTANCE_TICKS=1`
  - `AUTONOMOUS_ENTRY_LADDER_STEPS=3`
  - `AUTONOMOUS_ENTRY_LADDER_MAX_BPS=10`
  - `AUTONOMOUS_ENTRY_LADDER_REFRESH_S=5`
  - `AUTONOMOUS_ENTRY_LADDER_ORDER_TTL_S=60`
  - `AUTONOMOUS_EXIT_REPRICE_INTERVAL_S=10`
  - `AUTONOMOUS_EXIT_MAX_ORDER_AGE_S=600`
  - `AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS=1`
  - `AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S=3`
  - `AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN=60`
  - `AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL=120`
  - `AUTONOMOUS_MAX_OPEN_ORDERS_PER_SYMBOL=8`
  - `AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN=12`
  - `AUTONOMOUS_SPREAD_HIGH_BPS=40.0`
  - `AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE=120.0`
- Constraints TTL + endpoint rate-limit budgets:
  - `AUTONOMOUS_CONSTRAINTS_TTL_S=1800`
  - `AUTONOMOUS_ENDPOINT_RATE_LIMIT_BUDGET=5`
  - `AUTONOMOUS_ENDPOINT_RATE_LIMIT_WINDOW_S=60`
  - `AUTONOMOUS_ENDPOINT_RETRY_BUDGET=2`
  - `AUTONOMOUS_ENDPOINT_RETRY_BACKOFF_MULT=1.35`
- Runtime adapter services (drop-in):
  - `FeeProfileService` refresh:
  - `AUTONOMOUS_FEE_REFRESH_S=21600`
  - `AUTONOMOUS_FEE_REFRESH_VOLUME_JUMP_RATIO=0.25`
  - `SlippageCalibrator`:
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_PCTL=0.95`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_MIN_BPS=10.0`
  - `AUTONOMOUS_SLIPPAGE_CALIBRATION_MAX_BPS=60.0`
  - `RateLimitGovernor`:
  - `AUTONOMOUS_RATE_LIMIT_GOVERNOR_WINDOW_S=60`
  - `AUTONOMOUS_RATE_LIMIT_GOVERNOR_MAX_EVENTS_60S=12`
  - `AUTONOMOUS_RATE_LIMIT_GOVERNOR_STORM_COOLDOWN_S=120`
  - `AUTONOMOUS_RATE_LIMIT_GOVERNOR_RETRY_BUDGET=2`
  - `WSDataIntegrityGuard`:
  - `AUTONOMOUS_WS_MAX_OUT_OF_ORDER=8`
  - `AUTONOMOUS_WS_TRADE_ID_CACHE=10000`
- Stuck/hedge/churn/validation/mastermind layers:
  - `StuckPositionGovernor`:
  - `AUTONOMOUS_STUCK_GOVERNOR_ENABLED=true`
  - `AUTONOMOUS_STUCK_AGE_S=3600`
  - `AUTONOMOUS_STUCK_DD_TRIGGER=-0.012`
  - `AUTONOMOUS_STUCK_BLOCKED_SELLS_TRIGGER=5`
  - `AUTONOMOUS_STUCK_ENTRIES_PAUSE_MIN_S=900`
  - `HedgeManager` (OPEN hedge tranches only; closes remain ProfitGate-gated):
  - `AUTONOMOUS_HEDGE_ENABLED=true`
  - `AUTONOMOUS_HEDGE_MAX_RATIO=0.80`
  - `AUTONOMOUS_HEDGE_STEP_RATIO=0.20`
  - `AUTONOMOUS_HEDGE_DD_STEP=0.008`
  - `AUTONOMOUS_HEDGE_MIN_NOTIONAL=10.0`
  - `AUTONOMOUS_HEDGE_MAX_NOTIONAL_PER_SYMBOL=200.0`
  - `AUTONOMOUS_HEDGE_CLOSE_PROFIT_NET=0.02`
  - `AUTONOMOUS_HEDGE_FUNDING_WINDOW_S=1200`
  - `OrderChurnController`:
  - `AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN=20`
  - `AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN=5`
  - `AUTONOMOUS_RATE_LIMIT_STORM_COOLDOWN_S=60`
  - `OnlineSignalValidator`:
  - `AUTONOMOUS_ONLINE_VALIDATION_ENABLED=true`
  - `AUTONOMOUS_VALIDATION_WINDOW_TRADES=200`
  - `AUTONOMOUS_VALIDATION_MIN_ALPHA_BPS=-10`
  - `AUTONOMOUS_VALIDATION_MAX_REJECT_RATE=0.35`
  - `AUTONOMOUS_VALIDATION_COOLDOWN_S=3600`
  - `MastermindPolicy`:
  - `AUTONOMOUS_MASTERMIND_ENABLED=true`
  - `AUTONOMOUS_MASTERMIND_MAX_ENTRY_ORDERS_PER_MIN=6`
  - `CapitalUnlockManager`:
  - `AUTONOMOUS_CAPITAL_UNLOCK_ENABLED=true`
  - `AUTONOMOUS_CAPITAL_LOCKED_RATIO_TRIGGER=0.35`
  - `AUTONOMOUS_CAPITAL_MEDIAN_HOLD_S_TRIGGER=7200`
  - `AUTONOMOUS_CAPITAL_STUCK_ENTRY_SCALE=0.20`
  - `AUTONOMOUS_CAPITAL_REDIRECT_TOPK=30`
- Deterministic autotuning persistence:
  - `tuning_state.json` is stored in `run_dir` and reloaded on boot.

### Extended Monitoring + Research Additions
- Dashboard (`Flask`, read-only by default):
  - `python -m cli.run --config config.kraken_spot.live_profit.yaml --paper --dashboard`
  - standalone: `python -m cli.dashboard --config config.kraken_spot.live_profit.yaml`
  - env:
    - `AUTONOMOUS_DASHBOARD_ENABLED=true`
    - `AUTONOMOUS_DASHBOARD_PORT=8080`
  - endpoints:
    - `GET /health`, `GET /status`, `GET /positions`, `GET /pnl`, `GET /metrics`, `GET /audit-events`, `GET /slippage`
    - `GET /config`, `POST /config`, `POST /reload`
  - runtime overrides are stored in `run_dir/override.yaml` and merged into `run_dir/runtime_config.effective.yaml`.
  - see [docs/operator_ui.md](docs/operator_ui.md) and [docs/gpt_control_plane.md](docs/gpt_control_plane.md)

- Decision tick cadence (observability invariant):
  - emits `decision_tick` audit events + reliability bus events every bucket:
    - `AUTONOMOUS_DECISION_TICK_S=60`
    - `AUTONOMOUS_DECISION_PER_SYMBOL=1`
    - `AUTONOMOUS_DECISION_EMIT_TOPIC=intent`
  - dashboard metrics:
    - `decision_tick_total`
    - `decision_tick_skip_total`
    - `decision_tick_last_reason`

- Extended CLI:
  - portfolio backtest: `python -m cli.backtest --config backtest.yaml`
  - replay CSV summary: `python -m cli.replay --file trades.csv`
  - ML skeleton training: `python -m cli.train_model --input features.csv --output model.pkl`
  - SQLite/self-audit summary: `python -m cli.audit --config config.kraken_spot.live_profit.yaml --since 2026-03-01`
  - market/config matrix audit: `python scripts/audit_market_matrix.py --output docs/market_matrix.md`

- Hybrid paper/live symbol mode:
  - `AUTONOMOUS_HYBRID_SYMBOLS=[\"XBTUSD\",\"ETHUSD\"]`
  - listed symbols execute live; others are treated as hybrid-paper execution path.

- Multi-exchange + multi-account scaffolding:
  - `AUTONOMOUS_MULTIPLE_EXCHANGES_ENABLED=false` (default off)
  - account routing: `AUTONOMOUS_ACCOUNT_ROUTING_STRATEGY=round_robin|liquidity_based`
  - optional account keys:
    - `KRKN_API_KEY_MAIN`, `KRKN_API_SECRET_MAIN`
    - `KRKN_API_KEY_SUB1`, `KRKN_API_SECRET_SUB1`, ...

### Safety Notice
- The system does not guarantee profit.
- It enforces close gating: no SELL/CLOSE path is allowed unless ProfitGate certifies at least +2% net after modeled costs.
- Positions may remain open longer; hedging and multi-venue routing add operational complexity and cost.
