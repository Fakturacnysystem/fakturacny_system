# Decision Deadline Governor

The repo already had stale-data protection and stage timing metrics. It does not yet have a full fast-lane/deep-lane architecture.

Current implemented truth:

- stage timings are recorded in live runtime
- stale market and truth data remain fail-closed inputs
- latency warnings and degradation remain active

Code paths:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `src/autonomous_investment_robot/services/market_integrity_service/service.py`
- `src/autonomous_investment_robot/services/live_runtime/service.py`

Current artifact expectations:

- `decision_deadline_journal.jsonl`
- `signal_freshness_journal.jsonl`
- `route_selection_journal.jsonl`
- `expired_signal_review.jsonl`

Current limitation:

- this remains partial. The current upgrade improves latency visibility through module value reporting but does not create a separate deep-lane planner.
