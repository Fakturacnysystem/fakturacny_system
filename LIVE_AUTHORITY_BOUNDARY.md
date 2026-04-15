# Live Authority Boundary

This repository is `production-complete` only in the narrow sense that it can safely collect evidence, emit operator-grade artifacts, and run bounded Kraken SPOT rollout stages without ambiguous authority.

It is not a claim that every additive performance subsystem is live-authoritative.

## Canonical live authority

These paths are authoritative for real order-routing and capital mutation:

| Subsystem | Authority level | Stages | Notes | Rollback path |
|---|---|---|---|---|
| `RobotSettings`, `HarmonyConfigResolver`, rollout profile, live gate | authoritative live gating | `readonly`, `shadow`, `tiny_live`, `limited_live`, `normal_live` | Config truth, doctrine locks, live unlock, rollout envelope, provider/doctrine compatibility | revert config, disable env unlocks, rerun readonly |
| `services/live_runtime/coordination.py` | authoritative live coordination | `tiny_live`, `limited_live`, `normal_live` | Restart confidence, reserve policy, lifecycle-proof envelope, pre-submit live coordination | downgrade stage, freeze, flatten |
| `services/policy/service.py` | authoritative live decisioning | `tiny_live`, `limited_live`, `normal_live` | Existing policy path remains the only live decision authority | readonly/shadow run, revert release |
| `services/execution/service.py` | authoritative live execution planning | `tiny_live`, `limited_live`, `normal_live` | Existing execution planner remains canonical for real orders | freeze, flatten, rollback deploy |
| `services/execution/live_kraken_spot_service.py` | authoritative live submit / fill / sell-fence enforcement | `tiny_live`, `limited_live`, `normal_live` | Kraken SPOT only, long-only, hard SELL fences preserved | freeze, flatten, disable live unlock |
| `InventoryService`, `ProfitabilityService`, reconciliation / truth ownership surfaces | authoritative accounting truth guards | all stages, with live mutation only in live stages | FIFO/cost-basis truth, reserve truth, reconciliation truth, explicit gap handling | readonly rerun, flatten, incident review |
| Kill-switch / freeze / flatten / pause operator pathways | authoritative safety controls | all stages where applicable | Additive telemetry cannot bypass these controls | invoke freeze/flatten/KILL |

## Additive live telemetry only

These systems are wired, emitted, and operator-visible, but they do not own live order-routing authority:

| Subsystem | Current authority | Stages using output | Promotion preconditions | Rollback path |
|---|---|---|---|---|
| Performance target translation | additive telemetry | `readonly`, `shadow`, `tiny_live`, `limited_live`, `normal_live` | clean artifact stability, operator adoption, no config ambiguity | ignore artifact, keep live path unchanged |
| Capital envelope / dead-capital reports | additive telemetry | same | evidence that allocator inputs match realized balances and reserve truth | disable consumption in summaries |
| Multi-pair universe ranking / clustering / rotation | shadow-evaluable only | `readonly`, `shadow`, additive in live summaries | live sample proof, pair-level reconciliation, explicit bounded promotion design | keep single-pair live config |
| Regime hysteresis / exit-family hints | additive telemetry | all stages | stable report correctness and no contradiction with live policy | ignore hints |
| Playbook framework | shadow-evaluable only | `readonly`, `shadow`, additive summaries in live stages | closed-trade evidence, explicit promotion gate, no doctrine conflict | keep `PolicyService` authoritative |
| Opportunity auction / backlog / FN / FP / crowding | shadow-evaluable only | `readonly`, `shadow`, additive summaries in live stages | repeated tiny-live evidence and explicit routing gate | keep legacy decision path |
| Fill-aware cost model / degradation reports | additive telemetry | all stages | verify cost truth against realized fills before any gating authority change | use existing TCO/live fences only |
| Portfolio allocator | shadow-evaluable only | `readonly`, `shadow`, additive summaries in live stages | repeated agreement with realized reserve/exposure truth | keep existing notional caps authoritative |
| Expectancy engine / intraday model / meta-router | shadow-evaluable only | `readonly`, `shadow`, additive summaries in live stages | sufficient closed-trade sample, stable promotion score behavior | keep manual promotion only |
| Experiments / promotion score / rollback trigger | additive governance telemetry | all stages | operator acceptance and bounded rollout policy | manual rollout remains canonical |
| Exit intelligence / lifecycle scoring / adverse excursion | additive diagnostics | all stages | explicit sell-fence-safe design for any future live use | existing exit path remains canonical |
| Adaptive cadence / entry timing / self-throttling reports | additive telemetry | all stages | prove no hidden authority leak and bounded effect model | ignore reports, freeze if degraded |
| RCC advanced KPI panels | operator-only surface | all stages | N/A | fall back to raw artifacts |

## Shadow-only by design

These are intentionally non-authoritative until explicit future promotion:

| Subsystem | Reason | Stages | Promotion blockers |
|---|---|---|---|
| `inventory_unwind` playbook | touches cleanup / reduce-only semantics and needs realized evidence | `readonly`, `shadow` | needs closed-trade evidence and explicit cleanup policy review |
| `profit_capture_exit` playbook | not yet safe as live routing authority | `readonly`, `shadow` | needs proven live compatibility with sell fences |
| `capital_protection_exit` below profit floor | would interact with hard SELL doctrine | diagnostic only | requires explicit doctrine change; currently blocked |
| `forced_inventory_cleanup_exit` | can conflict with current alpha profit fence | diagnostic only | requires explicit bounded emergency design |
| allocator-sized live notionals | could silently change economic meaning of live routing | none | requires explicit routing gate and evidence |
| auction-selected live candidate routing | would supersede current policy authority | none | requires explicit code-level gating and tiny-live proof |

## Non-negotiable doctrine

- Kraken SPOT only.
- Long-only only.
- Never sell below authoritative cost basis.
- Never sell unless modeled net profit is `>= minimum_sell_net_profit_bps`.
- `minimum_sell_net_profit_bps` must never be lowered below `120`.
- Readonly / shadow / tiny_live / limited_live / normal_live semantics remain explicit and reversible.

## Promotion rule

No additive subsystem may become live-authoritative unless:

1. The promotion target is named in `PROMOTION_GATES.md`.
2. `evidence_scorecard.json` marks it at least `promotable`.
3. The code change introduces an explicit bounded gate in the canonical live path.
4. Rollback is one-step and operator-visible.
