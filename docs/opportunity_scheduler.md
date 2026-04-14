# Opportunity Scheduler

The repo already had ranking, auction, and backlog telemetry. The runtime now uses a bounded live-authoritative scheduler in one specific case:

- mode is live-capable
- there is no active exposure
- there are no open orders
- configured universe contains more than one symbol

Code path:

- `src/autonomous_investment_robot/core/orchestrator.py`
- `_live_candidate_symbols()`
- `_candidate_scheduler_score()`
- `_select_live_symbol_candidate()`
- `_live_loop()`

Current behavior:

- evaluates each configured spot symbol through the real live market and decision coordinators
- ranks candidates by expected utility, floor compatibility, execution survivability, capital efficiency, and toxicity penalty
- chooses one symbol only
- preserves `max_active_pairs=1`
- falls back to the legacy single-symbol loop once inventory or open orders exist

Artifacts:

- `opportunity_scheduler_journal.jsonl`
- `capital_allocation_journal.jsonl`
- `opportunity_ranking_snapshot.json`
- `correlation_budget_journal.jsonl`
- `deferred_opportunity_review.jsonl`

Current limitation:

- this is still a flat-state scheduler, not a multi-position portfolio controller
