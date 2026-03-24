# Architecture Truth Document

**Last updated:** 2026-03-24
**Scope:** Hard truth classification of all feature directories and capabilities.

---

## What is REAL and RUNTIME-ACTIVE

These modules are fully implemented, wired into the main execution path, and covered by tests:

| Module | Path | Status |
|--------|------|--------|
| Data Ingestion | services/data_ingestion/ | COMPLETE – CSV replay + Binance WebSocket recorder |
| Feature Store | services/feature_store/ | COMPLETE – v3-perps feature pipeline (ret_1, vol, spread, etc.) |
| Event Store | services/event_store/ | COMPLETE – JSONL append-only logs, idempotency keys |
| Risk Engine | services/risk_engine/ | COMPLETE – kill-switch, safe mode, drawdown, exposure, crowding |
| Policy Service | services/policy/ | COMPLETE – 6 strategies, bandit allocator, regime gating |
| Execution Service | services/execution/ | COMPLETE – paper sim + guarded live adapters with launch-gated Kraken SPOT target |
| OMS | services/oms/ | COMPLETE – INTENT→ACK→FILLED state machine |
| Reconciliation | services/reconciliation/ | COMPLETE – position vs exchange mismatch detection |
| Compliance | services/compliance/ | COMPLETE – provider whitelist enforcement |
| Ops / Prometheus | services/ops/ | COMPLETE – metrics, audit log, prometheus file export |
| Incident Policy | services/incident/ | COMPLETE – 11 incident types, responder wired into live loop |
| Orchestrator | core/orchestrator.py | COMPLETE – paper run + live loop + kill file detection |
| MLOps | services/mlops/ | COMPLETE – model registry, drift detector (PSI) |
| Replay Engine | services/replay/ | COMPLETE – CSV replay, event sourcing, golden tests |
| Binance Connector | connectors/cex/binance_um_perps.py | COMPLETE – REST + signed trading |
| Kraken Connector | connectors/cex/kraken_derivatives.py | COMPLETE – derivatives connector retained, but config-file launch is doctrine-blocked |
| Kraken Spot Connector | connectors/cex/kraken_spot.py | COMPLETE – guarded spot connector with exchange-market constraint normalization |
| Live Binance Service | services/execution/live_binance_service.py | COMPLETE – full signed trading with pre-submit validation |
| Live Kraken Service | services/execution/live_kraken_service.py | COMPLETE – service retained, but config-file launch is doctrine-blocked |
| Live Kraken Spot Service | services/execution/live_kraken_spot_service.py | COMPLETE – final live submit gate for long-only spot doctrine, cost-basis floor, and 120 bps net sell floor |
| Mastermind | services/mastermind/ | COMPLETE – bounded-safe heuristic advisory routed into doctrine/policy/execution |
| Decision Doctrine | services/decision_doctrine_service/ | COMPLETE – unified truth/survival/robustness doctrine |
| HarmonyConfigResolver | services/harmony_config_resolver/ | COMPLETE – doctrine-critical config resolution and harmony reports |
| Market Integrity | services/market_integrity_service/ | COMPLETE – dynamic evidence-based integrity scoring |
| MarketWatchService | services/market_watch_service/ | COMPLETE – blackout, spread, and liquidity safety integration |
| Venue Capability Registry | services/venue_capability_registry/ | COMPLETE – provider-aware capability evidence with runtime refresh |
| Observability Facade | services/observability_facade/ | COMPLETE – dedicated evidence/journal routing |
| Replay Reporting Coordinator | services/replay_reporting/ | COMPLETE – Kraken-SPOT capability manifests, replay summary, artifact index |
| Operator Summary Coordinator | services/operator_summary/ | COMPLETE – unified operator bundle for doctrine/capital/forensics/activation state |

---

## What is STUB / EMPTY DIRECTORY (not implemented)

These directories exist in the codebase but contain NO implementation files.
They represent future work, not current capability.

