# Causal Market Twin Runbook

## Scope
Operational runbook for `CausalMarketTwinEngine` and the counterfactual entry MVP.

## Config Knobs

Configured under `autonomous` and/or env overrides:
- `counterfactual_min_edge_bps`
- `market_twin_include_advanced_scenarios`
- `market_twin_max_snapshots`

Env form:
- `AUTONOMOUS_COUNTERFACTUAL_MIN_EDGE_BPS`
- `AUTONOMOUS_MARKET_TWIN_INCLUDE_ADVANCED_SCENARIOS`
- `AUTONOMOUS_MARKET_TWIN_MAX_SNAPSHOTS`

## Runtime Wiring Check

1. Start safe path:
```bash
bash /Users/martinholik/Projects/fakturacny_system/scripts/run_paper.sh
```

2. Validate diagnostics:
- inspect `decision_brain_tick` events in audit log
- confirm `market_twin_*` fields are populated
- verify `DecisionOutcome.diagnostics.market_twin` exists in decision snapshots
- verify world-state adapter diagnostics are present:
  - `world_state_source`
  - `world_state_available`
  - `world_state_graph_available`
  - `world_state_safe_to_trade`
  - `world_state_stale_critical_domains`

3. Validate bounded snapshot persistence:
- `model_state.market_twin_latest`
- `model_state.market_twin_snapshots` does not exceed configured max.

## Validation Commands

```bash
python3 -m py_compile \
  /Users/martinholik/Projects/fakturacny_system/src/autonomous_investment_robot/services/autonomous_decision/causal_market_twin.py \
  /Users/martinholik/Projects/fakturacny_system/src/autonomous_investment_robot/services/autonomous_decision/engine.py \
  /Users/martinholik/Projects/fakturacny_system/src/autonomous_investment_robot/core/orchestrator.py \
  /Users/martinholik/Projects/fakturacny_system/src/autonomous_investment_robot/config/settings.py \
  /Users/martinholik/Projects/fakturacny_system/tests/test_causal_market_twin_engine.py
```

```bash
pytest -q \
  /Users/martinholik/Projects/fakturacny_system/tests/test_causal_market_twin_engine.py \
  /Users/martinholik/Projects/fakturacny_system/tests/test_autonomous_decision_engine.py
```

```bash
pytest -q
```

## Failure Handling

- If market twin evaluation fails:
  - runtime falls back to base decision logic
  - `market_twin_error` is populated in diagnostics
  - hard risk/profit invariants remain active

- If no scenarios are valid:
  - arbitration falls back to `skip` path.

## Data Limitations

The causal layer is probabilistic and heuristic by design:
- no claim of perfect causal certainty
- optional data (news/macro/fundamentals/sentiment) is used only when present
- no fabricated external inputs
