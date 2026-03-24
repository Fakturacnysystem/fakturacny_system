# Truth Ownership Map

**Last updated:** 2026-03-23

This document defines explicit ownership for critical accounting truth domains.
Ownership is also emitted at runtime in `events_truth.jsonl` as `TRUTH_OWNER_DECLARED`.

Ownership answers "who is the canonical writer for this domain when the venue/runtime supports it."
It does **not** mean the domain is currently available with full confidence on every run.
Current runtime confidence is emitted separately as `TRUTH_CONFIDENCE_SNAPSHOT` in `events_truth.jsonl`
and journaled into `truth_confidence_journal.jsonl` with levels:
- `authoritative`
- `proxy`
- `unavailable`

## Paper mode (`execution.mode=paper`)

| Domain | Owner | Authority | Notes |
|---|---|---|---|
| balance truth | `RobotOrchestrator.paper_equity_model` | `derived` | Synthetic equity model; no exchange cash ledger in paper mode. |
| fill truth | `OMSService.apply_fill (accepted fills only)` | `authoritative` | Only OMS-accepted fills can affect accounting. |
| order truth | `OMSService.orders state machine` | `authoritative` | Explicit lifecycle transitions. |
| position truth | `RobotOrchestrator.paper_exposure_notional` | `derived` | Derived from accepted fills; checked by reconciliation. |
| fee truth | `ExecutionService.execute_paper fill fee model` | `authoritative` | Deterministic fee/slippage model in paper execution. |
| realized PnL truth | `RobotOrchestrator.paper_pnl_formula` | `derived` | Derived from accepted fills, fees, slippage, and funding proxy. |
| unrealized PnL truth | `UNASSIGNED_GAP` | `gap` | No explicit unrealized PnL ledger exists yet. |
| exposure truth | `RobotOrchestrator.paper_exposure_notional` | `derived` | Derived from accepted fills and consumed by risk/recon. |
| risk decision truth | `RiskEngineService.evaluate` | `authoritative` | Risk allow/reject and reason codes are canonical. |
| execution decision truth | `ExecutionService.execute_paper` | `authoritative` | Execution outcomes gate accounting mutations. |
| configuration truth | `RobotSettings.from_file + OpsService.track_config` | `authoritative` | Parsed config plus run hash is canonical for run behavior. |
| environment variable truth | `OS environment (validated by RobotSettings and services)` | `authoritative` | Environment inputs are operator-controlled and validated. |
| runtime mode truth | `RobotSettings.execution_mode_enum` | `authoritative` | Canonical mode selector for paper/live paths. |
| risk mode truth | `RiskEngineService.state.risk_mode` | `authoritative` | Explicit risk posture emitted into risk decisions and health journals. |
| live gating status truth | `RobotSettings.live_gate_status` | `authoritative` | Paper still records live gate status so rollout intent remains explicit. |
| reconciliation status truth | `ReconciliationService.reconcile_report` | `authoritative` | Typed reconciliation outcome is the canonical state-agreement record. |

## Live modes (`execution.mode=live_readonly/live_testnet/live`)

