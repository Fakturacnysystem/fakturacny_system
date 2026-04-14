# Module Value Map

This repo now emits module-level value artifacts through:

- `module_value_summary.json`
- `module_latency_budget_report.json`
- `module_redundancy_report.json`
- `module_opportunity_cost_report.json`

Authoritative live inputs:

- `decision_doctrine`
- `trade_admission`
- `capital_sovereignty`
- bounded `opportunity_scheduler` when the live loop is flat and there are no open orders

Advisory or telemetry-first layers:

- `mastermind`
- `event_intelligence`
- `synthetic_affect`
- `execution_simulation`
- `spre`
- `shadow_rival`

Current emitted value fields:

- invocation count
- influence count
- veto count
- action
- reasons
- authoritative/advisory role
- backlog pressure
- false-negative rate
- primary veto
- per-stage latency totals

The runtime should use this file as the truth map for operator review, not as evidence of PnL contribution by itself. Economic value still requires realized trade evidence.
