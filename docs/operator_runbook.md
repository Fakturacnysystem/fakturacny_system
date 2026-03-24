# Operator Runbook — autonomous_investment_robot

**Last updated:** 2026-03-23

---

## Quick reference: execution modes

| Mode | Config | Command | Risk level |
|------|--------|---------|------------|
| Paper | config.perps_intraday.paper.yaml | `PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.perps_intraday.paper.yaml` | NONE (offline simulation) |
| Live readonly | config.perps_intraday.live_readonly.yaml | `PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.perps_intraday.live_readonly.yaml` | NONE (read-only) |
| Testnet | config.perps_intraday.testnet.yaml | `scripts/run_testnet.sh` | LOW (testnet only) |
| Canary | config.perps_intraday.live_canary.yaml | `scripts/run_live_canary.sh` | MEDIUM (1–5% notional) |
| Live | config.perps_intraday.live.yaml | `scripts/run_live.sh` | HIGH (full notional) |
| Kraken readonly | config.kraken_derivatives.live_readonly.yaml | `scripts/run_kraken_live_readonly.sh` | NONE |
| Kraken testnet | config.kraken_derivatives.testnet.yaml | `scripts/run_kraken_testnet.sh` | LOW |
| Kraken live canary | config.kraken_derivatives.live_canary.yaml | `scripts/run_kraken_live_canary.sh` | MEDIUM |
| Kraken live | config.kraken_derivatives.live.yaml | `scripts/run_kraken_live.sh` | HIGH |

---

## Environment setup

```bash
# 1. Install Python dependencies
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Copy and fill .env
cp .env.example .env
# Edit: BINANCE_API_KEY, BINANCE_API_SECRET (or KRAKEN_API_KEY, KRAKEN_API_SECRET)
# Edit: ENABLE_LIVE_TRADING=false (keep false until canary passes)
source .env

# 3. Run tests to verify environment
.venv/bin/pytest -q
```

---

## Preflight checklist before going live

Before switching `ENABLE_LIVE_TRADING=true`:

- [ ] Paper mode passed 48h continuous run without kill-switch trigger
- [ ] Testnet mode passed 24h with positive fill rate
- [ ] Reconciliation checks passing (no `reconciliation_mismatch_total > 0`)
- [ ] Golden replay tests green: `pytest tests/test_replay_golden*.py`
- [ ] Risk limits reviewed and set in config (no UNSPECIFIED values)
- [ ] API credentials verified via `scripts/instant_validate_kraken.sh` or provider preflight
- [ ] `ACK_I_UNDERSTAND_RISKS=true` set in .env
- [ ] `CANARY_MODE=true` set initially

---

## Emergency stop

```bash
# Method 1: KILL file (safest, robot detects on next poll)
touch runs/<run_id>/KILL

# Method 2: Emergency flatten (sends provider-supported reduce-only flatten orders)
PYTHONPATH=src python3 -m autonomous_investment_robot flatten \
  --config config.perps_intraday.live.yaml

# Method 3: Kill process
kill -SIGTERM <pid>
```

---

## Monitoring

```bash
# View Prometheus metrics
cat runs/<run_id>/metrics.prom

# View audit log
cat runs/<run_id>/audit.jsonl | python3 -m json.tool | less

# View fills
cat runs/<run_id>/fills.csv

# Inspect doctrine / mastermind / escalation summaries
cat runs/<run_id>/decision_doctrine_summary.jsonl
cat runs/<run_id>/mastermind_summary.jsonl
cat runs/<run_id>/human_escalation_journal.jsonl
```

Start the monitoring stack (if Docker available):
```bash
cd infra && docker compose up -d prometheus grafana
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
```

---

## Configuration validation

```bash
# Validate config file
PYTHONPATH=src python3 -c "
from autonomous_investment_robot.config.settings import RobotSettings
s = RobotSettings.from_file('config.perps_intraday.live.yaml')
print('Config valid:', s.execution.mode, s.execution.provider_id)
"

# Validate compose files
docker compose -f infra/docker-compose.yml config -q && echo "OK"

# Run full validation suite
bash scripts/validate_compose_runtime.sh
```

---

## Distributed mode (FUTURE — not yet implemented)

See `docs/redis_postgres_validation.md` for current state.
See `docs/architecture_truth.md` for full feature classification.

Distributed mode requires:
1. `services/distributed/redis_backend.py` implementation
2. `services/storage/postgres_mirror.py` implementation
3. `REDIS_URL` and `POSTGRES_DSN` in .env
4. Running infra: `cd infra && docker compose up -d`

---

## Rollback

```bash
# Rollback to previous config (paper first)
git stash  # or git checkout <prev-commit>
PYTHONPATH=src python3 -m autonomous_investment_robot run \
  --config config.perps_intraday.paper.yaml --once

# Verify golden checksums still match
.venv/bin/pytest tests/test_replay_golden*.py -v
```

---

## Known limitations

- Single-symbol per run (no parallel processing)
- Single-machine only (no distributed compute)
- Recording only for Binance USDT-M (Kraken recording not implemented)
- Requested target `Kraken SPOT only` is not implemented in the launch-gated runtime
- `god_mode_launcher.py`, `live_production_master.py`, and `src/main.py` are not supported operator entrypoints
- HarmonyConfigResolver / harmony reports are not implemented
- Prometheus/Grafana infra defined but no active dashboard queries
