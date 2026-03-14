# Causal Market Twin Architecture

## Purpose
`CausalMarketTwinEngine` adds a live causal and counterfactual layer to the runtime decision system.  
It does not replace guardrails. It improves trade selection and timing inside existing safety bounds.

## Runtime Placement

Primary path:
1. `RobotOrchestrator` builds `DecisionContext` per symbol/tick.
2. `AutonomousMarketPredictionAndDecisionEngine.run_decision_algorithm()` computes:
   - multimodal fused features
   - probabilistic forecasts
   - uncertainty/conformal/drift state
3. `CausalMarketTwinEngine.evaluate()` builds a `MarketTwinSnapshot`.
4. Best scenario feeds back into decision arbitration:
   - entry/skip gating
   - route preference (`maker`/`taker`)
   - bounded sizing scale
   - optional exit override (`partial_close`/`full_close`)
5. Snapshot and diagnostics are persisted to in-memory model state and decision diagnostics.

## Engine Components

- `RealityStateBuilder`
  - normalizes the live market state (`build_market_twin_state`).
- `CausalDriverEstimator`
  - estimates and scores likely active market drivers.
- `PathForecastEngine`
  - path-aware risk profile:
    - interim drawdown risk
    - false-breakout risk
    - signal-decay risk
- `ExecutionTwinEngine`
  - execution path estimates:
    - fill probability
    - adverse selection risk
    - execution path cost
- `CounterfactualScenarioEngine`
  - simulates alternatives:
    - `enter_market`
    - `enter_limit`
    - `wait_one_cadence`
    - `skip`
    - optional advanced scenarios (`scale_in_entry`, position exits)
- `DecisionArbitrationEngine`
  - ranks and selects scenario utility under a minimum net-edge floor.

## MVP: Counterfactual Entry Engine

The MVP is runtime-active and required four-way entry simulation is implemented:
- market entry now
- limit entry now
- wait one cadence
- skip

Each scenario includes:
- expected net edge after modeled costs
- fill probability
- slippage risk
- adverse move risk
- confidence decay risk
- expected path quality

## Safety Model

The twin influences decisioning but cannot bypass hard invariants:
- never sell below entry/cost basis
- never sell below hard net-profit floor
- no bypass of drawdown/exposure/fatal guardrails

## Diagnostics and Persistence

Structured outputs:
- `DecisionOutcome.diagnostics["market_twin"]`
- in-memory bounded history:
  - `model_state["market_twin_latest"]`
  - `model_state["market_twin_snapshots"]`

Audit-facing fields include:
- primary driver + causal confidence
- winning scenario + action
- top ranked scenarios
- scenario count
