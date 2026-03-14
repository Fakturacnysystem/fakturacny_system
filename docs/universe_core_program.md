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
- `src/autonomous_investment_robot/services/universe_core/execution_intel.py`
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
- refine execution through microstructure-aware execution intelligence
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
| `UNIVERSE MEMORY` | `services/storage`, `services/event_store`, `services/research/service.py`, `services/research/self_improvement.py`, `services/universe_core/memory.py` | Implemented in `universe_core` meta-layer; legacy orchestrator authority path intentionally preserved |
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
| Phase 7. Memory Engine | Implemented (meta-layer) | typed decision memory records, deterministic outcome grading, shield-aware policy grading, promotion/demotion/retirement recommendation gates, bounded retention compaction, ops learning summaries | legacy orchestrator-wide adoption remains out of scope for additive rollout |
| Phase 8. Research / Replay Lab | Implemented (meta-layer) | deterministic replay session, decision reconstruction, comparative counterfactual evaluation, walk-forward holdout evaluation, promotion ladder stages, adaptive activation gate, replay retention/compaction, UniverseMind/ops integration | legacy orchestrator-wide authority migration remains out of scope for additive rollout |
| Phase 9. Execution Intelligence Hardening | Implemented (meta-layer) | microstructure sensing, stress-indexed execution personality, liquidity-aware slicing, execution risk identity, exchange health checks, capital-survival doctrine, and memory-feedback wiring in `execution_intel.py` | legacy orchestrator-wide authority migration remains out of scope for additive rollout |
| Phase 10. Universe Ops / Productionization | Implemented (meta-layer) | typed rollout governance contracts, activation-gate decisions, operator approval artifacts, evidence bundles, promotion governance decisioning, rollback readiness records, and governance observability in `services/universe_core/ops.py` + `service.py` integration | legacy orchestrator-wide authority migration remains out of scope for additive rollout |
| Phase 11. Legacy Orchestrator Shadow Adapter | Implemented (additive) | orchestrator-integrated, env-gated UniverseMind shadow adapter emits per-cycle decision packets and observability diagnostics while persisting to `run_dir/universe_shadow/*` | remains shadow-only; legacy orchestrator execution authority path is still sole live authority |
| Phase 12. Unified Event Fabric Legacy Producer Adoption | Implemented (additive) | `EventFabric` legacy adapters normalize selected legacy producer shapes into canonical Universe envelopes with deterministic idempotency and dead-letter handling | broad legacy producer migration is still incremental beyond selected adopted domains |
| Phase 13. World State Canonical Read Adapter | Implemented (additive) | typed `WorldStateReadAdapter` contracts now bridge runtime world-state availability/freshness into orchestrator decision context and decision-brain diagnostics | canonical read consumption is additive and currently derived from runtime observation adapter path |
| Phase 14. Mission and Incident Bridge | Implemented (additive) | mission diagnostics bridge from shadow `UniverseMind` into orchestrator audit/decision telemetry, incident advisory inputs, and mastermind mission trace payloads | remains advisory and non-authoritative; hard safety actions retain strict precedence |
| Phase 15. Strategy Parliament Contract Adapter | Implemented (additive) | legacy policy intents can now emit deterministic typed `StrategyProposal` contract payloads (env-gated) and Universe Core parliament intent adapter now consumes serialized proposal contracts first | default runtime remains unchanged unless adapter env gate is enabled, preserving replay-golden baselines |
| Phase 16. ExecutionPlan Contract Bridge | Implemented (additive) | shadow `ExecutionPlan` contract diagnostics are bridged into live intent metadata (env-gated) and deterministic risky-buy blocking (`abort`/`non-positive-edge`/`critical`) is enforced in legacy execution path | remains additive and non-authoritative with legacy router authority preserved |
| Phase 17. Shield Convergence Adapter | Implemented (additive) | shadow shield escalation telemetry now converges into legacy risk/watchdog contexts via additive adapters and non-bypassable shield hard-stop/observe-only risk decisions | bridge is env-gated and preserves existing authority path; hard safety is strengthened |
| Phase 18. Decision Memory Ubiquity | Implemented (additive) | learning-summary schemas are now normalized without dropping extended replay/meta keys, and decision-tick memory traces are persisted via bounded ops memory trace adapter for broader path coverage | additive memory-trace layer is bounded and non-authoritative; Universe decision authority remains unchanged |
| Phase 19. Replay Determinism and Promotion Gate CI | Implemented (additive) | typed replay-promotion contract hashing is now produced from replay batch metadata, and promotion stage changes are gated on replay determinism with deterministic evidence/rollback linkage in `ops` governance artifacts | governance remains advisory and separated from live activation; legacy orchestrator authority path is unchanged |
| Phase 20. Cross-Asset Allocator Normalization | Implemented (additive) | cross-asset allocator now normalizes market-class aliases, applies deterministic class-aware scoring, and enforces deterministic market-class weight caps; distributed local ranking normalizes market-class aliases to the same canonical classes | allocations remain bounded by additive caps and compatible with existing risk gates; live authority path remains unchanged |
| Phase 21. Distributed Runtime Evidence Enforcement | Implemented (additive) | deployment-manifest validator now emits explicit runtime-evidence gate status (`rollout_claim_ready`) and classifies missing runtime artifacts/host constraints as `blocked` vs `pass`; distributed tests assert blocked-vs-pass contract behavior | distributed rollout claims are now evidence-driven and cannot be truthfully marked ready from static checks alone |
| Phase 22. Rollback Dry-Run Automation | Implemented (additive) | rollback dry-run evidence is now machine-emitted by `safety_preflight` and `runtime_audit` (`rollback_dry_run.validated` + deterministic `artifact_id`) and consumed by Universe Ops rollback readiness via typed artifact bridge | rollback readiness no longer depends on manual boolean assertion alone; live authority path and safety doctrines remain unchanged |
| Phase 23. Configuration Determinism and Freeze Contract | Implemented (additive) | harmony resolved config now carries deterministic `resolved_config_fingerprint`; config-matrix audit emits per-config freeze contracts, matrix fingerprint, and machine-enforced drift failure counts (`drift_failures`) | checkpoint comparisons are now deterministic and machine-checkable without weakening existing guard/profit-floor doctrines |
| Phase 24. Manual Live Gate Dual-Control Hardening | Implemented (additive) | governance promotion approval now requires both operator approval artifact and manual env/file live gate for live-candidate stages; preflight and artifact-generation paths now include typed operator approval artifact handling | dual-control checks are explicit, test-backed, and fail-closed to `blocked` when either control is missing |
| Phase 25. Program Freeze and Truth Dossier | Implemented (additive) | final freeze dossier and phase ledger published with residual-risk register and strict completion evidence across phases 10-25 | roadmap window is now frozen for this cycle; further changes should open a new phase window with explicit backlog update |

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

