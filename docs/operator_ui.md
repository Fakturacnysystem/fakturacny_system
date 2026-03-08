# Operator UI

`apps/operator_ui.py` is a Streamlit control-plane view for runtime observability and safe overrides.

## Run

```bash
streamlit run apps/operator_ui.py -- --config config.kraken_spot.live_profit.yaml
```

Or via CLI runtime (dashboard sidecar):

```bash
python -m cli.run --config config.kraken_spot.live_profit.yaml --paper --dashboard
```

## What It Shows

- Latest dashboard snapshot KPIs (`dashboard_snapshot.json`)
- Recent audit events (`audit.log`)
- Recent bus events (`event_bus.jsonl`)
- Current health and watchdog state

## Safe Overrides

UI writes overrides to:

- `runs/<run_dir>/operator_overrides.sh` (shell format for launch scripts)
- `runs/<run_dir>/override.yaml` (dashboard/runtime config override)

Only allowlisted parameters can be changed from UI. Core safety invariants remain locked:

- `AUTONOMOUS_PROFIT_TARGET_NET` cannot be lowered via UI
- Long-only spot and fatal invariants are not editable

## Apply Model

Overrides are applied on worker restart (or reload marker + restart). UI itself does not send orders.
