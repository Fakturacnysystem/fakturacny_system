# Event Feed Runtime

Event intelligence is optional and bounded-safe.

Code paths:

- `src/autonomous_investment_robot/services/event_intelligence_service/service.py`
- `src/autonomous_investment_robot/services/live_runtime/coordination.py`
- `src/autonomous_investment_robot/core/orchestrator.py`

Current runtime truth:

- absent event evidence is represented as partial/unavailable, not as negative evidence
- configured external path comes from `KRAKEN_SPOT_EVENT_FEED_PATH`
- event outputs can influence admission, capital posture, and explainability, but cannot bypass doctrine or risk

Current emitted artifacts:

- `live_event_feed_status.json`
- `event_context_journal.jsonl`
- `event_availability_journal.jsonl`
- `event_edge_impact_review.jsonl`

Current limitation:

- live event evidence quality is still only as strong as the provided feed and source trust
