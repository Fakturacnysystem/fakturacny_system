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
