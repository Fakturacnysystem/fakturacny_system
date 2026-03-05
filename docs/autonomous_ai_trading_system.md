# Autonomous AI Trading System (Kraken Spot)

This repository now supports a control-plane + execution-plane architecture:

- Deterministic live trading loop remains in the hot path.
- GPT tuning is isolated in a separate script and only writes safe overrides.
- Fatal invariants are always enforced.

## Core Components

- Exchange constraints oracle
  - Service: `src/autonomous_investment_robot/services/exchange_constraints/service.py`
  - Caches constraints in `<run_dir>/exchange_constraints.json`
  - Validates and rounds orders by min notional, base min qty, and precision.
- Inventory-aware spot execution
  - No short selling on spot: SELL only reduces long inventory.
  - Dust handling for non-tradeable tiny amounts.
- Microstructure toxicity scorer
  - Service: `src/autonomous_investment_robot/services/market_microstructure/toxicity.py`
  - Produces `toxicity_score` and drives adaptive throttling/freeze.
- PnL attribution and execution quality
  - Modeled + realized cost metrics (shortfall/slippage/fees/cost-to-alpha).
  - Dashboard + audit events include execution rationale and cost fields.
- Canary/promote/rollback
  - `scripts/run_kraken_spot_canary.sh`
  - `scripts/run_kraken_spot_main.sh`
  - `scripts/promote_canary.py`
  - `scripts/rollback_last_good.py`
- GPT control-plane
  - `scripts/gpt_control_plane.py`
  - Reads artifacts, calls OpenAI Responses API with strict JSON schema, writes safe env overrides.
- Operator UI
  - `apps/operator_ui.py` (Streamlit)
  - Manual overrides, KPI visibility, audit event browsing.

## Security and Secrets

- Never place secrets in code, config files committed to git, or logs.
- Use environment variables only:
  - `KRAKEN_API_KEY`
  - `KRAKEN_API_SECRET`
  - `OPENAI_API_KEY`
- If keys were ever pasted into chat or shell history, rotate them immediately.

### Create OpenAI API Key

1. Open your OpenAI account dashboard and create a new API key.
2. Copy it once and store it in a password manager.
3. Export it only in your shell session:

```bash
export OPENAI_API_KEY="YOUR_KEY_HERE"
```

Do not commit it, print it in logs, or paste it into chat.

## Fatal Invariants (Always Enforced)

- Missing/invalid auth or permissions.
- Invalid symbol mapping/unavailable pair.
- Invalid exchange constraints (min notional/precision/tick).
- Invalid top-of-book (`bid/ask <= 0` or non-finite).
- Idempotency duplicate.
- Hard exchange rate-limit storm / cooldown gate.

## Run GPT Control-Plane

Dry-run (default):

```bash
python3 scripts/gpt_control_plane.py --config config.kraken_spot.live_profit.yaml
```

Apply (write overrides):

```bash
python3 scripts/gpt_control_plane.py --config config.kraken_spot.live_profit.yaml --apply
```

Output files:

- `<run_dir>/gpt_suggestions.json`
- `<run_dir>/env_overrides.sh`

`run_kraken_spot_live.sh`, canary, and main scripts source:

- `<run_dir>/env_overrides.sh`
- `<run_dir>/operator_overrides.sh`

## Canary -> Promote -> Rollback

Start canary:

```bash
scripts/run_kraken_spot_canary.sh
```

Evaluate and promote if KPI gates pass:

```bash
python3 scripts/promote_canary.py --run-dir runs/kraken_spot_live
```

Rollback to last known-good overrides:

```bash
python3 scripts/rollback_last_good.py --run-dir runs/kraken_spot_live
```

## Operator UI

```bash
streamlit run apps/operator_ui.py
```

UI lets operator adjust safe parameters (e.g. max orders/min, edge threshold, growth fraction), pause new entries, and inspect recent audit events.
