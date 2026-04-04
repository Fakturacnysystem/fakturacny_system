# Operations Runbook Requirements

## Goal
Define operator procedures for incidents, degraded states, control actions, replay review, and post-incident handling.

## Incident Severity Model
### SEV-1
Examples:
- emergency flatten required
- unsafe execution state
- corrupted control state
- critical backend/runtime mismatch

### SEV-2
Examples:
- stale market data
- degraded integrity
- repeated bridge/backend failures
- major replay/forensics inconsistency

### SEV-3
Examples:
- partial artifact availability
- non-critical diagnostics degradation
- UI/bridge mismatch without execution risk

## Operator Procedures

### Pause
When to use:
- suspicious behavior
- pre-maintenance
- manual inspection

Required steps:
1. confirm command
2. verify effective state
3. verify audit reference
4. add operator note if reason is operational

### Resume
Required checks before resuming:
- health is acceptable
- no critical blockers
- integrity state understood
- operator confirms resume reason

### Freeze
Use when:
- execution must stop immediately
- risk/integrity state is unclear
- human intervention required urgently

### Emergency Flatten
Use when:
- immediate position exit is required
- risk state is unacceptable
- doctrine/integrity breach creates unacceptable exposure

Required steps after flatten:
1. confirm response/audit reference
2. open diagnostics
3. write incident note
4. create replay review task

## Incident Note Requirements
Each significant incident note should include:
- operator
- timestamp
- severity
- summary
- observed symptoms
- action taken
- next review step

## Replay / Post-Incident Review
For serious incidents:
1. open Replay Lab
2. inspect run timeline
3. inspect analog matches / counterfactuals / pnl attribution
4. document root cause hypothesis
5. classify incident severity
6. define corrective action

## Acceptance Criteria
- procedures are visible in docs
- UI can link or align with these procedures
- operator actions have a consistent review flow
