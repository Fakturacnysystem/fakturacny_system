# Trade Admission Model

`PolicyService.evaluate_decision()` now computes an authoritative `trade_admission` payload before the final live decision path.

Code path:

- `src/autonomous_investment_robot/services/policy/service.py`
- `_trade_admission_assessment()`

Current inputs:

- forecast confidence
- expected edge and cost
- execution quality when present
- portfolio allocation when present
- profitability/inventory pressure when present
- event risk when present
- provider lifecycle completeness when present

Current outputs:

- `floor_reach_probability`
- `floor_compatibility_score`
- `expected_mae_bps`
- `expected_mfe_bps`
- `expected_time_to_floor_minutes`
- `expected_realized_net_edge_bps`
- `capital_lock_cost_score`
- `signal_decay_risk`
- `expected_utility_score`
- `execution_survivability_score`
- `edge_per_time_score`
- `recommended_execution_style`
- `recommended_action`
- explicit `rationale`

Authority boundary:

- Missing evidence is treated as partial, not automatically negative.
- The admission layer can block economically weak setups or downsize/probe valid-but-weak setups.
- It cannot bypass doctrine, risk, truth, or sell guards.

Artifacts:

- `trade_admission_journal.jsonl`
- `trade_admission_summary.jsonl`
- `admission_feature_snapshot.jsonl`
- `opportunity_cost_journal.jsonl`
- `floor_compatibility_summary.jsonl`
