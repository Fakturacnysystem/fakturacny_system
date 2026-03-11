# UNIVERSE CORE Truth Map And Execution Plan

## Purpose

`UNI-6` is an epic-level program brief, not a single feature ticket. This document turns the Linear import into a repo-side execution map that is honest about the current baseline and explicit about what still needs to be built.

The goal is to let Codex or a human engineer execute the roadmap incrementally without guessing:

- what already exists
- what is only partial
- what new first-class modules are still missing
- which phases depend on earlier work
- how each phase should be validated without weakening current live safety controls

## Implemented Foundation In This Repo

The first executable cut of `UNIVERSE CORE` now exists under:

- `src/autonomous_investment_robot/services/universe_core/events.py`
- `src/autonomous_investment_robot/services/universe_core/state.py`
- `src/autonomous_investment_robot/services/universe_core/mission.py`
- `src/autonomous_investment_robot/services/universe_core/parliament.py`
- `src/autonomous_investment_robot/services/universe_core/execution.py`
- `src/autonomous_investment_robot/services/universe_core/shield.py`
- `src/autonomous_investment_robot/services/universe_core/memory.py`
- `src/autonomous_investment_robot/services/universe_core/research.py`
- `src/autonomous_investment_robot/services/universe_core/cross_asset.py`
- `src/autonomous_investment_robot/services/universe_core/ops.py`
- `src/autonomous_investment_robot/services/universe_core/service.py`

This is deliberately additive. It does not replace the live orchestrator yet. Instead it creates the missing top-layer contracts and a deterministic `UniverseMind` cycle that can already:

- ingest canonical world/account/risk/health events
- build a central world-state graph
- choose a mission
- evaluate a strategy parliament
- compile an execution plan
- gate it through a unified shield
- persist a decision packet into memory
- grade outcomes offline
- compute research promotion state
- allocate across multiple market universes
- emit an ops/readiness snapshot

## Phase 1 Unified Event Fabric (Implemented)

`services/universe_core/events.py` now provides an additive unified fabric for `UNIVERSE CORE` runtime events:

- expanded envelope contract with identity, domain, schema, timing, correlation/causation, replay/snapshot flags, producer/trace tags, and payload
- event-domain taxonomy (`market`, `account`, `execution`, `risk`, `regime`, `mission`, `strategy`, `telemetry`, `system`, `research`)
- typed schema registry with per-event required-field checks and schema-version compatibility checks
- middleware pipeline, wildcard subscriptions, handler isolation, dead-letter routing, and metrics hooks
- append-only persistence + replay reader + correlation trace reconstruction
- source-aware TTL dedup cache with bounded memory
- projection seed for minimal market/account/risk/health read models
- runtime observability metrics (throughput, handler latency, dead-letter/schema reject rates, queue depth, replay speed)

Failure behavior is fail-safe: invalid events are rejected without crashing the loop, handler failures are isolated, and persistence failures trigger warning mode instead of fatal exit.

## Phase 2 World State Graph (Implemented)

The world model in `services/universe_core/state.py` now provides:

- deterministic reducers for all required domains: market, venue, asset, portfolio, execution, infra, risk, strategy
- per-domain freshness timestamps, stale-domain detection, and `safe_to_trade(...)` evaluation
- serializable snapshots with symbol-level query APIs and domain summaries
- projection failure behavior that marks world state unavailable (`graph_available = false`) without crashing the decision cycle

## Phase 3 Mission Engine (Implemented)

`services/universe_core/mission.py` now includes a typed mission layer centered on objective selection (not action selection):

- `MissionType`, `MissionReasonCode`, `MissionContext`, `MissionPolicy`, `MissionDecision`, `MissionTransitionSummary`
- deterministic `MissionEngine.choose(...)` over world, risk, execution, and infra posture
- conservative fallback (`observation_only`) if mission selection fails
- policy outputs that influence proposal eligibility and posture hints:
  - allowed/blocked strategy families
  - execution posture hint
  - shield posture hint
  - no-trade preference
  - conservative size clipping hint

`UniverseMind.run_cycle()` now applies mission policy to proposals before parliament scoring and emits enriched `MissionEvent` payloads. Mission metadata is propagated into:

- `WorldStateGraph.strategy_state`
- decision packets (`universe_memory.jsonl`)
- `UniverseOpsSnapshot` diagnostics

The Phase 2 world-state layer is now materially implemented inside `services/universe_core/state.py`:

