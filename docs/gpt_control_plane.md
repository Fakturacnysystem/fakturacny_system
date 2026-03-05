# GPT Control Plane

This project includes a separate control-plane script for GPT-assisted tuning:

- Script: `scripts/gpt_control_plane.py`
- Inputs: `audit.log`, `dashboard_snapshot.json`, `event_bus.jsonl`
- Outputs (with `--apply`): `gpt_suggestions.json`, `env_overrides.sh` in the run directory

The control plane is **not** in the hot execution path. Trading logic remains deterministic inside the live bot.

## Safety Policy

GPT overrides are filtered by an allowlist. Allowed override keys:

- `AUTONOMOUS_MIN_NET_EDGE_BPS`
- `AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO`
- `AUTONOMOUS_MAX_ORDERS_PER_MIN`
- `AUTONOMOUS_RATE_LIMIT_COOLDOWN_S`
- `AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S`
- `AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE`
- `AUTONOMOUS_GROWTH_MAX_FRACTION`
- `AUTONOMOUS_SELF_TUNER_MIN_SAMPLES`
- `AUTONOMOUS_SELF_TUNER_EVERY_STEPS`
- `AUTONOMOUS_CANARY_FRACTION`
- `AUTONOMOUS_PROMOTED_FRACTION`

The control plane blocks attempts to disable kill-switch/min-notional/rate-limit protection.  
Universe suggestions are filtered to top-liquidity symbols if `symbols_trade_candidates.txt` / `symbols_watch_1000.txt` exist in `run_dir`.

## 1) Set `OPENAI_API_KEY`

```bash
export OPENAI_API_KEY="your_key_here"
```

Optional model override:

```bash
export OPENAI_MODEL="gpt-5.2"
```

## 2) Run control plane

Dry-run (default, prints JSON only):

```bash
python3 scripts/gpt_control_plane.py --config config.kraken_spot.live_profit.yaml
```

Apply suggestions (writes files into run directory):

```bash
python3 scripts/gpt_control_plane.py --config config.kraken_spot.live_profit.yaml --apply
```

## 3) Live script integration

`scripts/run_kraken_spot_live.sh` now auto-loads `${RUN_DIR}/env_overrides.sh` (if present) using `set -a`/`set +a`. This lets GPT suggestions tune env values without editing tracked run scripts.
