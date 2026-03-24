# Operator Runbook — autonomous_investment_robot

**Last updated:** 2026-03-24

---

## Quick reference: execution modes

| Mode | Config | Command | Risk level |
|------|--------|---------|------------|
| Paper | config.kraken_spot.paper.yaml | `PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.kraken_spot.paper.yaml` | NONE (offline simulation) |
| Paper full analysis | config.kraken_spot.paper_full_analysis.yaml | `scripts/run_kraken_spot_paper_full_analysis.sh` | NONE (offline simulation, full stack) |
| Replay full analysis | config.kraken_spot.replay_full_analysis.yaml | `scripts/run_kraken_spot_replay_full_analysis.sh` | NONE (offline replay, full stack) |
| Readonly analysis | config.kraken_spot.readonly_analysis.yaml | `scripts/run_kraken_spot_readonly_analysis.sh` | NONE (read-only, no order placement) |
| Kraken SPOT guarded live | config.kraken_spot.live.yaml | `scripts/run_kraken_spot_profit_full_throttle.sh` | HIGH (launch-gated spot only) |
| Kraken SPOT higher-notional | config.kraken_spot.live_profit.yaml | `scripts/run_kraken_ultra_profit_full_throttle.sh` | HIGH (launch-gated spot only) |

Both supported Kraken SPOT live configs boot in normal risk mode. Startup no-trade safe mode is not armed by default. Capital protection remains enforced by doctrine, reconciliation, market-integrity, market-watch, risk, and final pre-submit validation.

---

## Environment setup

```bash
# 1. Install Python dependencies
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Copy and fill .env
cp .env.example .env
# Edit: KRAKEN_SPOT_API_KEY, KRAKEN_SPOT_API_SECRET
# Edit: ENABLE_LIVE_TRADING=false (keep false until canary passes)
# Edit: ENABLE_FULL_LIVE_STAGE=false (set true only for config.kraken_spot.live_profit.yaml)
source .env

# 3. Run tests to verify environment
.venv/bin/pytest -q
```

---

## Kraken SPOT doctrine-only non-live surfaces

Active for paper / replay / readonly full-analysis:
- market integrity
- provider capability truth
- harmony reporting
- market watch
- quantum / signal interference
- edge immunity
- SPRE / shadow
- capital sovereignty / morphing / adaptive exit
- synthetic affect
- execution simulation
- escalation
- replay/operator bundles
- PnL attribution / loss autopsy / episodic memory / analog / counterfactual summaries

Active but partial unless event evidence is supplied:
- source trust / novelty / relevance / impact / priced-in / adversarial / provenance

Explicitly blocked by doctrine:
- derivatives/perps launch paths
- short-opening strategies
- fresh SELL entries outside reduce-only inventory-backed exits

## Preflight checklist before going live

Before switching `ENABLE_LIVE_TRADING=true`:

- [ ] Paper mode passed 48h continuous run without kill-switch trigger
- [ ] Kraken SPOT runtime preflight passes at boot with real API credentials
- [ ] Reconciliation checks passing (no `reconciliation_mismatch_total > 0`)
- [ ] Golden replay tests green: `pytest tests/test_replay_golden*.py`
- [ ] Risk limits reviewed and set in config (no UNSPECIFIED values)
- [ ] API credentials verified via `scripts/instant_validate_kraken.sh` or provider preflight
- [ ] `ACK_I_UNDERSTAND_RISKS=true` set in .env
- [ ] `ENABLE_LIVE_TRADING=true` set only immediately before guarded launch
- [ ] `ENABLE_FULL_LIVE_STAGE=true` set only for `config.kraken_spot.live_profit.yaml`

---

## Emergency stop

```bash
# Method 1: KILL file (safest, robot detects on next poll)
touch runs/<run_id>/KILL

# Method 2: Emergency flatten (sends provider-supported reduce-only flatten orders)
PYTHONPATH=src python3 -m autonomous_investment_robot flatten \
  --config config.kraken_spot.live.yaml

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
cat runs/<run_id>/kraken_spot_operator_summary.json
cat runs/<run_id>/kraken_spot_replay_summary.json
cat runs/<run_id>/live_capability_matrix.json
cat runs/<run_id>/live_activated_capabilities.json
cat runs/<run_id>/live_still_gated_capabilities.json
cat runs/<run_id>/live_doctrine_blocked_capabilities.json
cat runs/<run_id>/live_artifact_index.json
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
s = RobotSettings.from_file('config.kraken_spot.paper_full_analysis.yaml')
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
- Recording-backed replay for Kraken SPOT still depends on operator-supplied recordings/events
- `god_mode_launcher.py`, `live_production_master.py`, and `src/main.py` are not supported operator entrypoints
- Derivatives `live` / `live_testnet` configs are intentionally blocked for the current doctrine
- Prometheus/Grafana infra defined but no active dashboard queries