- typed domains for market, venue, asset, portfolio, execution, infra, risk, and strategy state
- deterministic projection/update semantics via `WorldStateGraph`
- a `WorldStateStore` query layer with symbol, portfolio, execution, risk, infra, and strategy reads
- freshness/as-of semantics and JSON-safe snapshot export

This is still additive. `UNIVERSE CORE` can consume the world-state graph today, but the legacy orchestrator is not yet fully migrated to it as a canonical read model.

Validation currently lives in:

- `tests/test_universe_core.py`

That test file covers the first operational slice across Phases 1 through 10 without touching current live safety invariants.

## Non-Negotiable Constraints

- Preserve existing hard safety rules, live manual gate, exposure caps, profit-floor logic, and fail-closed behavior.
- Prefer additive modules and adapters over orchestrator rewrites.
- Keep all new state replay-safe, typed, and auditable.
- Do not claim a phase is complete while key behavior still lives in ad hoc orchestrator wiring.
- Every phase must end in a shippable state: production-active, shadow-active, or safely scaffolded behind a flag.

## Current Runtime Mapping

| UNIVERSE layer | Current code anchors | Truth status |
| --- | --- | --- |
| `UNIVERSE SENSE` | `services/data_ingestion`, `services/market_watch`, `services/raw_store`, `services/universe`, `connectors/cex/*` | Strong partial foundation |
| `UNIVERSE STATE` | `services/autonomous_decision/engine.py`, `services/autonomous_decision/causal_market_twin.py`, `services/risk_engine`, `services/liquidity_map`, `services/universe_core/state.py` | Implemented in `universe_core` meta-layer; legacy orchestrator migration still partial |
| `UNIVERSE MISSION` | `services/policy/mastermind_policy.py`, orchestrator mode/guard logic, `services/incident`, `services/universe_core/mission.py` | Implemented in `universe_core` meta-layer; legacy orchestrator path remains authoritative |
| `UNIVERSE PARLIAMENT` | `services/policy/service.py`, `services/policy/allocator.py`, `services/policy/mastermind_policy.py` | Partial, but not a formal proposal parliament |
| `UNIVERSE EXEC` | `services/execution/smart_router.py`, `services/execution/live_*`, `services/execution/cost_engine.py`, `services/execution/rate_limit_governor.py` | Strong partial foundation |
| `UNIVERSE SHIELD` | `services/risk_engine`, `services/execution/profit_gate.py`, `services/reliability/health_audit_110.py`, `services/reliability/watchdog.py`, `services/governance`, `services/compliance`, `services/universe_core/shield.py` | Implemented in `universe_core` meta-layer; legacy orchestrator authority path intentionally preserved |
| `UNIVERSE MEMORY` | `services/storage`, `services/event_store`, `services/research/service.py`, `services/research/self_improvement.py` | Partial, but fragmented across stores |
| `UNIVERSE OPS` | `services/ops/service.py`, `services/distributed/*`, `scripts/runtime_audit.py`, deployment docs/runbooks | Strong partial foundation |

## Truth Summary By Phase

| Phase | Status | What exists now | Missing first-class capability |
| --- | --- | --- | --- |
| Phase 1. Unified Event Fabric | Implemented (meta-layer) | `services/universe_core/events.py` + additive adapters to `EventStore`/`ReliabilityBus` | full migration of legacy producers still pending |
| Phase 2. World State Graph | Implemented (meta-layer) | `services/universe_core/state.py` typed graph + projection/query layer | orchestrator canonical-read migration still pending |
| Phase 3. Mission Engine | Implemented (meta-layer) | `services/universe_core/mission.py` + mission policy propagation/events | orchestrator-side objective migration still pending |
| Phase 4. Strategy Parliament | Partial | strategy components, allocator weights, mastermind scoring | typed `StrategyProposal`, parliament judge, conflict resolution/blending, memory hooks |
| Phase 5. Execution Intelligence | Strong partial | smart routing, cost model, slicing, live services, rate controls | explicit `ExecutionPlan` contract, lifecycle metrics, repricing orchestration |
| Phase 6. Universe Shield | Implemented (meta-layer) | typed `ShieldEscalation*` contracts, deterministic escalation matrix, hysteresis state, mission/parliament/meta-aware shield decisions, ops/decision-packet diagnostics | legacy orchestrator remains authoritative path until planned migration |
| Phase 7. Memory Engine | Partial | SQLite persistence, event store, research registry, self-improvement logs | unified decision packet schema, grading pipeline, regime-policy performance memory |
| Phase 8. Research / Replay Lab | Strong partial | record/replay, walk-forward, nested OOS gate, paper mode | event-store-backed replay lab, standardized promotion ladder and reports |
| Phase 9. Cross-Asset Expansion | Partial | spot, futures, perps, xStocks-related paths, distributed ranking | explicit cross-asset allocator and adapter contracts |
| Phase 10. Universe Ops / Productionization | Strong partial | metrics, audit logs, distributed audit stream, runbooks, deployment scripts | unified governance checklist, rollout/rollback contract, final readiness artifact |

