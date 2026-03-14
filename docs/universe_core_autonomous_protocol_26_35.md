# Universe Core Autonomous Development Protocol (Window 26-35)

Status: active  
Effective date: 2026-03-12  
Scope: `src/autonomous_investment_robot/services/universe_core/*` and additive adapters around it.

## 1. Purpose

Define a deterministic, replay-safe, rollback-safe protocol for autonomous delivery of Universe Core phases `26..35` without weakening safety controls or replacing the legacy orchestrator authority path.

## 2. Non-Negotiable Constraints

1. Keep hard safety doctrines intact: profit-floor logic, exposure caps, drawdown/risk limits, fail-closed behavior.
2. Keep the manual live gate intact.
3. Do not rewrite or replace `src/autonomous_investment_robot/core/orchestrator.py` as authority path.
4. All changes must be additive, typed, deterministic under replay, bounded-memory, and auditable.
5. No phase may be marked complete without explicit test evidence and rollback notes.

## 3. Truth Baseline (Repository Inspection Snapshot)

As of 2026-03-12:

1. Prior backlog window `10..25` is frozen and complete.
2. A new additive backlog exists for this window:
   - `docs/universe_core_phase_backlog_26_35.json`
3. New additive modules for phases `26..35` are integrated through `UniverseMind` and `UniverseOpsSnapshot`, with strict recommendation-only behavior.
4. Legacy orchestrator remains the authority execution path.

## 4. Phase Order and Priority

Authoritative machine backlog: `docs/universe_core_phase_backlog_26_35.json`.

Execution order policy:

1. Finish all pending work for the earliest dependency-unblocked, highest-impact phase.
2. Never skip dependencies to chase a later phase.
3. For equal score, choose lower phase number.

Default next target after this run: **none (window frozen through Phase 35)**.

## 5. Test and Validation Gates

Every completed phase run in this window must include:

1. Focused phase gate from backlog entry (`pytest -q tests/test_universe_program_window_26_35.py -k phase<N>`).
2. Full suite gate:
   - `pytest -q`
3. Fail-closed behavior must remain intact in existing safety and live-gate paths.

## 6. Completion Standard

A phase can be marked `completed_additive` only when all are true:

1. Scope done against phase objective in backlog.
2. Focused tests pass.
3. Full test suite passes.
4. Safety/manual gate semantics are preserved or strengthened.
5. Strict report exists under `docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md`.
6. Backlog status is updated truthfully.

## 7. Report Convention

Each strict report must include:

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
3. `docs/live_readiness_checklist.md`
4. `docs/operator_runbook.md`
