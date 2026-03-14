# Universe Core Autonomous Development Protocol (Window 36-50)

Status: active  
Effective date: 2026-03-12  
Scope: additive Universe Core intelligence modules and adapters under `src/autonomous_investment_robot/services/universe_core/*`.

## 1. Purpose

Define a deterministic, replay-safe, rollback-safe delivery protocol for Universe Core phases `36..50`, continuing the system toward institutional-grade autonomous capital intelligence without weakening existing hard safety doctrines.

## 2. Non-Negotiable Constraints

1. Keep hard safety doctrines intact: profit-floor logic, exposure caps, drawdown/risk limits, fail-closed behavior.
2. Keep the manual live gate intact.
3. Do not rewrite or replace `src/autonomous_investment_robot/core/orchestrator.py` authority path.
4. All changes must be additive, typed, deterministic under replay, bounded-memory, and auditable.
5. No phase may be marked complete without focused tests, full `pytest -q`, rollback notes, and strict report evidence.

## 3. Truth Baseline (Repository Inspection Snapshot)

As of 2026-03-12:

1. Program window `26..35` is implemented and revalidated green.
2. Source-of-truth regression gates executed in this run:
   - `pytest -q tests/test_universe_program_window_26_35.py -k 'phase29 or phase32 or phase34'`
   - `pytest -q tests/test_universe_program_window_26_35.py`
   - `pytest -q`
3. Legacy orchestrator remains the only live execution authority path.
4. Window `36..50` starts from additive advisory intelligence and may graduate only through existing ops/manual gate process.

## 4. Authoritative Backlog

Machine backlog file: `docs/universe_core_phase_backlog_36_50.json`.

Execution order policy:

1. Choose highest score among dependency-unblocked phases.
2. If equal score, choose lower phase number.
3. If a safety blocker is unresolved, phase remains `active_hardening` or `blocked` and cannot be marked complete.

## 5. Required Validation Gates

Each completed phase in this window must include:

1. Focused phase tests in `tests/test_universe_program_window_36_50.py` (or explicitly listed phase-specific tests).
2. `pytest -q tests/test_universe_program_window_26_35.py`.
3. `pytest -q`.
4. No regression of manual live gate or hard safety paths.

## 6. Strict Completion Standard

A phase can be marked `completed_additive` only when all are true:

1. Objective and contracts implemented in listed repo anchors.
2. Acceptance criteria met with deterministic evidence.
3. Mandatory test gates pass.
4. Rollout constraints and live-gate requirements are preserved.
5. Strict completion report exists: `docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md`.
6. Backlog status and `recommended_next_phase` are updated truthfully.

## 7. Report Convention

Every strict report for phases `36..50` must include:

1. `inspection_findings`
2. `files_changed`
3. `modules_fully_implemented`
4. `modules_partial`
5. `missing_or_blocked`
6. `tests_added`
7. `test_results`
8. `runtime_safety_impact`
9. `rollback_readiness`
10. `rollout_readiness`
11. `next_phase_recommendation`
12. `completion_status`

## 8. References

1. `docs/universe_core_program.md`
2. `docs/universe_core_phase_backlog_26_35.json`
3. `docs/universe_core_phase_backlog_36_50.json`
4. `docs/live_readiness_checklist.md`
5. `docs/operator_runbook.md`