## Dependency Order

1. Phase 1 must establish a canonical envelope before any serious Phase 2 projection work.
2. Phase 2 must expose stable read APIs before Phase 3 mission selection and Phase 4 parliament selection become clean.
3. Phase 3 and Phase 4 can iterate in parallel after a minimum world-state contract exists.
4. Phase 5 depends on Phase 4 output shape, but current routing code can be adapted rather than replaced.
5. Phase 6 must integrate with the outputs of Phases 3 to 5, not bypass them.
6. Phase 7 should consume Phase 3 to 6 artifacts, especially mission, proposal, execution, and shield outcomes.
7. Phase 8 should be rebuilt on top of Phase 1 event storage and Phase 7 memory records.
8. Phase 9 depends on Phase 2, 4, 5, and 6 abstractions being venue-agnostic.
9. Phase 10 spans the whole program, but final readiness should happen only after Phase 1 to 9 contracts settle.

## Phase Execution Details

### Phase 1: Unified Event Fabric

Linear scope: `1.1` through `1.16`

Current baseline:

- `services/replay/events.py` already defines typed runtime events plus deterministic checksums and idempotency keys.
- `services/event_store/service.py` already persists per-stream JSONL event logs.
- `services/reliability/bus.py` already provides append, dedup, replay, and dead-letter behavior.
- `services/distributed/contracts.py` already defines a typed distributed envelope for Redis streams.

Truthful gap:

- These pieces are independent. The runtime still has multiple event shapes and multiple publish paths.
- There is no single `EventEnvelope` used across market, account, execution, risk, telemetry, audit, and distributed flows.
- There is no schema registry or event middleware contract.

Required deliverables:

- Add a canonical envelope under a new `services/universe_events` or similar package.
- Define event taxonomy and schema versioning for market, account, execution, risk, mission, parliament, shield, telemetry, and ops domains.
- Wrap current event emitters so they publish through one fabric without breaking current logs.
- Add projection hooks that Phase 2 can consume.

Acceptance criteria:

- Every new unified event has `event_id`, `event_type`, `version`, `source`, `ts`, `partition_key`, `idempotency_key`, and `payload`.
- Market/account/execution/risk/telemetry events can be replayed in order from one interface.
- Duplicate events are dropped deterministically and dead-lettered after bounded retries.
- Existing audit and live safety flows remain intact.

Validation:

- Preserve and extend `tests/test_treasury_governance_reliability.py`.
- Add event schema tests, ordering tests, middleware tests, and replay parity tests.
- Run existing record/replay tests after Kraken integration wiring.

