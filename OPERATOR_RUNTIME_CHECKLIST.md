# Operator Runtime Checklist

## Startup validation

1. Run `python3 scripts/validate_config_matrix.py`.
2. Confirm config stage matches intended runtime:
   - readonly analysis: `live_readonly` + `shadow`
   - tiny live: `live` + `tiny_live`
   - limited live: `live` + `limited_live`
3. Confirm `minimum_sell_net_profit_bps >= 120`.
4. Confirm live unlock env vars are false before readonly/shadow.

## Readonly validation

1. Run `./scripts/run_kraken_spot_readonly_analysis.sh`.
2. Check:
   - `kraken_spot_operator_summary.json`
   - `live_safety_summary.json`
   - `performance_gap_report.json`
   - `pair_ranking_report.json`
   - `expectancy_engine_report.json`
   - `promotion_gate_report.json`
3. If `performance_gap_report.json["theoretically_implausible_under_current_capital_envelope"] == true`, treat target as blocked, not as an execution failure.

## Shadow multi-pair validation

1. Run `./scripts/run_kraken_spot_shadow_multi_pair.sh`.
2. Confirm ranked pairs, clusters, and admission/expulsion reports are non-empty.
3. Confirm no live-order artifact or authority leak is implied by the run.

## Tiny-live evidence collection

1. Run readonly first.
2. Run `python3 scripts/tiny_live_promotion_readiness.py --run-dir <run_dir> --secrets-dir <secrets_dir>`.
3. Review `evidence_scorecard.json`, `promotion_gate_report.json`, `rollback_trigger_report.json`, and `rollout_readiness_report.json`.
4. Launch tiny live only if current review status is `evidence_collect` and no blocked safety condition exists.

## Freeze / pause / flatten path

1. If truth degrades or lifecycle becomes partial in a live run, freeze new opens first.
2. If reconciliation or accounting truth is ambiguous, flatten.
3. Record the action in run review notes and retain artifact bundle.

## Incident triage

1. Check `health_summary.json`, `control_journal.jsonl`, `reconciliation_journal.jsonl`, `live_degradation_detector_report.json`.
2. Confirm whether the issue is:
   - doctrine/safety block
   - market/integrity block
   - credentials / lifecycle block
   - promotion/readiness block
3. Do not override with ad-hoc config edits during incident response.

## Not trading diagnosis

Review in order:

1. `no_trade_reason_histogram.json`
2. `opportunity_queue_snapshot.json`
3. `candidate_rejection_matrix.json`
4. `performance_gap_report.json`
5. `market_watch_journal.jsonl`

## Target impossible diagnosis

Use:

1. `performance_target_translation.json`
2. `performance_gap_report.json`
3. `capital_envelope_summary.json`
4. `capital_efficiency_report.json`

If the target is implausible under current capital envelope, the correct action is evidence review or target revision, not live aggression increase.
