# False-Negative Review

The runtime now emits stronger veto and false-negative evidence from the real policy path.

Code paths:

- `src/autonomous_investment_robot/services/policy/service.py`
- `src/autonomous_investment_robot/services/live_runtime/coordination.py`

Current emitted artifacts:

- `decision_waterfall_journal.jsonl`
- `veto_attribution_journal.jsonl`
- `false_negative_review.jsonl`
- existing `false_negative_report.json`

Current runtime behavior:

- every evaluated live decision now carries a `decision_waterfall`
- primary veto attribution is explicit
- high-utility no-trade outcomes are surfaced as false-negative candidates

Current limitation:

- this is still review-oriented evidence, not an automatic promotion path
