# Autonomous Investment Robot (Perps Intraday Paper, Safe-First)

Offline, deterministic autonomous crypto robot scaffold for intraday + perpetual futures paper trading.

## Safety invariants (hard)
- Safe-mode default.
- Missing/`UNSPECIFIED` critical limits => fail-closed no-trade.
- Integrity kill paths (stale/divergence/reconciliation) => stop + safe mode + flatten (paper).
- Live is hard-locked unless ALL are true: `ENABLE_LIVE_TRADING=true`, `ACK_I_UNDERSTAND_RISKS=true`, `CANARY_MODE=true`, and all required limits set.

## Quickstart (offline)
```bash
make up
make init
make paper
```

## Paper profiles
- Baseline: `config.paper.yaml`
- Perps intraday: `config.perps_intraday.paper.yaml`

Run:
```bash
PYTHONPATH=src python scripts/run_paper.py --config config.perps_intraday.paper.yaml
PYTHONPATH=src python -m autonomous_investment_robot replay --config config.perps_intraday.paper.yaml --source fixtures
```

## What is implemented
- Strategy ensemble plugins (trend, mean-reversion, carry stub) + regime controller (TREND/RANGE/PANIC, GOOD/THIN).
- Bandit allocator with decay, cooldown, fatal-loss kill, max strategy weight.
- Cost-aware policy (TCO gate: fees + slippage + funding + spread component).
- Execution v2: anti-toxic filter, participation cap, slicing (POV/TWAP-like), partial fills.
- Risk v2: perps constraints (funding/OI/liquidations/margin buffer/divergence), DD throttle, CVaR approx, flatten triggers.
- Deterministic append-only event log with checksum/idempotency.
- Incident policy engine + notifier stub.
- MLOps stubs: registry, drift detector, canary/rollback trigger logic.

## Monitoring
- Prometheus: `infra/prometheus.yml`
- Alerts: `infra/alerts/alerts.yml`
- Grafana dashboard: `infra/grafana/dashboards/autobot.json`

## Incident automation mapping
- DataStale -> safe_mode
- RejectStorm -> cooldown
- ReconciliationMismatch -> flatten
- HighSlippage -> reduce_size

## Outputs
`runs/*` include:
- `order_plans.json`, `fills.json`, `report.json`, `checksums.json`
- `events_*.jsonl` (append-only)
- `metrics.prom`
- `audit.log`, `config_history.jsonl`

## Security hygiene
- Secrets via env vars only.
- Never commit API keys.


## Metrics exported
- pnl, drawdown, exposure_notional
- fees_paid, funding_paid, slippage_bps
- allocator_weight_*
- compliance_veto_state, kill_switch_state, reconciliation_mismatch_total
