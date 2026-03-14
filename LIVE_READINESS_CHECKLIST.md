# Live Readiness Checklist

## Safety Preconditions

- [ ] `pytest -q` passes.
- [ ] `./.venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode live` passes.
- [ ] Hard sell invariants enabled and unchanged.
- [ ] Harmony resolved config generated and reviewed.
- [ ] Mastermind status health is `OK`.

## Manual Live Gate (Required)

- [ ] `AUTONOMOUS_LIVE_GO=1` exported in operator shell.
- [ ] Confirmation artifact exists:
  - default: `ops/live_operator_confirmation.txt`
  - or `AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE` points to existing file.

## Runtime Infra

- [ ] Redis reachable if distributed compute is expected.
- [ ] Postgres DSN configured if mirror sink is required.
- [ ] Docker/Compose available on cloud node (for compose deployments).

## Operational Controls

- [ ] Monitoring and runtime audit scripts available.
- [ ] Kill path tested (`KILL` file / process stop command).
- [ ] Recovery path tested (restart and artifact continuity).

## Go / No-Go

- Go only if all checks above are green.
- No-Go if any safety preflight or invariant check fails.