| Domain | Owner | Authority | Notes |
|---|---|---|---|
| balance truth | `<provider>.balances endpoint` | `authoritative` | Exchange balance endpoint is canonical. |
| fill truth | `LiveBinanceService/LiveKrakenService authoritative_fill_history` | `authoritative` | Exchange-native trade history is normalized into local `events_fills.jsonl` with idempotent fill IDs. |
| order truth | `<provider> order status endpoints` | `authoritative` | Exchange order state is canonical. |
| position truth | `<provider>.position_risk endpoint` | `authoritative` | Exchange position state is canonical for reconciliation. |
| fee truth | `exchange-native trade history/account log fee fields` | `authoritative` | Fee fields are ingested from exchange-native history; missing fields force `flatten_only`. |
| realized PnL truth | `LiveBinanceService/LiveKrakenService authoritative_realized_pnl + local fill ledger` | `authoritative` | Realized PnL comes from exchange-native income/account history and is mirrored locally fill-by-fill. |
| unrealized PnL truth | `RobotOrchestrator._live_loop internal mark-to-market` | `derived` | Estimated from internal exposure and mid-price deltas. |
| exposure truth | `<provider>.position_risk endpoint + ReconciliationService` | `authoritative` | Live exposure truth comes from exchange positions plus reconciliation. |
| risk decision truth | `RiskEngineService.evaluate` | `authoritative` | Canonical risk gate before execution. |
| execution decision truth | `LiveBinanceService/LiveKrakenService execute_intent` | `authoritative` | Canonical execution outcome for each live intent. |
| configuration truth | `RobotSettings.from_file + OpsService.track_config` | `authoritative` | Config hash and parsed settings define run behavior. |
| environment variable truth | `OS environment (validated by RobotSettings/connectors)` | `authoritative` | Credential and unlock env vars are validated fail-closed. |
| runtime mode truth | `RobotSettings.execution_mode_enum` | `authoritative` | Canonical mode selector for readonly/testnet/live behavior. |
| risk mode truth | `RiskEngineService.state.risk_mode` | `authoritative` | Explicit risk posture is canonical and is never inferred downstream. |
| live gating status truth | `RobotOrchestrator.boot LIVE_GATE_STATUS event` | `authoritative` | Combines config gate, rollout stage, adapter preflight, and restart confidence. |
| reconciliation status truth | `ReconciliationService.reconcile_live_report` | `authoritative` | Typed outcome drives alert, halt, or halt-and-flatten behavior. |

## Explicit design flaws (current)

- `unrealized_pnl_truth` in paper mode is a declared gap.
- `unrealized_pnl_truth` in live mode is still derived from local mark-to-market, not a venue-native PnL feed.

These gaps are explicitly emitted as `TRUTH_OWNERSHIP_GAP` risk events so they are auditable.

## Current truth confidence owners

| Runtime confidence domain | Decision owner | Persistence owner | Notes |
|---|---|---|---|
| fill truth confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | Derived from exchange-history completeness, duplicate suppression, and gap detection. |
| fee truth confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | Downgrades when exchange-native fee fields are missing or ambiguous. |
| realized PnL confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | `proxy` when only balance-delta inference exists; `unavailable` when neither native nor proxy evidence exists. |
| balance truth confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | Tracks empty/non-positive/fetch-error cases separately from ownership. |
| exposure truth confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | Exchange positions remain the owner of truth; confidence drops when exchange state is unavailable. |
| market-data truth confidence | `LiveStateCoordinator.truth_confidence` | `events_truth.jsonl`, `truth_confidence_journal.jsonl` | Driven by stale feed / degraded market-health evidence. |

## Bounded-context ownership

| Bounded context | Owner of truth | Owner of decisioning | Owner of persistence |
|---|---|---|---|
| market data | exchange market-data endpoints and recorder snapshots | `MarketDataService.assess_health` | raw tables, journals, recorder artifacts |
| policy | forecast/features/regime inputs owned by upstream services | `PolicyService.evaluate_decision` | `policy_journal.jsonl`, order intent events |
| risk | current exposure, balances, and truth confidence from runtime services | `RiskEngineService.evaluate` | risk events, ops metrics |
| execution | exchange order state and native trade history | `ExecutionService.execute_live`, live adapters | order/fill/account events, `fills_journal.jsonl` |
| reconciliation | exchange balances/orders/positions plus local ledgers | `ReconciliationService.reconcile_live_judgment` | reconciliation events, `reconciliation_journal.jsonl` |
| recovery | local run artifacts plus exchange open-order/position state | `LiveStateCoordinator.recover_inflight_state` | `events_recovery.jsonl`, `recovery_journal.jsonl` |
| meta-governor/runtime control | health snapshot, rollout stage, reconciliation outcome, truth confidence | `HealthService.govern`, `LiveControlCoordinator` | `meta_governor_journal.jsonl`, `control_journal.jsonl` |

## Rollout and gate ownership

- Rollout stage truth is derived from `RobotSettings.rollout_stage()`:
  - `paper`
  - `shadow` for `live_readonly`
  - `tiny_live` for `live_testnet`
  - `limited_live` for `live` canary profiles
  - `normal_live` for full `live`
- Live gating truth is emitted as `LIVE_GATE_STATUS` during boot.
- Restart-state confidence is classified as `trusted`, `degraded`, or `insufficient`.
- `insufficient` confidence forces `flatten_only` and blocks new opens.