Phase 7 status update:

- `services/universe_core/memory.py` now defines typed memory and learning contracts:
  - `DecisionMemoryRecord`, `DecisionMemorySnapshot`, `DecisionFingerprint`
  - `DecisionOutcomeGrade`, `OutcomeGrade`, `OutcomeGradeReason`
  - `PolicyGradeRecord`, `StrategyPolicyGrade`, `GradeWindowSummary`
  - `PromotionGateDecision`, `DemotionGateDecision`, `RetirementGateDecision`
  - `ReplayPromotionCandidate`, `PromotionEvidenceBundle`, `LearningCandidateRecord`
  - `MemoryRetentionPolicy`, `MemoryCompactionDecision`, `MemoryArchiveSummary`
- Universe Core now persists bounded decision memory records with stable fingerprints and replay eligibility markers.
- Outcome grading is deterministic from persisted evidence and explicitly shield-aware.
- Promotion/demotion/retirement gates produce recommendation records only; they do not silently activate live behavior changes.
- Bounded compaction and archive summaries are now part of memory retention health.
- `UniverseMind.run_cycle()` now enriches ops snapshots and decision packets with Phase 7 learning summaries in additive mode.

Truthful gap:

- This rollout is intentionally additive to Universe Core; legacy orchestrator authority path is unchanged.

Acceptance criteria:

- Every Universe Core decision remains reconstructable from persisted packet + memory record.
- Grading, policy summaries, and gate recommendations are deterministic and replay-safe.
- Learning remains recommendation-only unless explicitly promoted outside this phase.

Validation:

- `tests/test_universe_memory_phase7.py`
- `tests/test_universe_core.py`
- `tests/test_universe_meta_intelligence.py`
- `tests/test_universe_shield_phase6.py`

### Phase 8: Research / Replay Lab

Linear scope: `8.1` through `8.6`

Phase 8 status update:

- `services/universe_core/replay_ladder.py` now provides production-grade replay/promotion primitives:
  - deterministic replay batch/session execution
  - decision reconstruction with explicit inferred markers
  - comparative counterfactual evaluation
  - walk-forward + holdout evaluation flow
  - strategy replay grading with reproducibility metadata
  - promotion ladder stages:
    - `offline_replay`
    - `walk_forward_validated`
    - `shadow_ready`
    - `paper_ready`
    - `limited_live_ready`
    - `scaled_live_candidate`
  - backward-compatible legacy aliases retained (`sandbox_shadow`, `shadow_live`, etc.)
  - adaptive activation gate with hard kill-switch handling
  - bounded replay retention and compaction in memory persistence
- `UniverseMind.run_cycle()` now runs the Phase 8 ladder when enabled (`UNIVERSE_REPLAY_PROMOTION_ENABLED=1`) and propagates replay/promotion summaries into:
  - memory artifacts
  - ops snapshot
  - decision packet learning summary
- Recommendation vs activation remains separated:
  - ladder emits promotion decisions and gated activation recommendations
  - no silent global live promotion is performed by Phase 8 itself.

Truthful gap:

- This remains additive inside Universe Core; legacy orchestrator authority path is intentionally unchanged.

Validation:

- `tests/test_universe_replay_phase8.py`
- `tests/test_universe_core.py`
- `tests/test_universe_meta_intelligence.py`
- `tests/test_universe_shield_phase6.py`
- `tests/test_universe_memory_phase7.py`

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

Phase 10 status update:

- `services/universe_core/ops.py` now defines typed rollout-governance contracts:
  - `ActivationGateContract`
  - `OperatorApprovalArtifact`
  - `PromotionEvidenceBundle`
  - `PromotionGovernanceDecision`
  - `RollbackReadinessRecord`
  - `RolloutGovernanceSnapshot`
- Rollout stage vocabulary is now explicit and normalized for production governance:
  - `offline_replay`
  - `shadow_ready`
  - `paper_ready`
  - `limited_live_ready`
  - `scaled_live_candidate`
  - `blocked`
- `UniverseOpsService.assess(...)` now computes regression gates + hard safety gates + manual live gate enforcement before resolving rollout stage.
- Promotion governance now consumes Phase 9 execution diagnostics (`mode`, stress, abort, advisory severity, net-edge).
- Ops snapshot now carries deployment-grade governance observability and rollback-readiness metadata.
- `UniverseMind.run_cycle()` integration remains additive: governance contracts are emitted via `ops_snapshot` and persisted in decision packets.

Truthful gap:

- This remains additive inside Universe Core; legacy orchestrator authority path is intentionally unchanged.

Primary entry points:

- `src/autonomous_investment_robot/services/ops/service.py`
- `src/autonomous_investment_robot/services/distributed/contracts.py`
- `src/autonomous_investment_robot/services/distributed/compute_bridge.py`
- `src/autonomous_investment_robot/services/distributed/postgres_mirror.py`
- `scripts/runtime_audit.py`

### Phase 11: Legacy Orchestrator Shadow Adapter

Linear scope: `11.1` through `11.4`

Phase 11 status update:

- `src/autonomous_investment_robot/core/orchestrator.py` now includes an additive, shadow-only UniverseMind adapter:
  - `AUTONOMOUS_UNIVERSE_SHADOW_ENABLED` (default off)
  - `AUTONOMOUS_UNIVERSE_SHADOW_FAIL_OPEN` (default on)
  - `AUTONOMOUS_UNIVERSE_SHADOW_EVERY_N_STEPS` (default 1)
- When enabled, orchestrator emits one shadow Universe Core cycle per runtime loop step and records packet diagnostics:
  - audit events: `universe_shadow_cycle`, `universe_shadow_cycle_error`
  - module telemetry: `universe_shadow_adapter`
  - decision tick extras: `universe_shadow_enabled`, `universe_shadow_emitted`, `universe_shadow_packet_id`, `universe_shadow_error`
- Shadow decision packets are persisted under `run_dir/universe_shadow/*`, providing replay/audit parity without touching order authority.
- Adapter behavior is fail-open by default to preserve deterministic runtime safety.

Truthful gap:

- Shadow outputs are advisory/observability only; they do not alter order submission authority or bypass hard safety/manual live gates.

