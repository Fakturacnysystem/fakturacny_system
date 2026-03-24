.cursor/
  rules/
    trading-os-master.mdc
docs/
  CURSOR_MASTER_TASK.md
  CURSOR_PHASE_REPORT_TEMPLATE.md
  CURSOR_DEFINITION_OF_DONE.md

##   CURSOR_IMPLEMENTATION_ORDER.md

## description: Master implementation rules for Autonomous Trading OS
globs:
  - "src/autonomous_investment_robot/**/*.py"
  - "tests/**/*.py"
  - "docs/**/*.md"
alwaysApply: true

# Autonomous Trading OS - Master Cursor Rule

## Mission

You are working on an existing autonomous crypto trading system.
This repository is NOT a greenfield rewrite.
This repository must evolve through compatibility-first, correctness-first, fail-closed, production-grade implementation.

The target system is an autonomous trading operating system that:

- understands market state on multiple layers
- distinguishes truth from approximation
- treats uncertainty as a first-class input
- allows trades only when they survive hostile reality
- manages capital freely only inside a strict survival envelope
- can degrade, restrict itself, or halt automatically
- tracks order-state, fills, fees, PnL, and reconciliation truth precisely
- can explain every realized outcome with evidence
- remains compatible with the current system and avoids silent behavior drift

## Absolute non-negotiable rules

- Do not perform a big-bang rewrite.
- Refactor incrementally behind compatibility adapters and shims.
- Keep the system runnable after each phase.
- Preserve current CLI entrypoints.
- Preserve current config compatibility unless a backward-compatible additive change is strictly necessary.
- Preserve public imports and call signatures for:
  - RobotSettings
  - PolicyService.make_intent
  - RiskEngineService.evaluate
  - ExecutionService.execute_paper
  - ExecutionService.execute_live
  - OMSService
  - ReconciliationService.reconcile
  - ReconciliationService.reconcile_live
  - RobotOrchestrator.boot()
- Preserve replay/golden behavior unless a verified correctness defect requires an explicit, justified change.
- Do not silently update replay/golden fixtures.
- Do not present heuristics as ML.
- Do not present scaffolding as complete functionality.
- If an exchange/provider cannot provide authoritative truth, classify capability as partial and degrade behavior safely.
- No illegal or manipulative market behavior.
- Respect official exchange limits, semantics, websocket constraints, and authenticated stream behavior.
- Prefer truth, safety, replayability, auditability, recovery correctness, execution realism, and capital protection over sophistication.

## System philosophy

This system is not a predictor-first bot.
It is a probabilistic, reality-tested, capital-sovereign, fail-closed trading OS.

Core principle:
The system does not trade because it predicts profit.
It trades only when profit survives hostile reality.

## Architecture principles

- compatibility-first staged split
- hardened single-process core plus CI
- strict separation of:
  - truth ownership
  - truth confidence
  - decision authority
  - persistence ownership
- no-trade is a first-class outcome
- weak truth must reduce aggression
- uncertainty must reduce aggression
- bad execution conditions must reduce aggression
- restart safety is mandatory
- risk has veto power over everything

## Required bounded contexts

Foundation / hardening:

- MarketIntegrityService
- VenueCapabilityRegistry
- SharedVenueLimitGovernor
- OrderLifecycleMirror
- VenuePnLTruthProvider
- TruthConfidenceService
- ReconciliationService
- RecoveryStitchCoordinator
- RiskDictatorService
- ExecutionPlanService

Decision intelligence:

- QuantumScenarioService
- SignalInterferenceEngine
- EdgeImmunityService
- SPREEngine
- ShadowRivalService
- CollapseDecisionAdapter
- CapitalSovereigntyService
- PositionMorphingEngine
- AdaptiveExitAllocator
- SyntheticAffectEngine

Intelligence / context:

- SourceTrustService
- FreshnessNoveltyEngine
- AssetRelevanceMapper
- MarketImpactInterpreter
- PricedInProbabilityEngine
- AdversarialNewsFilter
- DataProvenanceLedger
- ExecutionSimulationSandbox

Learning / forensics:

- EpisodicTradeMemory
- AnalogTradeLookup
- LearningService
- CounterfactualEvaluator
- PnLAttributionService
- LossAutopsyService

Orchestration / operator:

- PaperFlowCoordinator
- ReplayReportingCoordinator
- OperatorSummaryCoordinator
- HumanEscalationLayer
- ObservabilityFacade
- RobotOrchestrator as conductor, not business-logic owner

## Truth ownership discipline

For every changed bounded context, explicitly maintain and document:

- owner of truth
- owner of decisioning
- owner of persistence
- current truth confidence

At minimum this must be explicit for:

- account balances
- positions/inventory
- accepted fills
- fees
- realized PnL
- unrealized PnL
- order lifecycle state
- live gating status
- reconciliation status
- market integrity status
- scenario tree output
- edge immunity evidence
- PnL attribution evidence
- loss autopsy evidence

## High-level decision maps

### Live gating

config unlocked?
-> provider valid?
-> credentials valid?
-> permissions clear?
-> rollout stage allows?
-> truth confidence ok?
-> lifecycle confidence ok?
-> market integrity ok?
-> risk mode allows?
-> yes => allow capital action
-> no => degrade / wait / flatten-only / halt

### Trade permission

candidate trade
-> priced-in check
-> scenario tree check
-> edge immunity check
-> parallel reality dominance check
-> shadow rival check
-> capital sovereignty proposal
-> risk dictatorship veto?
-> execution fragility acceptable?
-> permission_to_trade yes/no

### Exit decision

open position
-> market state update
-> truth confidence update
-> execution quality update
-> scenario branch update
-> keep core?
-> trim satellites?
-> reduce risk?
-> runner allowed?
-> full exit?

### System degradation

weak truth / weak lifecycle / weak market integrity / high stress / high anomaly pressure
-> cautious
-> degraded
-> defensive
-> flatten-only
-> kill-switch

## Required implementation behavior

- Audit first.
- Then implement immediately.
- Do not stop at planning.
- Keep each phase runnable.
- Fix production logic instead of weakening tests.
- Use typed contracts.
- Use explicit invariants.
- Add tests for every critical branch touched.
- Update docs alongside implementation.

## Required reporting after every phase

You must always output:

- files changed
- invariants added
- public contracts preserved
- tests added/updated
- tests run
- failures found
- unresolved risks
- replay/golden changed or unchanged
- truth ownership changed or unchanged
- compatibility shims added or not
- fully implemented / partial / scaffolded items for that phase

## Final quality bar

The system is only considered complete when:

- venue-native unrealized PnL truth is implemented to the maximum safely possible
- exchange-native order lifecycle mirror is materially strong and restart-safe
- Quantum Scenario Engine exists and produces auditable outputs
- Edge Immunity Engine filters fragile trades
- SPRE Engine selects dominant action across realistic future realities
- ARC-style permission-to-trade logic blocks weak trades
- Capital Sovereignty Engine manages capital inside the survival envelope
- Synthetic Affect Engine modulates aggression and caution
- event/internet intelligence filters trust, novelty, and priced-in state
- PnL attribution and loss autopsy are evidence-based
- non-live orchestrator decomposition is completed
- touched tests pass
- full regression passes
- tracked secret scan passes
- replay/golden remains stable unless correctness defect required change
- documentation is complete

# CURSOR MASTER TASK — Autonomous Trading OS

## Objective

Implement the final blueprint as a compatibility-safe, production-grade, fail-closed trading operating system.

Do not rewrite the repository.
Do not stop at planning.
Implement phase by phase, keep the system runnable, and preserve compatibility.

## Primary implementation priorities

1. Market integrity and venue capability truth
2. Venue-native unrealized PnL truth
3. Exchange-native order lifecycle mirror
4. Quantum Scenario Engine
5. Edge Immunity Engine + ARC
6. SPRE Engine + Shadow Rival
7. Capital Sovereignty + Position Morphing
8. Synthetic Affect Engine
9. Event intelligence + priced-in + provenance
10. PnL attribution + loss autopsy
11. Orchestrator decomposition outside live path
12. Final world-class hardening pass

## Detailed phase roadmap

### Phase 0 — Audit and gap map

Tasks:

- map real modules already present
- map existing guardrails
- verify what from the blueprint already exists
- identify provider-specific capabilities
- identify missing bounded contexts
- propose file-by-file target plan
- document baseline and risks

Deliver:

- gap report
- before vs target map
- baseline risks
- initial file list for first implementation wave

### Phase 1 — Market integrity + venue capability + shared limits

