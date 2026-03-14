# Operator Runbook

## 1. Validate First

```bash
cd /Users/martinholik/Projects/fakturacny_system
./.venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode paper
pytest -q
./.venv/bin/python scripts/audit_config_matrix.py
./.venv/bin/python scripts/validate_deployment_manifests.py
```

## 2. Start Paper Mode (Default)

```bash
cd /Users/martinholik/Projects/fakturacny_system
./scripts/run_kraken_ultra_profit_full_throttle.sh
```

If live gate is not satisfied, launcher starts paper mode automatically.

## 3. Manual Live Gate (Operator-Controlled)

```bash
cd /Users/martinholik/Projects/fakturacny_system
./scripts/create_live_confirmation_artifact.sh
export AUTONOMOUS_LIVE_GO=1
export AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE=/Users/martinholik/Projects/fakturacny_system/ops/live_operator_confirmation.txt
```

Then run live preflight:

```bash
./.venv/bin/python scripts/safety_preflight.py --config config.kraken_spot.live_profit.yaml --target-mode live
```

Or use the combined helper:

```bash
source deploy/live-unlock.env.example
./scripts/live_unlock_check.sh config.kraken_spot.live_profit.yaml
```

Only after passing preflight:

```bash
./scripts/run_kraken_ultra_profit_full_throttle.sh
```

## 4. Runtime Audit

```bash
./.venv/bin/python scripts/runtime_audit.py --run-dir runs/kraken_ultra_profit_full_throttle --event-limit 3000 --output runs/latest_runtime_audit_ultra.json
```

## 5. Stop Runtime

```bash
pkill -f "python.*-m cli.worker --config runs/kraken_ultra_profit_full_throttle/runtime_config.effective.yaml" || true
pkill -f "python.*-m cli.run --config config.kraken_spot.live_profit.yaml --nonstop" || true
```
