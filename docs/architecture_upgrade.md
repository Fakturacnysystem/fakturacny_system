# Architecture Upgrade

## Before
- The runtime already had the core loop: ingestion, QA, features, forecast, policy, risk, OMS, execution, reconciliation, metrics, and events.
- The main weakness was concentration of control in `RobotOrchestrator`, with richer semantics embedded in ad hoc dicts instead of explicit boundary contracts.
- Paper replay behavior was deterministic, but runtime explainability, decision structure, and bounded-context separation were limited.

## After
- The orchestrator still preserves the existing entrypoints, but now coordinates explicit service stages:
  - `market_data_service`
  - `regime_service`
  - `alpha_service`
  - `policy`
  - `portfolio_service`
  - `risk_engine`
  - `execution`
  - `reconciliation`
  - `health_service`
  - `learning_service`
  - `observability_service`
- The new domain contract layer in `src/autonomous_investment_robot/core/contracts.py` defines typed payloads for market state, regime, alpha outputs, no-trade decisions, portfolio allocation, execution plans, ledgers, health, and learning records.
- `PolicyService.make_intent()` remains compatible, but is now backed by `evaluate_decision()` so no-trade becomes a first-class structured outcome.
- `RiskEngineService.evaluate()` remains compatible, but now exposes explicit risk modes and accepts additional fail-closed inputs such as balance-state, reject bursts, abnormal latency, slippage drift, and unexplained PnL deviation.
- `ExecutionService` now separates execution planning/quality forecasting from execution itself.
- `forensics_service` now emits structured PnL attribution and loss-autopsy artifacts from fills, fees, slippage, realized PnL, reconciliation context, and truth-confidence context.
- `quantum_state_service` now models heuristic multi-scenario market branches, interference, and collapse-to-action decisions without changing legacy paper replay payloads.
- `edge_immunity_service` now stress-tests a candidate edge across deterministic counterfactual worlds before live policy is allowed to treat the thesis as robust.
- `EventStore` and `PortfolioService` now support local rehydration so boot can classify restart-state confidence before placing new live orders.
- Live boot, restart rehydration, market sensing, decision/risk flow, reconciliation, runtime control, and live result accounting are now delegated into `live_runtime` coordinators instead of staying entirely inline in `RobotOrchestrator`.
- Truth ownership is now separated from truth confidence. Ownership remains fixed per domain, while runtime confidence is emitted as a distinct typed snapshot and influences reconciliation and downgrade policy.

## Runtime flow
1. Market snapshot and market-health assessment are built in `market_data_service`.
2. Forecast and regime assessment are produced separately.
3. Baseline alpha experts produce structured expert outputs.
4. Policy decides trade vs no-trade with explicit reasons.
5. Portfolio allocation produces a recommended budget scalar.
6. Risk decides whether the candidate survives and in which risk mode.
7. Execution produces a plan plus a venue-specific execution result.
8. Reconciliation emits typed severity/action results.
9. Live adapters fetch exchange-native trade history before mutating the local fill/fee/realized-PnL ledger.
10. Health/meta-governor can halt or flatten on degraded runtime state.
11. Forensics writes reconstructable attribution and loss-autopsy artifacts.
12. Learning and observability write reconstructable artifacts.

## Live bounded-context ownership

| Context | Owner of truth | Owner of decisioning | Owner of persistence |
|---|---|---|---|
| market sensing | exchange market-data endpoints | `LiveMarketCoordinator` + `MarketDataService` | journals + raw recorder artifacts |
| trade/no-trade policy | policy inputs from forecast/regime/alpha/portfolio | `PolicyService.evaluate_decision` | `policy_journal.jsonl`, order intent events |
| risk | balances, exposure, truth confidence, market health | `RiskEngineService.evaluate` | risk events + ops metrics |
| execution planning | execution-quality forecast and venue constraints | `ExecutionService.build_execution_plan` | `execution_journal.jsonl` |
| probabilistic scenario modeling | forecast/features/regime/alpha/execution inputs | `QuantumStateService.evaluate` | `quantum_state_journal.jsonl` |
| edge robustness stress-testing | counterfactual world generator + execution fragility heuristics | `EdgeImmunityService.evaluate` | `edge_immunity_journal.jsonl` |
| live execution truth | exchange-native order/fill/fee/realized-PnL endpoints | live adapter + `LiveLedgerCoordinator` | `events_orders.jsonl`, `events_fills.jsonl`, `events_account.jsonl`, `fills_journal.jsonl`, `accounting_truth_journal.jsonl` |
| restart recovery | local artifacts + exchange open orders/positions | `LiveRecoveryCoordinator` / `LiveStateCoordinator.recover_inflight_state` | `events_recovery.jsonl`, `recovery_journal.jsonl` |
| reconciliation | exchange balances/orders/positions + local ledgers | `ReconciliationService.reconcile_live_judgment` via `LiveReconciliationCoordinator` | `reconciliation_journal.jsonl`, truth events |
| runtime control | health/meta-governor state, kill-file, incident policy | `HealthService.govern`, `LiveControlCoordinator` | `meta_governor_journal.jsonl`, `control_journal.jsonl` |
| attribution / loss autopsy | fills, fees, realized PnL, reconciliation and truth-confidence evidence | `ForensicsService.analyze_trade` / `record_runtime_anomaly` | `pnl_attribution.jsonl`, `loss_autopsy.jsonl` |

## Preserved compatibility
- CLI entrypoints and config files remain unchanged.
- Existing imports for `RobotSettings`, `PolicyService`, `RiskEngineService`, `ExecutionService`, `OMSService`, and `ReconciliationService` remain valid.
- Paper replay golden checksums remain unchanged.

## Fully implemented
- Unified typed contracts for the new bounded contexts.
- Structured no-trade decisions and risk modes.
- Execution planning and execution-quality forecasting.
- Local portfolio ledger for accepted paper fills.
- Local live account snapshots and normalized live fill/fee/realized-PnL ledger records from exchange-native history endpoints.
- Journal artifacts for config, signals, policy, execution, reconciliation, health, and learning.
- Journal artifacts for quantum state, edge immunity, PnL attribution, and loss autopsy.
- CI workflow running `pytest -q` plus tracked-file secret scan.
- Restart-safe local state rehydration with downgrade to `flatten_only` when confidence is insufficient.
- Restart rehydration can now backfill missing local fill history from exchange-native trade history before classifying confidence.

## Partially scaffolded
- Exchange-native unrealized-PnL truth; live unrealized PnL is still compared against exchange position marks, not a dedicated exchange PnL ledger.
- Quantum and edge-immunity layers are deterministic/probabilistic heuristics, not trained ML.
- External intelligence layers such as news, on-chain, and cross-exchange context.
- Margin remains explicitly disabled for non-paper modes.

## Invariants added
- Only OMS-accepted fills mutate accounting state.
- No-trade is explicit and reason-coded.
- Live margin stays fail-closed.
- Risk mode is explicit on every risk decision.
- Reconciliation emits severity and action, not only a boolean.
- Live gate truth is explicit and persisted as `LIVE_GATE_STATUS`.
- Missing normalized live fill truth never mutates local exposure by approximation.
- Missing exchange-native fee or realized-PnL fields force `flatten_only` instead of silently downgrading accounting truth.
- Restart with insufficient local state confidence blocks new opens instead of approximating state.
- Rich observability metadata is kept out of legacy paper checksum payloads.