| Directory | Intended Future Capability | Status |
|-----------|---------------------------|--------|
| services/distributed/ | Redis Streams backbone, compute/live node separation | EMPTY STUB |
| services/llm/ | LLM integration layer | EMPTY STUB |
| services/universe_core/ | Dynamic universe discovery | EMPTY STUB |
| services/market_microstructure/ | LOB intelligence, order flow | EMPTY STUB |
| services/market_watch/ | Legacy placeholder directory name | SUPERSEDED BY `services/market_watch_service/` |
| services/market_discovery/ | Symbol discovery automation | EMPTY STUB |
| services/multi_account/ | Multi-account management | EMPTY STUB |
| services/multi_exchange/ | Cross-exchange arbitrage | EMPTY STUB |
| services/liquidity_map/ | Legacy placeholder directory name | PARTIALLY SUPERSEDED BY `services/market_watch_service/` |
| services/governance/ | Policy governance | EMPTY STUB |
| services/exchange_constraints/ | Per-exchange constraint rules | MISSING BOUNDED CONTEXT |
| services/autonomous_decision/ | Autonomous decision engine | EMPTY STUB |
| services/fees/ | Fee model abstraction | EMPTY STUB |
| services/risk_calendar/ | Calendar-aware risk | EMPTY STUB |
| services/reliability/ | Reliability/SLA monitoring | EMPTY STUB |
| services/storage/ | Distributed storage abstraction | EMPTY STUB |
| services/treasury/ | Capital allocation | EMPTY STUB |
| services/portfolio/ | Portfolio optimization | EMPTY STUB |
| services/research/ | Research / backtesting framework | EMPTY STUB |
| services/ml/ | ML inference layer | EMPTY STUB |
| services/risk/ | Extended risk models | EMPTY STUB |

---

## Infrastructure defined but NOT CODE-WIRED

Defined in `infra/docker-compose.yml`, started by `scripts/dev_up.sh`, but zero Python integration:

| Service | Defined | Code-wired | Runtime-proven |
|---------|---------|------------|----------------|
| Redis 7 | YES | NO | NO |
| PostgreSQL 16 | YES | NO | NO |
| ClickHouse 24.8 | YES | NO | NO |
| MinIO | YES | NO | NO |
| NATS 2.10 | YES | NO | NO |
| Prometheus | YES | PARTIAL (file export) | LOCAL ONLY |
| Grafana | YES | NO (dashboards defined) | NO |

---

## Capabilities explicitly NOT implemented

These were mentioned in project backlog/planning but do not exist in the codebase:

- Causal Market Twin Engine (planning concept only)
- Counterfactual Entry Engine (planning concept only)
- STORM model (planning concept only)
- xStocks / fractional shares / stock market integration (not in scope)
- external operator UI/workflow for manual review ACKs
- venue-native websocket sequence/checksum truth for Kraken SPOT beyond current adapter evidence
- Parallel symbol processing (single-symbol per run)
- Feature cache (in-memory only, no persistence)
- Signal cache (in-memory only, no persistence)
- Distributed compute separation (single machine only)

---

## System architecture (honest current state)

```
Single Python process (synchronous, single-machine)
│
├── Paper mode: deterministic offline replay from OHLCV CSV fixtures
├── Kraken SPOT paper full analysis: offline replay with market integrity, capability truth, market watch, doctrine, SPRE/shadow, execution-sim, escalation, and unified operator/replay bundles
├── Kraken SPOT replay full analysis: recording-backed offline replay with the same evidence/routing bundle
├── Kraken SPOT readonly analysis: connects to exchange/public market data, no order placement, emits the same analysis bundle where possible
└── Live canary/live: guarded Kraken SPOT signed execution behind launch gates and preflight
│
├── Persistence: local JSONL files in run_dir/ with dedicated doctrine, mastermind, SPRE, shadow, escalation, and forensics channels
├── Metrics: Prometheus .prom file (scraped by Prometheus container if running)
└── Transport: direct HTTP REST to Binance/Kraken APIs
```

---

## Safety-critical caveats

- Requested launch target `Kraken SPOT only` is implemented and launch-gated.
- Requested non-live unlock target `Kraken SPOT only` is implemented with explicit capability manifests:
  - `kraken_spot_capability_unlock_matrix.json`
  - `activated_capabilities.json`
  - `still_gated_capabilities.json`
  - `doctrine_blocked_capabilities.json`
- Root helpers `live_production_master.py`, `god_mode_launcher.py`, and `src/main.py` are not supported launch paths and are blocked or dead.
- Use only `python -m autonomous_investment_robot ...` and the scripts under `scripts/`.

## Minimum path to distributed readiness

1. Implement `services/distributed/redis_backend.py` — Redis Streams producer/consumer
2. Implement `services/storage/postgres_mirror.py` — mirror event writes to Postgres
3. Add `REDIS_URL` and `POSTGRES_DSN` env vars to settings
4. Wire backend selection in EventStore
5. Add `tests/test_distributed_e2e.py` (integration test, skipped without Redis)
6. Run `infra/docker-compose.yml` and verify roundtrip
