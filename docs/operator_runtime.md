# Operator Runtime Guide

## Key run artifacts
Each run directory now includes:
- `config_manifest.jsonl`
- `events_account.jsonl`
- `truth_confidence_journal.jsonl`
- `signal_journal.jsonl`
- `policy_journal.jsonl`
- `execution_journal.jsonl`
- `fills_journal.jsonl`
- `accounting_truth_journal.jsonl`
- `health_journal.jsonl` (live loop)
- `meta_governor_journal.jsonl`
- `control_journal.jsonl`
- `recovery_journal.jsonl`
- `reconciliation_journal.jsonl`
- `quantum_state_journal.jsonl` (live loop)
- `edge_immunity_journal.jsonl` (live loop)
- `market_integrity_journal.jsonl` (live loop)
- `market_integrity_evidence_journal.jsonl` (live loop)
- `venue_limit_journal.jsonl` (live loop)
- `mastermind_journal.jsonl`
- `spre_journal.jsonl`
- `shadow_rival_journal.jsonl`
- `decision_doctrine_journal.jsonl`
- `execution_simulation_journal.jsonl`
- `human_escalation_journal.jsonl`
- `pnl_attribution.jsonl`
- `loss_autopsy.jsonl`
- `post_trade_summary.jsonl`
- `loss_review_summary.jsonl`
- `provider_capability_journal.jsonl`
- `analog_trade_lookup.jsonl`
- `counterfactual_review.jsonl`
- `trade_episode_memory.jsonl`
- `calibration_profile.json`
- `decision_doctrine_summary.jsonl`
- `mastermind_summary.jsonl`
- `learning_records.jsonl`
- `portfolio_ledger.json`
- existing metrics, report, fills, trade log, and checksum artifacts

These files are append-only evidence for replay, reject autopsy, and loss review.

## Quantum + edge immunity
- `quantum_state_service` is a heuristic probabilistic layer. It models multiple market branches, branch probabilities, interference, and a collapse-to-action recommendation.
- `edge_immunity_service` is a deterministic stress layer. It evaluates whether the current thesis survives counterfactual spread/depth/adverse-move worlds and whether waiting dominates trading now.
- `spre_service` is a heuristic parallel-reality dominance layer. It compares `trade_now`, `trade_smaller`, `probe`, `wait`, and `no_trade` across richer reality forks including integrity breaks, priced-in fades, execution breaks, stale-signal chop, and squeeze extension.
- `shadow_rival_service` is a heuristic adversarial critic. It reviews SPRE dominance, failure clusters, ambiguity gap, survival ratio, and execution/event break paths before it keeps size small, waits, or vetoes.
- `capital_sovereignty_service`, `position_morphing_service`, and `adaptive_exit_allocator` reshape whether to allocate, how to stage, and how to release/rotate capital inside a hard survival envelope.
- `synthetic_affect_service` is a synthetic regulation layer. It modulates caution, stress, conviction, fear, and aggression clamp without replacing policy or bypassing risk.
- `event_intelligence_service` composes source trust, freshness/novelty, asset relevance, market impact, priced-in probability, adversarial narrative filtering, and provenance into one evidence report.
- `execution_simulation_sandbox` stress-tests the current trade idea across execution worlds before final decision collapse.
- `mastermind_service` is now a bounded-safe top-logic advisor, not a noop stub. It evaluates whether the current setup is robust enough to continue, should be probed, should trade smaller, should wait, or should be vetoed entirely. It can only reduce aggression or block action.
- `execution_service` now reads doctrine context from the final decision path, so probe entries, trade-smaller decisions, partial-truth degradations, and forced exits produce different execution styles instead of reusing one local planner shape.
- `human_escalation_layer` raises manual-review or flatten-only decisions when module disagreement or uncertainty becomes too severe.
- manual-review or flatten-only escalation now also writes `MANUAL_REVIEW_REQUIRED.json` into the run directory so operator intervention is explicit even outside journal inspection.
- `forensics_service` now also persists episodic memory, analog lookups, counterfactual reviews, and heuristic calibration profiles derived from recent outcomes.
- Both layers currently influence live policy as additive evidence only.
- They do not bypass risk, live gating, accounting truth, or reconciliation.
- Legacy paper checksum payloads remain unchanged.

