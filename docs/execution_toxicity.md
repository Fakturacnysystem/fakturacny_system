# Execution Toxicity

Execution planning remains on the existing authoritative live path. The current upgrade strengthens the planning inputs instead of introducing a parallel executor.

Code paths:

- `src/autonomous_investment_robot/services/execution/service.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
- `src/autonomous_investment_robot/services/cost_model/service.py`

Current behavior:

- admission can force `probe`, `trade_smaller`, `wait`, or `no_trade`
- execution planner now consumes admission execution style, signal decay, floor compatibility, and execution survivability
- high-decay but still-strong setups can choose `marketable_limit`
- weak survivability or non-replaceable venues bias toward passive behavior

Artifacts:

- `execution_toxicity_journal.jsonl`
- `queue_estimation_journal.jsonl`
- `child_order_planner_journal.jsonl`
- `execution_edge_decay_journal.jsonl`
- `realized_vs_forecast_execution_journal.jsonl`
- `fill_survivability_summary.jsonl`

Current limitation:

- there is still no full queue-position model or mature slicing engine