Primary entry points:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/replay/events.py`
- `src/autonomous_investment_robot/services/event_store/service.py`
- `src/autonomous_investment_robot/services/reliability/bus.py`
- `src/autonomous_investment_robot/services/ops/service.py`

### Phase 2: World State Graph

Linear scope: `2.1` through `2.6`

Current baseline:

- `services/autonomous_decision/engine.py` already computes market state, forecasts, uncertainty, and decision context.
- `services/autonomous_decision/causal_market_twin.py` already builds a causal snapshot for scenario arbitration.
- `services/risk_engine/service.py`, `services/liquidity_map`, and execution diagnostics already hold fragments of venue, risk, and execution state.

Truthful gap:

- State is fragmented across orchestrator locals, model state, service-specific caches, and ad hoc diagnostics payloads.
- There is no central world graph with stable read semantics.
- Confidence, stability, and transition scoring are not represented as a unified state contract.

Required deliverables:

- Build a typed `WorldStateGraph` with market, venue, portfolio, execution, risk, and infra domains.
- Implement projections from Phase 1 events.
- Add read/query APIs that downstream phases consume instead of direct orchestrator internals.
- Add confidence/stability/transition scoring to the graph.

Acceptance criteria:

- A single graph snapshot can explain why the current mission or action was chosen.
- Query methods are deterministic under replay.
- Risk and infra health state are included in the same graph as market state.

Validation:

- Extend `tests/test_autonomous_decision_engine.py` and `tests/test_causal_market_twin_engine.py`.
- Add graph projection tests using ordered event sequences.
- Add replay correctness tests comparing graph snapshots against recorded baselines.

Primary entry points:

- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
- `src/autonomous_investment_robot/services/autonomous_decision/causal_market_twin.py`
- `src/autonomous_investment_robot/core/orchestrator.py`

### Phase 3: Mission Engine

Linear scope: `3.1` through `3.5`

Current baseline:

- `services/policy/mastermind_policy.py` already enforces runtime mode, entry budget, and basic strategy selection.
- Existing orchestrator and incident/risk logic already impose no-trade and exits-only states.

Truthful gap:

- Mission selection is implicit. There is no explicit objective layer that can say "protect capital", "harvest carry", "trend capture", "inventory cleanup", or "observe only".
- Mission changes are not eventized.

Required deliverables:

- Define a mission taxonomy and typed mission state.
- Add a mission selector that consumes Phase 2 world state.
- Emit mission lifecycle events.
- Integrate no-trade and degraded modes into mission outcomes instead of scattered booleans.

Acceptance criteria:

- The runtime can explain the active mission and why it changed.
- No-trade and exits-only outcomes are mission states, not hidden side effects.
- Mission decisions remain subordinate to hard safety controls.

Validation:

- Extend `tests/test_mastermind_policy.py` and incident policy tests.
- Add replay scenarios for regime change, feed degradation, and execution stress.

Primary entry points:

- `src/autonomous_investment_robot/services/policy/mastermind_policy.py`
- `src/autonomous_investment_robot/services/incident`
- `src/autonomous_investment_robot/core/orchestrator.py`

### Phase 4: Strategy Parliament

Linear scope: `4.1` through `4.6`

Current baseline:

- `services/policy/service.py` and existing decision components already produce strategy-like signals.
- `services/policy/allocator.py` already provides bandit-style performance weighting.
- `MastermindPolicy` already ranks component outputs inside one intent.

Truthful gap:

- There is no formal `StrategyProposal` contract.
- Strategies are not independent parliament members with standardized diagnostics, constraints, and confidence fields.
- Conflict resolution and blending are still embedded in decision logic.

Required deliverables:

- Define a common proposal contract for every strategy.
- Adapt existing strategies into members that return proposals instead of hidden intermediate dicts.
- Implement a parliament judge or meta-allocator that selects top-1 or top-N proposals.
- Persist enough metadata for later memory/grading.

Acceptance criteria:

- Multiple strategy proposals can be compared using one schema.
- Proposal selection is traceable and replayable.
- Blending rules never bypass risk limits or sell-side profit-floor invariants.

Validation:

- Extend policy and allocator tests.
- Add replay tests for proposal conflict and tie-breaking behavior.
- Add paper-mode behavior tests for proposal selection stability.

Primary entry points:

- `src/autonomous_investment_robot/services/policy/service.py`
- `src/autonomous_investment_robot/services/policy/allocator.py`
- `src/autonomous_investment_robot/services/policy/mastermind_policy.py`

### Phase 5: Execution Intelligence Layer

Linear scope: `5.1` through `5.6`

Current baseline:

- `services/execution/smart_router.py` already handles maker vs taker choice, route scoring, and slice planning.
- `services/execution/cost_engine.py`, `services/execution/slippage_calibrator.py`, and live execution services already model costs and route constraints.
- `services/execution/rate_limit_governor.py` and `services/execution/order_churn_controller.py` already constrain churn.

Truthful gap:

- The router outputs a route decision, but there is no first-class `ExecutionPlan` contract spanning decision, slicing, repricing, timeout, and fill-quality feedback.
- Repricing and timeout orchestration are still service-local.

Required deliverables:

- Define a typed `ExecutionPlan`.
- Standardize maker/taker, slicing, repricing, timeout, and fallback decisions behind that contract.
- Feed execution-quality measurements back to parliament, mission, and memory.

Acceptance criteria:

- Every submitted order can be tied to an execution plan.
- Execution plans capture expected edge, total modeled cost, fill probability, and escape conditions.
- Shadow and paper modes can execute the same plan contract without live exchange writes.

Validation:

- Extend `tests/test_tco_execution.py`, router tests, and live service tests.
- Add explicit execution-plan unit tests and paper/shadow parity tests.

Primary entry points:

- `src/autonomous_investment_robot/services/execution/smart_router.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_router_service.py`

### Phase 6: Universe Shield

Linear scope: `6.1` through `6.5`

Current baseline:

- `services/risk_engine/service.py`, `services/execution/profit_gate.py`, `services/reliability/health_audit_110.py`, `services/reliability/watchdog.py`, `services/governance`, and `services/compliance` already enforce strong guardrails.
- Incident and health logic already support degraded and fail-closed behavior.

Phase 6 status update:

- `services/universe_core/shield.py` now exposes typed escalation contracts: `ShieldEscalationState`, `ShieldEscalationReason`, `ShieldEscalationDecision`, `ShieldHealthEnvelope`, `ShieldOverrideRecord`, and `ShieldHysteresisState`.
- `UniverseShield.assess(...)` now consumes mission output, parliament diagnostics, adaptive/meta diagnostics, regime confidence, exploration state, execution/infra/account stress, and world/risk posture to produce deterministic escalation decisions.
- Escalation modes are now explicit and replay-safe: `normal`, `cautious`, `defensive`, `observe_only`, `hard_stop`.
- Conservative de-escalation with hysteresis is enforced via sustained-recovery windows and stepwise unwind.
- `UniverseMind.run_cycle()` now propagates shield escalation details into risk events, ops snapshot, and decision memory packets.
- Existing hard safety doctrines (`hard_stop`/`observe_only` authority and fail-closed behavior) remain non-bypassable.

Required deliverables:

- Define shield modes and escalation levels.
- Centralize recovery, cooldown, degrade-to-observe, and exits-only behavior.
- Make shield outputs explicit inputs to mission selection, parliament selection, and execution planning.

Acceptance criteria:

- Shield decisions are visible and audit-friendly.
- Recovery and cooldown behavior are deterministic under replay.
- Existing hard safety behavior is preserved or strengthened.

Validation:

- Extend `tests/test_risk_live_guard.py`, `tests/test_watchdog_supervisor.py`, `tests/test_runtime_audit.py`, and related health tests.
- Add scenario tests for feed staleness, permission failures, rate storms, and reconciliation mismatch.

Primary entry points:

- `src/autonomous_investment_robot/services/risk_engine/service.py`
- `src/autonomous_investment_robot/services/execution/profit_gate.py`
- `src/autonomous_investment_robot/services/reliability/health_audit_110.py`
- `src/autonomous_investment_robot/services/reliability/watchdog.py`

### Phase 7: Memory Engine

Linear scope: `7.1` through `7.6`

Current baseline:

- `services/storage` already persists submissions and runtime records.
- `services/event_store/service.py` already stores event streams.
- `services/research/service.py` already records experiments, feature schemas, and nested walk-forward results.
- `services/research/self_improvement.py` already writes bounded self-improvement suggestions.

Truthful gap:

- There is no single decision packet schema tying together world state, mission, proposals, execution plan, shield state, and outcome.
- Post-trade grading and regime/policy memory are not first-class services.

Required deliverables:

- Define a decision packet record that binds phases 2 through 6 together.
- Persist post-trade and post-skip grading.
- Build regime-by-asset-by-policy performance memory.
- Add governance hooks for controlled policy updates only after validated improvement.

Acceptance criteria:

- Every decision can be reconstructed from one persisted packet.
- Grading is deterministic and does not mutate live policy directly.
- Memory features are read-only to production decisioning unless explicitly promoted.

Validation:

- Extend `tests/test_self_improvement.py` and storage-related tests.
- Add packet persistence tests, grading tests, and policy-promotion gate tests.

Primary entry points:

- `src/autonomous_investment_robot/services/storage`
- `src/autonomous_investment_robot/services/research/service.py`
- `src/autonomous_investment_robot/services/research/self_improvement.py`

### Phase 8: Research / Replay Lab

Linear scope: `8.1` through `8.6`

Current baseline:

- Record/replay flows already exist and are covered by replay tests.
- `ResearchPlatformService` already supports feature parity, leakage checks, experiments, nested walk-forward, and robust OOS gates.
- Paper mode already exists in the runtime.

Truthful gap:

- Research is not yet centered on the unified event store that Phase 1 requires.
- Promotion from replay to shadow to paper to limited live is not expressed as one formal ladder with standard reports.

Required deliverables:

- Rebuild replay on top of the unified event fabric and decision packets.
- Add shadow-mode evaluation using the same decision artifacts as live.
- Standardize evaluation reports and promotion gates.

Acceptance criteria:

- Replay, shadow, and paper share the same core state and decision contracts.
- Promotion decisions are evidence-based and reproducible.
- Reports capture both return metrics and safety/quality metrics.

Validation:

- Preserve `tests/test_record_replay_recordings.py`, `tests/test_replay_golden.py`, `tests/test_research*`, and walk-forward tests.
- Add promotion-ladder tests that fail closed when evidence is insufficient.

Primary entry points:

- `src/autonomous_investment_robot/services/replay`
- `src/autonomous_investment_robot/services/research/service.py`
- `src/autonomous_investment_robot/main.py`

### Phase 9: Cross-Asset Expansion

Linear scope: `9.1` through `9.5`

Current baseline:

- The runtime already spans spot, perps, futures, and some xStocks-related handling.
- `services/distributed/compute_bridge.py` and ranking logic already expose a venue-aware scoring path.
- Risk and execution services already know about multiple providers.

Truthful gap:

- Cross-asset support is still mostly adapter-specific.
- There is no first-class cross-market allocator or normalized asset-opportunity contract.

Required deliverables:

- Define venue and asset-class adapters that emit the same world state and proposal contracts.
- Add a cross-market allocator above symbol-level strategy selection.
- Make capital allocation and shield rules asset-aware but contract-compatible.

Acceptance criteria:

- New venues can plug in without changing mission or parliament interfaces.
- Allocation decisions can compare opportunities across asset classes using normalized constraints and costs.

Validation:

- Extend multi-exchange, universe, and risk-cap tests.
- Add allocator tests spanning spot, perps, and xStocks/equity-like instruments.

Primary entry points:

- `src/autonomous_investment_robot/services/multi_exchange`
- `src/autonomous_investment_robot/services/universe`
- `src/autonomous_investment_robot/services/distributed/compute_bridge.py`
- `src/autonomous_investment_robot/core/orchestrator.py`

### Phase 10: Universe Ops / Productionization

Linear scope: `10.1` through `10.6`

Current baseline:

- `services/ops/service.py` already exports audit logs, metrics, dashboard snapshots, and config history.
- `services/distributed/*` already covers audit stream publishing, compute bridge contracts, and Postgres mirror support.
- Deployment docs, runbooks, topology docs, and audit scripts already exist in the repo.

Truthful gap:

- Operational controls are spread across scripts and docs rather than one authoritative productionization contract.
- Final production readiness and rollback governance are not captured in one closing artifact.

Required deliverables:

- Define one runtime-boundary and deployment-governance document for live, shadow, paper, and compute roles.
- Consolidate configuration governance, rollback procedures, and migration checks.
- Add a final readiness checklist and a closing truth report.

Acceptance criteria:

- Operators can determine whether a build is replay-ready, shadow-ready, paper-ready, or live-ready from one artifact set.
- Rollback and migration steps are documented and testable.
- Universe audit events remain queryable after distributed deployment changes.

Validation:

- Preserve runtime audit, distributed, and deployment validation tests.
- Add smoke checks for distributed audit publication, config drift detection, and rollback rehearsals.

Primary entry points:

- `src/autonomous_investment_robot/services/ops/service.py`
- `src/autonomous_investment_robot/services/distributed/contracts.py`
- `src/autonomous_investment_robot/services/distributed/compute_bridge.py`
- `src/autonomous_investment_robot/services/distributed/postgres_mirror.py`
- `scripts/runtime_audit.py`

## Recommended Execution Strategy

Use the following implementation order for actual code work:

1. Build Phase 1 as a thin compatibility layer, not a rewrite.
2. Implement Phase 2 projections on top of that event layer.
3. Add Phase 3 mission state and Phase 4 proposal contracts behind flags.
4. Refactor Phase 5 execution into an `ExecutionPlan` without destabilizing live services.
5. Unify Phase 6 shield outputs only after Phases 3 to 5 have typed contracts.
6. Introduce Phase 7 decision packets before broad replay-lab changes.
7. Move Phase 8 replay, promotion, and shadow workflows onto the new contracts.
8. Generalize for Phase 9 only after state, proposal, and execution interfaces are stable.
9. Finish Phase 10 by freezing the production contract and writing the final truth report.

## What UNI-6 Does Not Mean

- It does not mean all ten phases are already implemented.
- It does not justify deleting or weakening existing live safety controls.
- It does not justify replacing stable live services with speculative abstractions in one step.
- It does not justify claiming a new architecture is complete without replay, paper, and operational validation.