Operator interpretation:
- `quantum_state_journal.jsonl`: inspect dominant state, no-trade probability, uncertainty, and execution fragility.
- `edge_immunity_journal.jsonl`: inspect edge survival ratio, fragility index, self-impact penalty, wait value, and recommended execution style.
- `policy_journal.jsonl`: inspect `spre` and `shadow_rival` sections for parallel-reality dominance, regret, critique score, and veto/size-cut reasons.
- `mastermind_journal.jsonl`: inspect the bounded-safe advisory verdict, risk level, size multiplier, execution-style bias, and raw fragility/truth/integrity components.
- `decision_doctrine_journal.jsonl`: inspect the top-level doctrine verdict for recommended action, size multiplier, truth strength, survival score, robustness score, execution survivability, capital freedom, partial-truth penalty, uncertainty pressure, and regret pressure.
- `market_integrity_journal.jsonl`: inspect integrity score, fail-closed action (`continue` / `degrade` / `flatten_only` / `halt`), and feed/book/capability stress reasons.
- `venue_limit_journal.jsonl`: inspect venue-driven size caps and reduce-only escalation derived from integrity plus provider capability truth.
- `provider_capability_journal.jsonl`: inspect venue-specific truth support, lifecycle completeness, replace/expire support, and user-stream confidence.
- `spre_journal.jsonl`: inspect dominant parallel-reality action, internal action universe ranking, survival ratio, dominance gap, dominant failure modes, and fork narrative.
- `shadow_rival_journal.jsonl`: inspect adversarial critique, thesis-break score, ambiguity score, kill-path score, survival ratio, and veto/size-cut reasons.
- `execution_simulation_journal.jsonl`: inspect stressed fill probability, worst-case costs, and execution-style recommendation.
- `execution_journal.jsonl`: inspect `global_execution_adjustments` to see how doctrine changed style, participation, blocking, or forced-exit posture.
- `human_escalation_journal.jsonl`: inspect disagreement score, severity, and manual-review vs flatten-only escalation.
- `MANUAL_REVIEW_REQUIRED.json`: current blocking manual-review or flatten-only marker for the run.
- `MANUAL_REVIEW_ACK.json`: explicit operator acknowledgment artifact for a matching `manual_review` decision key. It never clears `flatten_only`.
- `source_trust_journal.jsonl`, `freshness_novelty_journal.jsonl`, `asset_relevance_journal.jsonl`, `market_impact_journal.jsonl`, `priced_in_journal.jsonl`, `adversarial_narrative_journal.jsonl`, `data_provenance_journal.jsonl`: inspect the decomposed event-intelligence evidence rather than only the aggregate decision.
- `profitability_journal`: inspect round-trip net edge, reserve breach, stale inventory pressure, and capital-release preference.
- `pnl_attribution.jsonl`: inspect where realized PnL came from.
- `loss_autopsy.jsonl`: inspect evidence-based loss or anomaly reports.
- `post_trade_summary.jsonl`: quick operator-facing realized outcome summary.
- `loss_review_summary.jsonl`: concise severity and recommendation record for loss/anomaly review.
- `trade_episode_memory.jsonl`: inspect persisted episode-level setup, regime, truth state, execution state, and result.
- `analog_trade_lookup.jsonl`: inspect nearest remembered analogs for each reviewed trade.
- `counterfactual_review.jsonl`: inspect chosen action vs strongest alternative and realized/avoided regret.
- `calibration_profile.json`: inspect current heuristic bias adjustments derived from recent episode outcomes.
- `decision_doctrine_summary.jsonl`: inspect the operator-facing doctrine summary with truth, market integrity, provider capability, and final doctrine verdict in one place.
- `mastermind_summary.jsonl`: inspect the operator-facing bounded-safe advisory summary without digging through lower-level journals.

## Risk modes
`RiskEngineService` now reports one of:
- `normal`
- `cautious`
- `degraded`
- `defensive`
- `flatten-only`
- `kill-switch`

Interpretation:
- `normal`: trading permitted under configured limits
- `cautious`: size throttled
- `degraded`: runtime quality problem; size reduced and operator attention required
- `defensive`: safe-mode style posture
- `flatten-only`: no new opens; only reduction should be allowed
- `kill-switch`: trading halted, flatten expected

## Rollout ladder
- `paper`: offline deterministic execution only.
- `shadow`: operator-facing rollout stage resolved from `execution.mode=live_readonly`; market access and preflight only, no order placement.
- `tiny_live`: explicit rollout stage on `execution.mode=live`; ordering allowed only after double unlock and valid provider/risk config.
- `limited_live`: maps to `live` with canary-style profile (`canary` run dir or small base risk budget).
- `normal_live`: maps to full `live` after canary controls and testnet validation.

Promotion is manual by config/profile choice. Downgrades are automatic through preflight failure, restart-state confidence, risk mode, reconciliation outcomes, and health score.

`canary_live` is an additive rollout alias used by the meta-governor and operator reporting. It is derived from
the current compatible live profile (`canary_mode=true`, `run_dir` containing `canary`, or equivalent small-budget profile).
No existing CLI mode changed.

Additive performance systems visible in runtime API and RCC remain non-authoritative unless `LIVE_AUTHORITY_BOUNDARY.md` and `PROMOTION_GATES.md` explicitly say otherwise.

## Restart-state confidence
At live boot, the runtime now rehydrates local state from run artifacts and compares it with exchange positions/open orders.

