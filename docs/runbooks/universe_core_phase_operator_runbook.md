# Universe Core Phase Operator Runbook

## Purpose

Operator checklist for monitoring, reviewing, and checkpointing each completed Universe Core phase without weakening safety or manual live controls.

## 1. Pre-Phase Check

1. Confirm target phase from `docs/universe_core_phase_backlog_10_25.json`.
2. Confirm all dependencies for that phase are `completed_additive`.
3. Record baseline:
   - current git commit
   - latest strict completion report
   - current runbook checklist date/time
4. Run baseline safety checks:

```bash
python3 scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper
python3 scripts/runtime_audit.py --runs-root runs --event-limit 3000
```

## 2. During Implementation Monitoring

1. Keep scope constrained to the selected phase and additive adapters.
2. Watch for safety regressions in changed modules:
   - profit floor behavior
   - exposure/risk caps
   - manual live gate behavior
3. Maintain observability evidence in run artifacts (`audit.log`, `event_bus.jsonl`, governance snapshots).

## 3. Phase Review Gate

Run required gates for the phase (from backlog). Minimum common gate:

```bash
python3 -m py_compile <changed_python_files>
pytest -q <phase_targeted_tests>
```

If rollout/distributed behaviors were touched:

```bash
./scripts/validate_compose_runtime.sh
./scripts/smoke_test_live_compute_roundtrip.sh
python3 scripts/runtime_audit.py --runs-root runs --event-limit 3000
```

## 4. Completion Checkpoint

A phase can be checkpointed only when:

1. Mandatory tests pass.
2. Hard safety invariants remain intact.
3. Manual live gate remains required.
4. Strict report exists at `docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md`.
5. Backlog JSON status is updated truthfully.

Checkpoint outputs:

1. commit with phase convention.
2. annotated phase tag (only if complete, not blocked).
3. link to report + test output summary.

## 5. Blocked Phase Procedure

1. Mark status as blocked in report and backlog.
2. Record blocker class (`safety`, `dependency`, `infra`, `scope`) and failing gate.
3. Do not force completion.
4. Recommend the smallest safe unblock action.

## 6. Rollback Readiness Check

Before live-candidate claims:

1. Verify `rollout_governance.decision.approved == true`.
2. Verify `production_readiness.rollback_ready == true`.
3. Verify rollback dry-run status is explicitly recorded.
4. Verify manual controls:
   - `AUTONOMOUS_LIVE_GO=1`
   - operator confirmation artifact file exists

## 7. Operator Phase Note Template

```text
phase: <N>
timestamp_utc: <ISO8601>
status: <completed_additive|blocked>
tests: <commands + pass/fail>
safety_impact: <none|details>
rollback_status: <ready|blocked + reason>
manual_live_gate: <unchanged|details>
report_path: docs/reports/PHASE_<N>_STRICT_COMPLETION_REPORT.md
next_recommended_phase: <N+1 or other>
```