Implement:

- MarketIntegrityService
- VenueCapabilityRegistry
- SharedVenueLimitGovernor
- exchange assumptions evidence docs

Tests:

- checksum / sequence / gap handling
- stale feed
- book thinning
- limit governor degradation
- capability mismatch handling

### Phase 2 — Venue-native PnL truth

Implement:

- venue-native unrealized PnL path
- PnL truth classification
- confidence-aware comparison
- runtime degradation under weak truth

Tests:

- authoritative path
- partial path
- unavailable path
- reconciliation degradation
- risk/meta-governor reaction

### Phase 3 — Order lifecycle mirror

Implement:

- lifecycle state machine
- adapter normalization
- idempotency keys
- out-of-order journal
- restart stitching
- orphan/stuck classifier

Tests:

- accepted
- rejected
- partial fill
- full fill
- cancel success
- cancel failure
- replace accepted/rejected
- duplicate event
- out-of-order update
- phantom order protection
- restart stitching

### Phase 4 — Quantum Scenario Engine

Implement:

- state model
- branch tree
- state transition model
- probability field
- interference scoring
- collapse adapter

Tests:

- state output validity
- branch probability normalization
- interference behavior
- no-trade dominance
- compatibility adapter stability

### Phase 5 — Edge Immunity Engine + ARC

Implement:

- counterfactual world generator
- fragility engine
- ghost-twin self-impact
- adversarial attack library
- permission-to-trade gate

Tests:

- spread widening failure
- latency degradation
- partial fill degradation
- self-impact penalty
- weak truth penalty
- robust edge survives path

### Phase 6 — SPRE Engine + Shadow Rival

Implement:

- reality fork generator
- action universe evaluator
- dominance selector
- regret minimizer
- narrative output
- self-shadow rival

Tests:

- action dominance
- regret minimization
- no-trade as optimal action
- shadow rival kill path
- narrative summary integrity

### Phase 7 — Capital Sovereignty + Position Morphing

Implement:

- freedom envelope
- capital sovereignty decisions
- staged/probe entries
- keep-core/sell-satellites
- adaptive exit allocator
- capital rotation engine

Tests:

- size freedom inside envelope
- add/reduce conditions
- runner handling
- risk compression
- capital rotation under superior opportunity

### Phase 8 — Synthetic Affect Engine

Implement:

- confidence/caution/stress/conviction/fear/asymmetry states
- affect modulation rules
- aggression clamps
- no-trade threshold modulation

Tests:

- stress -> downgrade
- caution -> smaller sizing
- confidence + conviction -> controlled expansion
- fear -> strong compression

### Phase 9 — Event intelligence + priced-in layer

Implement:

- source trust
- novelty
- asset relevance
- impact interpreter
- priced-in engine
- adversarial news filter
- provenance ledger

Tests:

- weak source rejection
- novelty scoring
- priced-in degradation
- manipulative narrative detection
- provenance completeness

### Phase 10 — PnL attribution + loss autopsy

Implement:

- attribution pipeline
- autopsy engine
- forensic artifacts
- operator summaries
- replayable autopsy outputs

Tests:

- attribution correctness
- fee/slippage split
- partial/unknown honesty
- autopsy generation
- anomaly forensics

### Phase 11 — Orchestrator decomposition outside live path

Implement:

- paper coordinator
- replay coordinator
- operator summary coordinator
- thinner orchestrator

Tests:

- paper compatibility
- replay/report compatibility
- golden stability
- extracted coordinator outputs

### Phase 12 — Final hardening pass

Implement:

- stronger downgrade under weak truth
- stronger no-trade under ambiguity
- stronger operator forensic outputs
- stronger restart safety
- final docs cleanup

Final validation:

- targeted suites
- full pytest -q
- tracked secret scan
- replay/golden tests
- docs completeness

# Cursor Phase Report

## Phase

[phase number and name]

## Files changed

- ...

## Invariants added

- ...

## Public contracts preserved

- ...

## Tests added or updated

- ...

## Tests run

- ...

## Failures found

- ...

## Unresolved risks

- ...

## Replay/golden changed or unchanged

- ...

## Truth ownership changed or unchanged

- ...

## Compatibility shims added or not

- ...

## Fully implemented items

- ...

## Partially implemented items

- ...

## Scaffolded items

- ...

