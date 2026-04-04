# Promotion Gates

Promotion is manual. Evidence only informs it.

## Decision statuses

- `not_ready`: insufficient artifact integrity or missing prerequisites
- `shadow_only`: intentionally non-authoritative by design
- `evidence_collect`: bounded tiny-live collection is allowed; authority unchanged
- `promotable`: evidence threshold satisfied, but still requires explicit code-level promotion and review
- `blocked`: forbidden by doctrine or regression

## Promotable subsystems

| Subsystem | Current status | Required live sample count | Required closed-trade count | Threshold | Forbidden regressions | Rollback trigger | Operator complexity |
|---|---|---:|---:|---|---|---|---|
| Cost-model degradation telemetry | `evidence_collect` | 20 | 10 | realized fill-vs-model delta within bounded review tolerance | any hidden sell-fence interaction, reconciliation drift | 2 consecutive degraded runs with unexplained cost spikes | low |
| Pair ranking / multi-pair admission | `shadow_only` | 40 | 20 | ranked pair wins must match realized clean opportunity capture without worse reconciliation | any symbol-mapping ambiguity, increased no-truth events | ranking mismatch during tiny-live review | medium |
| Playbook framework candidates | `shadow_only` | 40 | 20 | promotable playbook must show non-negative realized net bps and no doctrine conflict | any sell-fence conflict, shadow cleanup leakage | one doctrine conflict or two negative evidence reviews | medium |
| Opportunity auction | `shadow_only` | 50 | 25 | top-ranked candidate must outperform authoritative path in shadow comparison | any hidden routing authority or inventory truth conflict | false-positive spike or rollback trigger | medium |
| Allocator recommended notional | `shadow_only` | 50 | 25 | allocator recommendation must stay within reserve truth and improve capital efficiency without widening drawdown | any cap breach, reserve breach, or envelope drift | one reserve breach or one cap breach | high |
| Expectancy / promotion score | `evidence_collect` | 30 | 15 | realized expectancy and promotion score must agree directionally over rolling windows | sample-guard bypass, misleading readiness output | score disagreement across two review windows | low |
| Adaptive cadence / entry timing / self-throttling | `shadow_only` | 30 | 15 | runtime degradation reduction without hidden order-routing authority | any order-rate or cadence side effect not explicitly gated | degraded run caused by cadence logic | medium |
| Exit-intelligence diagnostics | `shadow_only` | 30 | 20 | lifecycle scoring and adverse-excursion analysis must explain realized exits without contradicting canonical fill truth | any below-floor live sell implication | mismatch with authoritative exit record | low |

## Promotion checklist

1. Validate release baseline commands.
2. Review `evidence_scorecard.json`.
3. Confirm `LIVE_AUTHORITY_BOUNDARY.md` still matches code.
4. Review latest run with `RUN_REVIEW_TEMPLATE.md`.
5. If any forbidden regression is present, status is `blocked`.
6. If thresholds are met, status may become `promotable`, but live-authority still requires explicit code review and bounded gate design.
