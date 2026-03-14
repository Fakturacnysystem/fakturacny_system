# ULTRA FOCUS ULTIMATE PROFIT ACTIVATION REPORT

## 1. inspection_findings
- Repository inspected from current working tree and latest evidence bundles.
- Phase backlog 36..50 remains marked complete-additive (recommended_next_phase: null).
- Full suite before activation work was green and remained green after hardening changes.
- Latest activation workspace: runs/post_ultra_activation_20260312T192634Z.

## 2. readiness_preconditions_status
- readiness ladder baseline available: PASS
- full pytest green: PASS (537 passed, 1 skipped)
- runtime audit green on strongest safe path: PASS (perps post-soak system_state=OK)
- unresolved invariant failures: PASS (none)
- unresolved drift failures: PASS (drift_failures=0 in config matrix)
- replay determinism intact: PASS (tests and replay command outputs present)
- paper/readonly/replay telemetry analyzable: PASS
- canary envelope/governance evidence complete: PARTIAL (code/docs present; no new live canary activation evidence in this run)
- manual live gate enforced: PASS
- dual-control enforced: PASS
- rollback dry-run valid: PASS (paper preflight rollback validated)
- residual risk explicit: PASS (safety/live preflight blockers explicit)
- affordability tuning evidence-backed: PASS (analysis artifacts generated)
- true ultimate activation support evidence: FAIL (live preflight still blocked)

## 3. selected_profit_profile
- Selected profile: config.perps_intraday.paper.yaml in bounded paper soak mode.
- Why selected: both stronger profit scripts (ULTRA and PROFIT) were fail-closed blocked (allowlist_empty_after_filter) under safe paper activation.

## 4. rejected_profile_options_and_reasons
- ULTRA_PROFIT_FULL_THROTTLE (forced-safe paper): REJECTED
  - run status rc=2
  - runtime health reason allowlist_empty_after_filter
- PROFIT_FULL_THROTTLE (forced-safe paper): REJECTED
  - run status rc=2
  - runtime health reason allowlist_empty_after_filter
- ULTRA with explicit allowlist override: REJECTED
  - remained blocked allowlist_empty_after_filter

## 5. activation_mode_used
- strongest safe bounded mode used: paper soak
- command: .venv/bin/python -m cli.run --config config.perps_intraday.paper.yaml --paper --nonstop --max-restarts 0
- bounded by external timeout: 120s.

## 6. commands_run
- .venv/bin/python -m py_compile scripts/runtime_audit.py scripts/analyze_affordability_pressure.py tests/test_runtime_audit.py tests/test_live_profit_symbol_fixtures.py tests/test_affordability_pressure_analysis.py
- .venv/bin/pytest -q tests/test_runtime_audit.py tests/test_live_profit_symbol_fixtures.py tests/test_affordability_pressure_analysis.py
- .venv/bin/pytest -q
- .venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper --output runs/post_ultra_activation_20260312T192634Z/artifacts/rollback_preflight_liveprofit_paper.json
- .venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode live --output runs/post_ultra_activation_20260312T192634Z/artifacts/safety_preflight_live_target.json
- .venv/bin/python scripts/audit_config_matrix.py --json-output runs/post_ultra_activation_20260312T192634Z/artifacts/config_matrix_audit.json --md-output runs/post_ultra_activation_20260312T192634Z/artifacts/config_matrix_audit.md
- .venv/bin/python scripts/validate_deployment_manifests.py --runtime-evidence-run-dir /Users/martinholik/Projects/fakturacny_system/runs/kraken_spot_live_profit09
- ./scripts/validate_compose_runtime.sh
- AUTONOMOUS_LIVE_GO=0 AUTONOMOUS_PAPER_CONFIG=/tmp/candidate_ultra_paper_config.json ./scripts/run_kraken_ultra_profit_full_throttle.sh
- AUTONOMOUS_LIVE_GO=0 AUTONOMOUS_PAPER_CONFIG=/tmp/candidate_profit_paper_config.json ./scripts/run_kraken_spot_profit_full_throttle.sh
- AUTONOMOUS_LIVE_GO=0 AUTONOMOUS_PAPER_CONFIG=/tmp/candidate_ultra_paper_config.json AUTONOMOUS_UNIVERSE_ALLOWLIST=... AUTONOMOUS_DYNAMIC_UNIVERSE=false AUTONOMOUS_DYNAMIC_UNIVERSE_ALL=false ./scripts/run_kraken_ultra_profit_full_throttle.sh
- .venv/bin/python -m cli.run --config config.perps_intraday.paper.yaml --paper --once
- .venv/bin/python -m autonomous_investment_robot replay --config config.kraken_spot.live_readonly.yaml --source recordings
- .venv/bin/python -m autonomous_investment_robot replay --config config.perps_intraday.paper.yaml --source fixtures
- .venv/bin/python scripts/runtime_audit.py --run-dir runs/profit_activation_ultra_candidate_paper --event-limit 3000 --output runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_ultra_candidate.json
- .venv/bin/python scripts/runtime_audit.py --run-dir runs/profit_activation_profit_candidate_paper --event-limit 3000 --output runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_profit_candidate.json
- .venv/bin/python scripts/runtime_audit.py --run-dir runs/perps_intraday --event-limit 3000 --output runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_perps_intraday_post_soak.json
- .venv/bin/python scripts/analyze_affordability_pressure.py --run-dir runs/profit_activation_ultra_candidate_paper --runtime-audit runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_ultra_candidate.json --output runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_ultra_candidate.json
- .venv/bin/python scripts/analyze_affordability_pressure.py --run-dir runs/profit_activation_profit_candidate_paper --runtime-audit runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_profit_candidate.json --output runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_profit_candidate.json
- .venv/bin/python scripts/analyze_affordability_pressure.py --run-dir runs/perps_intraday --runtime-audit runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_perps_intraday_post_soak.json --output runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_perps_intraday_post_soak.json