Primary entry points:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/universe_core/service.py`
- `tests/test_orchestrator_universe_allowlist.py`
- `docs/operator_runbook.md`

### Phase 12: Unified Event Fabric Legacy Producer Adoption

Linear scope: `12.1` through `12.4`

Phase 12 status update:

- `src/autonomous_investment_robot/services/universe_core/events.py` includes additive legacy adapters:
  - `LEGACY_EVENT_TYPE_MAP`
  - `adapt_legacy_event(...)`
  - `EventFabric.ingest_legacy_event(...)`
  - `EventFabric.ingest_legacy_events(...)`
- `src/autonomous_investment_robot/core/orchestrator.py` now bridges selected legacy producer writes through canonical envelope mirroring while preserving existing artifact paths:
  - `_ensure_universe_event_adapter_fabric(...)`
  - `_append_legacy_event_and_mirror(...)`
  - env controls:
    - `AUTONOMOUS_UNIVERSE_EVENT_ADAPTER_ENABLED` (default on)
    - `AUTONOMOUS_UNIVERSE_EVENT_ADAPTER_FAIL_OPEN` (default on)
- Selected legacy producer events now map to canonical Universe Core envelope contracts:
  - `MarketEvent -> MarketTickEvent`
  - `OrderIntentEvent -> StrategyProposalEvent`
  - `OrderEvent -> OrderEvent`
  - `FillEvent -> FillEvent`
  - `PositionEvent -> AccountSnapshotEvent`
  - `RiskEvent -> RiskEvent`
  - `ComplianceEvent -> HealthEvent`
- Deterministic dedup is preserved via stable idempotency keys derived from legacy payload/sequence/checksum.
- Dead-letter behavior remains deterministic and explicit via `legacy_adapter_reject` classification.
- Existing event-store and reliability-bus artifacts remain backward-compatible:
  - legacy `EventStore` appends remain unchanged
  - canonical mirror is additive, metadata-tagged, and fail-open by default.

Primary entry points:

- `src/autonomous_investment_robot/services/universe_core/events.py`
- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/replay/events.py`
- `src/autonomous_investment_robot/services/event_store/service.py`
- `src/autonomous_investment_robot/services/reliability/bus.py`
- `tests/test_orchestrator_universe_allowlist.py`

### Phase 13: World State Canonical Read Adapter

Linear scope: `13.1` through `13.4`

Phase 13 status update:

- `src/autonomous_investment_robot/services/universe_core/state.py` now includes typed read-adapter contracts:
  - `WorldStateReadView`
  - `WorldStateReadAdapter`
  - adapter methods for snapshot, runtime observation, and conservative fallback views
- `src/autonomous_investment_robot/core/orchestrator.py` now consumes world-state read views via adapter APIs for each decision cycle.
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py` now ingests world-state adapter payload in `DecisionContext` and makes graph/freshness state explicit in diagnostics:
  - `world_state_source`
  - `world_state_available`
  - `world_state_graph_available`
  - `world_state_safe_to_trade`
  - `world_state_freshness_s`
  - stale domain diagnostics
- Conservative behavior is explicit and deterministic:
  - unavailable graph/state -> `world_state_unavailable`
  - stale critical domains -> `world_state_stale`
  - unsafe state posture -> `world_state_guard`

Primary entry points:

- `src/autonomous_investment_robot/services/universe_core/state.py`
- `src/autonomous_investment_robot/services/autonomous_decision/engine.py`
- `src/autonomous_investment_robot/core/orchestrator.py`
- `tests/test_autonomous_decision_engine.py`

### Phase 14: Mission and Incident Bridge

Linear scope: `14.1` through `14.4`

Phase 14 status update:

- `src/autonomous_investment_robot/core/orchestrator.py` now emits mission bridge diagnostics per cycle from shadow mission payloads:
  - `mission`
  - `mission_reason_codes`
  - `mission_no_trade_preferred`
  - `mission_allow_new_risk`
  - `mission_execution_posture_hint`
- Orchestrator now exports mission-bridge advisory metrics and events without changing authority path:
  - `mission_bridge_no_trade_preferred`
  - `mission_bridge_allow_new_risk`
  - audit event `mission_bridge` with `authority=advisory_non_authoritative`
- `src/autonomous_investment_robot/services/incident/service.py` now consumes mission-bridge advisory metrics as a non-authoritative final clause:
  - emits `IncidentAction("no_open_until_stable", "MissionNoTradeAdvisory")`
  - hard incident checks remain evaluated first, preserving safety precedence
- `src/autonomous_investment_robot/services/policy/mastermind_policy.py` now copies mission bridge context into `intent.why["mastermind"]["mission_advisory"]` for traceable strategy-selection diagnostics.

Primary entry points:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/incident/service.py`
- `src/autonomous_investment_robot/services/policy/mastermind_policy.py`
- `tests/test_incident_policy_phase3.py`
- `tests/test_orchestrator_universe_allowlist.py`
- `tests/test_mastermind_policy.py`

