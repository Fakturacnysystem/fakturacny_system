# Dynamic Cost Model

The repo already had fill-aware cost diagnostics. The current upgrade keeps that foundation and promotes more of its outputs into live economics.

Code paths:

- `src/autonomous_investment_robot/services/cost_model/service.py`
- `src/autonomous_investment_robot/services/execution/service.py`
- `src/autonomous_investment_robot/services/policy/service.py`

Current runtime use:

- admission reasoning uses realized-net-edge style penalties
- execution planning consumes admission action, signal-decay risk, floor compatibility, and execution survivability
- marketable-vs-passive bias is now tightened by the admission layer instead of static local heuristics only

Current emitted artifacts:

- `cost_model_diagnostics.json`
- `maker_taker_mix_report.json`
- `fill_quality_report.json`
- `cost_sensitivity_analysis.json`

Current limitation:

- forecast-vs-realized calibration is still partial and should remain operator-reviewed before any stronger automation