## 7. telemetry_artifacts_captured
- bundle root: runs/post_ultra_activation_20260312T192634Z
- artifacts index: runs/post_ultra_activation_20260312T192634Z/artifacts/execution_artifact_index.txt
- checksums: runs/post_ultra_activation_20260312T192634Z/artifacts/artifact_checksums.sha256
- candidate run statuses:
  - runs/post_ultra_activation_20260312T192634Z/artifacts/candidate_run_status.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/perps_soak_status.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/ultra_candidate_allowlist_status.json
- runtime audits:
  - runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_kraken_spot_live_profit09.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_ultra_candidate.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_profit_candidate.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/runtime_audit_perps_intraday_post_soak.json
- affordability diagnostics:
  - runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_ultra_candidate.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_profit_candidate.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/affordability_perps_intraday_post_soak.json
- replay outputs:
  - runs/post_ultra_activation_20260312T192634Z/artifacts/replay_recordings_live_readonly.json
  - runs/post_ultra_activation_20260312T192634Z/artifacts/replay_fixtures_perps_paper.json

## 8. activation_results
- ULTRA candidate: blocked, no orders submitted, reason allowlist_empty_after_filter.
- PROFIT candidate: blocked, no orders submitted, reason allowlist_empty_after_filter.
- Perps bounded soak: command ran for bounded window; post-soak runtime evidence in runs/perps_intraday shows order flow present via event files.

## 9. profit_profile_evaluation
- Candidate profile comparison result: regressed / not activatable for ULTRA and PROFIT (blocked at start).
- Strongest safe active profile result: conditionally acceptable on perps paper path.
- Evidence summary:
  - runs/perps_intraday post-soak runtime audit: system_state=OK
  - order_stats_source=events_files
  - submitted_orders=1500, hard_invariants.ok=true
  - guardrails remain strict and sell profit floor remains compatible.

## 10. fail_closed_decision
- Decision: Reject stronger ULTRA/PROFIT activation in current state.
- Accepted mode: stay on strongest lower safe mode (perps paper bounded/controlled).
- Reason: stronger modes failed activation gate with deterministic blocker allowlist_empty_after_filter.

## 11. runtime_safety_status
- hard invariants remained clean:
  - profit_lock_sell_below_entry=0
  - profit_lock_sell_below_min_profit=0
- manual live gate and dual-control were not bypassed.
- live target preflight remained fail-closed as expected.

## 12. rollback_readiness
- paper rollback dry-run validated (validated=true).
- artifact id captured in rollback preflight output.

## 13. remaining_blockers_to_true_ultimate_profit
- live preflight blockers remain:
  - missing configured live credentials/testnet flag/live go
  - manual gate unsatisfied
  - manual dual-control unsatisfied
- ULTRA/PROFIT paper candidate blockers:
  - allowlist_empty_after_filter under current candidate setup
- live-profit affordability pressure remains dominant on spot profile (entry_insufficient_quote).

## 14. recommended_next_tuning_loop
1. Resolve allowlist_empty_after_filter in ULTRA/PROFIT paper candidate path with explicit, deterministic tradable universe policy for safe paper mode.
2. Add profile-specific smoke test asserting non-empty tradable universe before activation command.
3. Continue affordability tuning loop on spot paper with bounded adjustments only (quote buffers/cadence) and before/after audits.
4. Re-run ULTRA candidate only after (1) and (2) pass with green focused tests.
