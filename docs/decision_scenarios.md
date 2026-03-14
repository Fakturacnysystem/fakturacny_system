# Decision Scenarios (Causal Market Twin)

## Scenario Set

Core entry scenarios (always generated):
- `entry_now_market`
- `entry_now_limit`
- `wait_one_cadence`
- `skip`

Advanced scenario (configurable):
- `scale_in_entry`

Position-aware scenarios (only when position exists):
- `partial_exit`
- `full_exit`

## Per-Scenario Metrics

Every `DecisionScenario` carries:
- `expected_net_edge_bps`
- `fill_probability`
- `slippage_risk_bps`
- `adverse_move_risk_bps`
- `expected_confidence_decay`
- `expected_path_quality`
- `path_risk`:
  - interim drawdown
  - false breakout
  - signal decay
  - adverse move
- `execution`:
  - order type
  - fill probability
  - adverse selection risk
  - path cost bps
  - latency sensitivity

## Ranking and Selection

`DecisionArbitrationEngine` ranks scenarios by utility:
- rewards:
  - net edge
  - path quality
- penalties:
  - drawdown/false-breakout/signal-decay risk
  - adverse selection risk
  - confidence decay

`choose_best_counterfactual_action()` then applies floor logic:
- if best entry scenario has net edge below `min_counterfactual_edge_bps`,
  fallback preference becomes `skip` or `wait_one_cadence`.

## Runtime Effects

Selected scenario can influence:
- entry blocking (`counterfactual_no_edge`, `counterfactual_wait_preferred`)
- route preference (`maker` vs `taker`)
- sizing scale (bounded)
- exit override for active positions (`partial_close` / `full_close`)

This effect is bounded by existing risk/execution/profit-lock invariants.

## Mission Bridge Advisory (Phase 14)

Mission diagnostics from the additive shadow `UniverseMind` path are bridged into orchestrator decision telemetry as non-authoritative advisory fields:
- `mission`
- `reason_codes`
- `no_trade_preferred`
- `allow_new_risk`
- `execution_posture_hint`

Runtime usage:
- incident policy can emit `MissionNoTradeAdvisory` as `no_open_until_stable`
- mastermind policy records mission advisory in `intent.why.mastermind.mission_advisory`

Safety precedence rule:
- mission bridge does not override hard incident actions (`kill_*`, `hard_stop`, observe-only safety flows)
- legacy orchestrator remains execution authority