- `trusted`: local mirror and exchange are consistent enough to continue.
- `degraded`: history exists but local and exchange state differ materially; trading can continue only under explicit degraded visibility.
- `insufficient`: exchange shows open risk without matching local history; runtime enters `flatten_only` and blocks new opens.

Recovery artifacts:
- `recovery_journal.jsonl`: boot outcome, duplicate suppression, orphan-order sweep, recovered order counts
- `truth_confidence_journal.jsonl`: per-domain truth confidence snapshot written at boot and reconciliation time

## Live ledger behavior
- Live adapters fetch exchange-native history before they write fill, fee, or realized-PnL truth into the local ledger.
- If a live order reports `filled_*` but exchange-native fill history is missing or ambiguous, the runtime emits `LIVE_FILL_TRUTH_GAP`, keeps local exposure unchanged, and downgrades to `flatten_only`.
- If exchange-native fee or realized-PnL history is missing for an accepted live fill, the runtime records the fill, emits the specific gap event, and downgrades to `flatten_only` so accounting cannot continue silently degraded.
- Restart rehydration can recover missing local fill history from exchange-native trade history and records `FILL_REHYDRATED_FROM_EXCHANGE` evidence when it does so.

Truth ownership vs current truth confidence:
- owner of truth answers "which subsystem is canonical when the domain is available"
- truth confidence answers "how much we trust the currently available evidence on this run"
- `truth_confidence_journal.jsonl` is the operator-facing record for this distinction

## No-trade reason codes
Structured no-trade decisions currently emit codes such as:
- `no_signals`
- `no_edge_after_costs`
- `confidence_guard`
- `execution_quality_bad`
- `liquidity_too_thin`
- `regime_unfavorable`
- `quantum_no_trade`
- `quantum_signal_conflict`
- `execution_fragility`
- `edge_fragility`
- `wait_dominance`
- `round_trip_profitability_guard`
- `wait_for_better_round_trip`
- `capital_release_priority`
- `decision_doctrine_no_trade`
- `decision_doctrine_wait`

Legacy paper execution still uses the historical trade/no-trade path to preserve replay stability, but the journals record the richer decision context.

## Operator checks before any live escalation
1. Run `pytest -q`.
2. Confirm readonly/testnet preflight passes.
3. Confirm `config_manifest.jsonl` shows the expected provider, runtime mode, and rollout stage.
4. Confirm no `TRUTH_OWNERSHIP_INVALID` event exists.
5. Confirm `truth_confidence_journal.jsonl` shows no `unavailable` level for fills, fees, realized PnL, balances, or exposure in the intended live run.
6. Confirm `LIVE_GATE_STATUS` shows `ordering_allowed=true` only in the intended live stage.
7. Confirm `reconciliation_journal.jsonl` stays in `continue` or `alert`, not `degrade`, `flatten_only`, `halt`, or `halt_and_flatten`.
8. Confirm `meta_governor_journal.jsonl` and `control_journal.jsonl` do not show forced downgrade actions for the intended live symbol/profile.
9. Confirm restart-state confidence is not `insufficient`.
10. Confirm no `LIVE_FILL_TRUTH_GAP`, `LIVE_FEE_TRUTH_GAP`, or `LIVE_REALIZED_PNL_TRUTH_GAP` events exist in the intended live run.
11. If `MANUAL_REVIEW_REQUIRED.json` exists with `action=manual_review`, acknowledge it explicitly before resuming opens:
   `PYTHONPATH=src python3 -m autonomous_investment_robot ack-review --run-dir <run_dir> --reviewer <name> --notes "<reason>"`

## Known live gaps
- Live unrealized PnL is still locally derived and checked against exchange position marks rather than sourced from a dedicated exchange PnL ledger.
- Kraken fill/fee/realized-PnL truth depends on the exchange history endpoints remaining available and internally consistent; ambiguity forces `flatten_only`.
- Quantum state and edge-immunity outputs are heuristic probabilistic baselines. They are explainable and testable, but they are not trained ML models and are not yet calibration-proven across long historical windows.
- Because of that, live mode should still be treated as guarded and operator-observed rather than fully autonomous.

## Rollback posture
- The CI workflow fails on test regressions and tracked-file secret signatures.
- The CI workflow now also validates Python compilation, config matrix loading, and tracked deployment manifest syntax.
- The paper replay golden test protects deterministic strategy-plan drift.
- Rich journals are kept separate from legacy checksum payloads so new observability does not silently alter replay baselines.
- Proof-only delivery helpers now exist for rollback pack creation and incident review template generation:
  - `./scripts/build_rollback_pack.sh`
  - `./scripts/generate_incident_review_template.py`
- Contradiction audit:
  - `./scripts/run_contradiction_audit.py`
  - verifies profitability vs risk wiring, OMS vs lifecycle mirror, lifecycle vs reconciliation, quantum policy hooks, edge vs execution planner, forensics journals, operator summaries, and replay fixture presence