### Phase 15: Strategy Parliament Contract Adapter

Linear scope: `15.1` through `15.4`

Phase 15 status update:

- `src/autonomous_investment_robot/services/policy/service.py` now includes an additive legacy-policy adapter that serializes accepted strategy components into typed `StrategyProposal` contract dictionaries:
  - contract payload key: `intent.why["strategy_proposals"]`
  - contract version key: `intent.why["strategy_proposals_contract_version"] = "v1"`
  - adapter gate: `AUTONOMOUS_STRATEGY_PROPOSAL_ADAPTER_ENABLED` (default `off` for replay baseline stability)
- `src/autonomous_investment_robot/services/universe_core/parliament.py` now prioritizes pre-serialized `strategy_proposals` payloads in `strategy_proposals_from_intent(...)` and falls back to component adaptation when absent.
- Determinism and risk-capping behavior:
  - proposal serialization ordering is deterministic
  - serialized target notional remains bounded by final intent target notional
  - default-off gate preserves historical replay-golden checksums unless operator explicitly enables adapter.

Primary entry points:

- `src/autonomous_investment_robot/services/policy/service.py`
- `src/autonomous_investment_robot/services/universe_core/parliament.py`
- `tests/test_phase1_policy_regime.py`
- `tests/test_universe_core.py`
- `tests/test_universe_meta_intelligence.py`

### Phase 16: ExecutionPlan Contract Bridge

Linear scope: `16.1` through `16.4`

Phase 16 status update:

- `src/autonomous_investment_robot/core/orchestrator.py` now bridges compact shadow `ExecutionPlan` semantics from additive UniverseMind cycles into diagnostics and optional intent metadata:
  - `execution_plan_contract`
  - `execution_plan_abort`
  - `execution_plan_abort_reason_codes`
  - `execution_plan_advisory_severity`
  - `execution_plan_advisory_reason_codes`
- Bridge is explicitly env-gated:
  - `AUTONOMOUS_UNIVERSE_EXECUTION_PLAN_BRIDGE_ENABLED` (default `off`)
- When bridge gate is enabled, orchestrator emits `execution_plan_bridge` advisory audit records and applies deterministic skip guards for risky buy intents:
  - `execution_plan_abort`
  - `execution_plan_non_positive_edge`
  - `execution_plan_critical_advisory`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py` now enforces the same deterministic execution-plan bridge guardrails on incoming buy intents (gate-controlled) before venue submission.

Primary entry points:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py`
- `src/autonomous_investment_robot/services/universe_core/execution.py`
- `src/autonomous_investment_robot/services/universe_core/execution_intel.py`
- `tests/test_universe_execution_phase9.py`
- `tests/test_kraken_spot_live_service.py`

### Phase 17: Shield Convergence Adapter

Linear scope: `17.1` through `17.4`

Phase 17 status update:

- `src/autonomous_investment_robot/services/risk_engine/service.py` now includes additive shield telemetry adapter methods:
  - `apply_shield_telemetry(...)`
  - `shield_telemetry_snapshot(...)`
- Risk engine now enforces non-bypassable shield outcomes:
  - `shield_observe_only` blocks new-risk actions
  - `shield_hard_stop` blocks/flatten path for non-reduce intents
  - reduce-only actions remain allowed under hard-stop for de-risking (`shield_hard_stop_reduce_only`)
- `src/autonomous_investment_robot/core/orchestrator.py` now bridges shadow shield telemetry into legacy risk/watchdog path when enabled:
  - gate: `AUTONOMOUS_UNIVERSE_SHIELD_BRIDGE_ENABLED` (default `off`)
  - bridge audit events/metrics:
    - `shield_bridge`
    - `shield_bridge_hard_stop`
    - `shield_bridge_observe_only`
  - runtime health heartbeat now includes shield/risk context fields.
- `src/autonomous_investment_robot/services/reliability/watchdog.py` now surfaces `shield_context` from heartbeat payload in `health()` output.

Primary entry points:

- `src/autonomous_investment_robot/services/universe_core/shield.py`
- `src/autonomous_investment_robot/services/risk_engine/service.py`
- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/reliability/watchdog.py`
- `tests/test_universe_shield_phase6.py`
- `tests/test_risk_live_guard.py`
- `tests/test_watchdog_supervisor.py`

### Phase 18: Decision Memory Ubiquity

Linear scope: `18.1` through `18.4`

Phase 18 status update:

- `src/autonomous_investment_robot/services/universe_core/service.py` now normalizes learning-summary payloads across normal/fallback paths using additive schema backfill while preserving extended replay/meta keys:
  - required memory/governance fields are always present
  - extended fields (`replay_batch_status`, feedback/replay deltas, etc.) are preserved
- `src/autonomous_investment_robot/services/ops/service.py` now provides bounded decision memory trace persistence:
  - `record_universe_memory_trace(...)`
  - file: `run_dir/universe_memory_trace.jsonl`
  - bounded retention via `AUTONOMOUS_UNIVERSE_MEMORY_TRACE_MAX_ROWS`
- `src/autonomous_investment_robot/core/orchestrator.py` now emits per-decision memory trace rows from decision-tick context, including packet id, mission/shield mode, execution-abort signal, and bounded-retention status fields.
- `tests/test_universe_memory_phase7.py` and `tests/test_ops_evidence_snapshot.py` now cover schema stability and bounded trace retention behavior.

Primary entry points:

- `src/autonomous_investment_robot/services/universe_core/memory.py`
- `src/autonomous_investment_robot/services/universe_core/service.py`
- `src/autonomous_investment_robot/services/ops/service.py`
- `src/autonomous_investment_robot/core/orchestrator.py`
- `tests/test_universe_memory_phase7.py`
- `tests/test_ops_evidence_snapshot.py`

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
10. Add a Phase 11 shadow adapter in orchestrator runtime before any authority-path integration.
11. Add Phase 12 legacy event adapters only through additive canonical envelope bridges.
12. Add Phase 13 read-only world-state adapters and propagate availability/freshness into decision diagnostics and conservative guards.
13. Add Phase 14 mission/incident advisory bridge wiring while keeping all mission outputs non-authoritative against hard safety doctrine.
14. Add Phase 15 typed strategy-proposal adapter wiring (legacy policy to parliament contracts) behind additive gates that preserve replay determinism by default.
15. Add Phase 16 execution-plan advisory bridge wiring into live intent/execution gating with deterministic risky-path blocking and preserved legacy router authority.
16. Add Phase 17 shield telemetry convergence into legacy risk/watchdog context with non-bypassable shield hard-stop/observe-only safety outcomes.
17. Add Phase 18 memory ubiquity adapters to ensure decision-tick paths carry bounded memory traces and normalized learning summaries across normal/fallback branches.

## Program Window 26-35 Status (Additive)

Window `26..35` is implemented additively under:

- `docs/universe_core_autonomous_protocol_26_35.md`
- `docs/universe_core_phase_backlog_26_35.json`
- `tests/test_universe_program_window_26_35.py`

Implemented layers:

1. Phase 26: global market brain foundation and context fusion contracts.
2. Phase 27: multi-horizon decision layer with alignment/conflict diagnostics.
3. Phase 28: market-energy physics model (momentum/friction/turbulence/gravity).
4. Phase 29: deterministic future simulation/scenario tree with replay export.
5. Phase 30: cross-reality signal fusion with integrity/degradation reporting.
6. Phase 31: adaptive execution/risk personality engine with hysteresis tracing.
7. Phase 32: capital survival doctrine and existential escalation contracts.
8. Phase 33: offline-only evolutionary strategy research scaffold with deterministic mutation seeds.
9. Phase 34: committee-style fund brain recommendation bundle with disagreement/veto diagnostics.
10. Phase 35: institutional readiness compiler with certification, truth-room index, valuation pack, operator dossier, and residual risk register.

Safety and authority-path status remains unchanged:

- legacy orchestrator remains execution authority path
- manual live gate remains mandatory
- all new window layers are recommendation/diagnostic additive contracts
- full suite remained green during window completion gates.

## What UNI-6 Does Not Mean

- It does not mean all ten phases are already implemented.
- It does not justify deleting or weakening existing live safety controls.
- It does not justify replacing stable live services with speculative abstractions in one step.
- It does not justify claiming a new architecture is complete without replay, paper, and operational validation.
