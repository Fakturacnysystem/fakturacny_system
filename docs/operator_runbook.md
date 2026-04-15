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
| Kraken SPOT tiny live | config.kraken_spot.tiny_live.yaml | `scripts/run_kraken_spot_tiny_live.sh` | HIGH (first-money proving mode, smallest live envelope) |
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
# Edit: ENABLE_LIVE_TRADING=false (keep false until tiny_live passes)
# Edit: ENABLE_FULL_LIVE_STAGE=false (set true only for config.kraken_spot.live_profit.yaml)
# Optional: KRAKEN_SPOT_EVENT_FEED_PATH=/absolute/path/to/events.jsonl
source .env

# 3. Run tests to verify environment
.venv/bin/pytest -q
python3 scripts/deployment_preflight.py
```

---

## Rollout ladder

| Stage | Purpose | Allowed actions | Blocked actions | Rollback target |
|-------|---------|-----------------|-----------------|-----------------|
| `readonly` | connector, truth, and analytics validation | live data, full decisioning, full reporting | any order placement | stay readonly |
| `shadow` | visibility-only decision comparison | readonly analysis plus additive action comparison | any order placement | `readonly` |
| `tiny_live` | first real-money execution proof | opens, reduce-only exits, flatten, freeze-only | high-notional sizing, full-stage envelope | `shadow` |
| `limited_live` | conservative post-tiny deployment | normal live actions inside conservative envelope | full-stage envelope | `tiny_live` |
| `normal_live` | full approved live envelope | full doctrine-safe autonomy | doctrine-incompatible paths | `limited_live` |

Tiny live is intentionally stricter than normal live:
- smaller notional envelope
- lower order-rate allowance
- tighter spread and depth gates
- faster downgrade to no-trade / freeze posture

Promotions remain explicit and manual. Downgrades may happen automatically on truth, reconciliation, market-watch, or health degradation.
Additive performance subsystems remain telemetry or shadow-only until promoted under `PROMOTION_GATES.md`.

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
- [ ] Readonly analysis passed with live market data and emitted operator summary
- [ ] `tiny_live_readiness_report.json["ready"] == true`
- [ ] `safety_preflight_live_target.json["ready"] == true`
- [ ] `rollback_preflight_liveprofit_paper.json["ready"] == true`
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

# Method 2a: Freeze new openings only
PYTHONPATH=src python3 -m autonomous_investment_robot flatten \
  --config config.kraken_spot.live.yaml \
  --freeze-only \
  --reason "operator_freeze_only"

# Method 2b: Flatten a single symbol
PYTHONPATH=src python3 -m autonomous_investment_robot flatten \
  --config config.kraken_spot.live.yaml \
  --scope symbol \
  --symbol BTC/USD \
  --reason "operator_symbol_flatten"

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
cat runs/<run_id>/throughput_diagnostics.json
cat runs/<run_id>/failure_taxonomy.json
cat runs/<run_id>/decision_explainability.json
cat runs/<run_id>/tiny_live_readiness_report.json
cat runs/<run_id>/safety_preflight_live_target.json
cat runs/<run_id>/rollback_preflight_liveprofit_paper.json
cat runs/<run_id>/tiny_live_envelope_summary.json
cat runs/<run_id>/live_operator_start_procedure.json
python3 scripts/runtime_status.py --run-dir runs/<run_id>
python3 scripts/runtime_healthcheck.py --run-dir runs/<run_id>
python3 scripts/collect_diagnostics_bundle.py --run-dir runs/<run_id>
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
python3 scripts/deployment_preflight.py
python3 scripts/verify_server_parity.py --runtime-path /opt/trading-bot/core
```

---

## Distributed mode (FUTURE — not yet implemented)

See `docs/redis_postgres_validation.md` for current state.
See `docs/architecture_truth.md` for full feature classification.

This surface remains explicitly non-production in the current repo. `redis_backend.py` and `postgres_mirror.py` are not implemented, so no deployment or runbook step may claim those paths are live-ready.

## Deployment truth

- `infra/docker-compose.yml` is the only supported compose manifest in this repo, and only for infra dependencies.
- Root `docker-compose.yml` is explicit `legacy_blocked` ballast and must not be used as a live runtime source.
- `src/autonomous-investment-robot/` is an archival duplicate snapshot, not the supported source tree.
- `apps/`, `tools/`, `bootstrap_mac.sh`, and `codex_ultra_master_prompt.md` are local-only and excluded from the supported deploy context.
- Before any restart or deploy:
  - `python3 scripts/deployment_preflight.py`
  - `python3 scripts/verify_server_parity.py --runtime-path <runtime_path>`
  - `python3 scripts/tiny_live_promotion_readiness.py --run-dir <run_dir> --secrets-dir <secrets_dir>`

Distributed mode requires:
1. `services/distributed/redis_backend.py` implementation
2. `services/storage/postgres_mirror.py` implementation
3. `REDIS_URL` and `POSTGRES_DSN` in .env
4. Running infra: `cd infra && docker compose up -d`

---

## Rollback

```bash
# Roll back tiny live to readonly / paper validation
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly \
  --config config.kraken_spot.readonly_analysis.yaml
PYTHONPATH=src python3 -m autonomous_investment_robot run \
  --config config.kraken_spot.paper_full_analysis.yaml --once

# Verify golden checksums still match
.venv/bin/pytest tests/test_replay_golden*.py -v
```

---

## Tiny live operator start procedure

1. Export:
   - `KRAKEN_SPOT_API_KEY`
   - `KRAKEN_SPOT_API_SECRET`
   - `ENABLE_LIVE_TRADING=true`
   - `ACK_I_UNDERSTAND_RISKS=true`
2. Keep `ENABLE_FULL_LIVE_STAGE=false`.
3. Optional:
   - `KRAKEN_SPOT_EVENT_FEED_PATH=/absolute/path/to/events.jsonl`
4. Run readonly first:
   - `bash scripts/run_kraken_spot_readonly_analysis.sh`
5. Inspect readiness artifacts in the latest run directory.
6. Start tiny live:
   - `bash scripts/run_kraken_spot_tiny_live.sh`
7. If truth or execution degrades:
   - `flatten --freeze-only ...`
   - then `flatten --scope symbol ...` or full flatten if needed
8. Promote to `config.kraken_spot.live.yaml` only after clean tiny-live execution evidence.

---

## Known limitations

- Single-symbol per run (no parallel processing)
- Single-machine only (no distributed compute)
- Recording-backed replay for Kraken SPOT still depends on operator-supplied recordings/events
- `god_mode_launcher.py`, `live_production_master.py`, and `src/main.py` are not supported operator entrypoints
- Derivatives `live` / `live_testnet` configs are intentionally blocked for the current doctrine
- Prometheus/Grafana infra defined but no active dashboard queries
