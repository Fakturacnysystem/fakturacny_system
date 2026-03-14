# Universe Core Autonomous Development Protocol

Status: active  
Effective date: 2026-03-11  
Scope: `src/autonomous_investment_robot/services/universe_core/*` and additive adapters around it.

## 1. Purpose

Define a deterministic, replay-safe, rollback-safe protocol for autonomous phase-by-phase delivery of Universe Core without weakening safety controls or replacing the legacy orchestrator authority path.

## 2. Non-Negotiable Constraints

1. Keep hard safety doctrines intact: profit-floor logic, exposure caps, drawdown/risk limits, fail-closed behavior.
2. Keep the manual live gate intact.
3. Do not rewrite or replace `src/autonomous_investment_robot/core/orchestrator.py` as authority path.
4. All changes must be additive, typed, deterministic under replay, bounded-memory, and auditable.
5. No phase may be marked complete without explicit test evidence and rollback notes.

## 3. Truth Baseline (Repository Inspection Snapshot)

As of 2026-03-11:

1. Universe Core modules exist and are active in additive path:
   - `events.py`, `state.py`, `mission.py`, `parliament.py`, `execution.py`, `execution_intel.py`, `shield.py`, `memory.py`, `replay_ladder.py`, `ops.py`, `service.py`.
2. Focused phase tests exist through Phase 25:
   - `tests/test_universe_core.py`
   - `tests/test_universe_shield_phase6.py`
   - `tests/test_universe_memory_phase7.py`
   - `tests/test_universe_replay_phase8.py`
   - `tests/test_universe_execution_phase9.py`
   - `tests/test_universe_ops_phase10.py`
   - `tests/test_orchestrator_universe_allowlist.py`
   - `tests/test_autonomous_decision_engine.py`
   - `tests/test_causal_market_twin_engine.py`
   - `tests/test_incident_policy_phase3.py`
   - `tests/test_phase1_policy_regime.py`
   - `tests/test_universe_meta_intelligence.py`
   - `tests/test_risk_live_guard.py`
   - `tests/test_watchdog_supervisor.py`
   - `tests/test_ops_evidence_snapshot.py`
3. Strict completion reports exist for phases 5/6/8/9/10/11/12/13/14/15/16/17/18/19/20/21/22/23/24/25 under `docs/reports/`.
4. Legacy orchestrator remains the authority path, with additive adapters available behind env gates:
   - shadow-only `UniverseMind` adapter (`AUTONOMOUS_UNIVERSE_SHADOW_ENABLED`)
   - legacy producer canonical-envelope mirror (`AUTONOMOUS_UNIVERSE_EVENT_ADAPTER_ENABLED`)
5. Runbook/checklist docs already exist for safety and distributed rollout:
   - `docs/live_readiness_checklist.md`
   - `docs/distributed_acceptance_checklist.md`
   - `docs/operator_runbook.md`

## 4. Phase Order and Priority

Authoritative machine backlog: `docs/universe_core_phase_backlog_10_25.json`.

Execution order policy:

1. Finish all pending work for the earliest dependency-unblocked, highest-impact phase.
2. Never skip a dependency to chase a later phase.
3. For equal score, choose lower phase number.

Default next target after this protocol setup: **none (roadmap window frozen through Phase 25)**.

## 5. Autonomous Run Loop

For each autonomous run:

1. Load truth inputs:
   - `docs/universe_core_phase_backlog_10_25.json`
   - latest `docs/reports/PHASE_*_STRICT_COMPLETION_REPORT.md`
   - `docs/live_readiness_checklist.md`
2. Select next phase using Section 11 scoring.
3. Implement minimal additive changes for that phase only.
4. Run mandatory gates from backlog phase entry.
5. If gates pass, write strict completion report and update backlog status.
6. Create commit + tag using Section 10 convention.
7. If gates fail, publish a blocked report (do not claim completion).

## 6. Phase Completion Standard

A phase can be marked `completed_additive` only when all are true:

1. Scope done against phase `done_when` criteria in backlog.
2. Required tests/validations for that phase pass.
3. Hard safety and manual live gate behavior unchanged or strengthened.
4. Replay determinism claims are backed by tests or reproducible checks.
5. Rollback path is explicit and tested or explicitly classified as blocked.
6. Strict report exists at `docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md`.
7. Backlog JSON status + evidence fields are updated truthfully.

## 7. Blocker Handling Rules

Blocker classes:

1. `safety_blocker`: any change would weaken hard safety/manual live gate.
2. `dependency_blocker`: required upstream phase artifact is missing.
3. `infra_blocker`: host/runtime limitation (for example docker unavailable).
4. `scope_blocker`: requested phase conflicts with non-negotiable constraints.

Required behavior:

1. Stop implementation at blocker boundary.
2. Produce a strict blocked report with:
   - blocker class
   - exact failing gate/command
   - smallest safe next action
3. Do not bypass by weakening invariants or broad rewrites.

## 8. Test Gates and Validation Gates

Every phase run must include:

1. `T0` syntax/type gate (changed Python modules):
   - `python3 -m py_compile <changed_files>`
2. `T1` focused phase tests from backlog entry.
3. `T2` safety regression gates:
   - `pytest -q tests/test_risk_live_guard.py tests/test_profit_gate.py tests/test_runtime_audit.py`
   - if touched scope intersects those domains.
4. `T3` full suite gate:
   - `pytest -q`
   - required for final phase completion claims unless pre-existing unrelated failures are proven.
5. `T4` operational validation (when phase affects rollout/distributed/runtime):
   - `python3 scripts/runtime_audit.py --runs-root runs --event-limit 3000`
   - `./scripts/validate_compose_runtime.sh`
   - distributed smokes where applicable.

## 9. Rollout Safety Gates

No rollout claim above paper/shadow unless all pass:

1. Manual live gate:
   - `AUTONOMOUS_LIVE_GO=1`
   - confirmation artifact at `AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE`
2. Universe Core governance gate:
   - `ops_snapshot.rollout_governance.decision.approved == true`
   - `ops_snapshot.rollout_stage != "blocked"`
3. Production readiness artifact gate:
   - required checklist items in `ops_snapshot.production_readiness.checklist` are passed.
4. Runtime invariants:
   - no fatal invariant breaches
   - no `profit_lock_sell_below_entry`
   - no `profit_lock_sell_below_min_profit`
   - effective `sell_min_profit_bps >= 120`

## 10. Required Report, Commit, and Tag Convention

For each phase run:

1. Report path:
   - `docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md`
2. Report sections (minimum):
   - `inspection_findings`
   - `files_changed`
   - `modules_fully_implemented`
   - `modules_partial`
   - `missing_or_blocked`
   - `tests_added`
   - `test_results`
   - `runtime_safety_impact`
   - `rollback_readiness`
   - `rollout_readiness`
   - `next_phase_recommendation`
3. Commit message:
   - `phase<N>(universe-core): <truthful additive summary>`
4. Annotated tag (only on completed phase):
   - `universe-core/phase-<NN>/<YYYYMMDD-HHMMSS>`
   - Tag body includes report path and completion status.
5. If blocked:
   - no completion tag
   - commit message prefix `phase<N>-blocked: ...`

## 11. Deterministic Next Highest-Impact Phase Selection

Selection source: backlog JSON fields.

Filter:

1. `status` in `{pending, active_hardening}`.
2. all dependencies resolved (`status == completed_additive`).

Score:

`score = impact + unblock_value + safety_value - effort_cost - blocker_risk`

Tie-breakers:

1. smaller `phase_number`
2. larger `safety_value`

Chosen phase must be recorded in the strict report with computed score inputs.

## 12. References

1. `docs/universe_core_program.md`
2. `docs/reports/PHASE_10_STRICT_COMPLETION_REPORT.md`
3. `docs/live_readiness_checklist.md`
4. `docs/distributed_acceptance_checklist.md`
5. `docs/operator_runbook.md`
