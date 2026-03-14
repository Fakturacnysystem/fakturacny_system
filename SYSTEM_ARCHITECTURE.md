# System Architecture

## Core Runtime Pipeline

1. `MarketDataEngine`:
- ingestion and quote snapshots (`services/data_ingestion`, `services/market_watch`)

2. `FeatureEngine`:
- feature extraction and quality checks (`services/feature_store`, `services/data_qa`)

3. `MarketStateEstimator` + `RegimeDetectionEngine`:
- market-state, regime, nowcasting and confidence context (`services/autonomous_decision/engine.py`)

4. `SignalEngine` + `ProbabilisticForecastEngine`:
- alpha/signal generation, probabilistic return-volatility-risk distributions

5. `UncertaintyQuantificationEngine` + `ConformalPredictionEngine`:
- uncertainty and calibrated intervals for decision gating

6. `ConceptDriftDetectionEngine` + `OnlineAdaptationEngine`:
- drift checks and bounded adaptation hooks

7. `StrategyRankingEngine` + `MetaStrategyAllocator`:
- opportunity scoring and strategy-level allocation

8. `RiskEngine` + `PortfolioEngine`:
- hard limits, drawdown/exposure/cooldown guards, portfolio constraints

9. `ExecutionEngine` + `SmartOrderRouter` + `SlippageEstimator`:
- execution preparation and safe routing under liquidity/latency/cost constraints

10. `AuditTrailEngine` + `TelemetryEngine` + `HealthMonitor`:
- audit events, dashboard metrics, runtime health checks

## Distributed Topology

- Live node:
  - `cli.run` + `cli.worker`
  - execution-critical loop only
  - watchdog/mastermind/harmony/audit

- Compute node:
  - `cli.compute_node`
  - distributed heavy scan/forecast/optimize workers

- Shared infra:
  - Redis Streams (`autobot.tasks.*`, `autobot.results.*`, `autobot.events.audit`)
  - optional Postgres mirror sink for snapshots

## Safety and Live Gate

- Hard invariant protections are enforced in orchestrator and live execution services.
- Live mode requires manual gate:
  - `AUTONOMOUS_LIVE_GO=1`
  - confirmation artifact file (default `ops/live_operator_confirmation.txt`)
- Default startup path is paper-safe unless explicit manual gate is satisfied.

