# Incident Runbooks

## Exchange down
1. Trigger infra kill-switch and block new orders.
2. Force reconciliation against last known balances.
3. Switch to no-trade / paper simulation.

## WS outage
1. Mark feed stale after configured threshold.
2. Enable REST polling fallback with reduced cadence.
3. If outage exceeds UNSPECIFIED threshold, kill trading for venue.

## Checksum mismatch
1. Halt symbol/venue trading immediately.
2. Refresh snapshot and replay buffered deltas.
3. Resume only after sequence + checksum pass.

## Reconciliation mismatch
1. Hard stop execution and open manual audit incident.
2. Compare orders↔fills↔balances and generate discrepancy report.
3. Resume only after signed operator approval.

## Rate-limit storm
1. Apply adaptive throttling and exponential backoff.
2. Prefer secondary providers for non-execution data.
3. If persistent, degrade to NO-TRADE safe mode.
