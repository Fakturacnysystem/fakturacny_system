# Autonomous Investment Robot for Crypto Markets (Safe-First Scaffold)

Production-grade **modular** architecture scaffold for a 24/7 autonomous crypto trading system with deterministic risk controls, compliance veto, and paper-trading default.

## Safety and non-goals
- Default mode is **SAFE_MODE + paper trading**.
- Live trading is blocked unless explicit live enable + mandatory risk limits are set.
- No promise of profits.
- No live self-rewriting models.
- No market manipulation or exchange rule bypass.

## Architecture

```mermaid
flowchart LR
 subgraph Market["Trhy a externé zdroje"]
 CEX["CEX feedy (tick, L2/L3, trades, funding, OI)"]
 DEX["DEX/aggregátory (quotes, routes, gas, MEV)"]
 ONC["On-chain (RPC, indexery, labelované entity)"]
 MAC["Makro (FX, sadzby, kalendár udalostí)"]
 NEWS["News/sentiment (event stream)"]
 end
 subgraph Data["Data layer"]
 ING["Data ingestion + normalizácia + deduplikácia"]
 QA["Data QA: outliers, gaps, checksum, sequence"]
 RAW["Raw store (immutabilné dáta)"]
 FS["Feature store (verzionované featury)"]
 end
 subgraph Models["Modely"]
 REG["Regime detector"]
 FCAST["Forecast engine (probabilistic ensemble)"]
 CAL["Calibration + uncertainty (PIT/CRPS/Conformal)"]
 end
 subgraph Decision["Rozhodovanie"]
 POL["Policy/portfolio optimizer (utility + constraints)"]
 RISK["Risk engine (VaR/CVaR, limity, kill-switch)"]
 end
 subgraph Exec["Exekúcia"]
 OMS["OMS/EMS + SOR"]
 ALG["Execution algos (TWAP/VWAP/POV/iceberg)"]
 REC["Reconciliation (orders↔fills↔balances)"]
 end
 subgraph Gov["Governance"]
 COMP["Compliance + reporting"]
 SEC["Security (keys, secrets, custody policy)"]
 OPS["Ops/monitoring (SLO, alerting, incident)"]
 end
 Market --> ING --> QA --> RAW --> FS
 FS --> REG --> POL
 FS --> FCAST --> CAL --> POL
 POL --> RISK --> OMS --> ALG --> REC --> RAW
 COMP --> RISK
 SEC --> OMS
 OPS --> ING
 OPS --> OMS
 OPS --> RISK
```

## Data model

```mermaid
erDiagram
 raw_tick ||--o{ raw_trade : contains
 raw_tick {
 string venue
 string symbol
 datetime ts
 float mid
 float bid
 float ask
 float spread
 }
 orderbook_snapshot ||--o{ orderbook_level : has
 orderbook_snapshot {
 string venue
 string symbol
 datetime ts
 int depth
 string checksum
 int sequence
 }
 orderbook_level {
 string side
 float price
 float qty
 int num_orders
 }
 featureset ||--o{ feature_value : includes
 featureset {
 string feature_version
 string symbol
 datetime ts
 }
 feature_value {
 string name
 float value
 }
 forecast ||--o{ forecast_quantile : provides
 forecast {
 string model_version
 string symbol
 datetime ts
 string horizon
 float mu
 float sigma
 float entropy
 }
 forecast_quantile {
 float q
 float value
 }
 order_intent ||--o{ order : spawns
 order {
 string venue
 string symbol
 string side
 float qty
 float limit_price
 string status
 }
 order ||--o{ fill : results_in
 fill {
 datetime ts
 float qty
 float price
 float fee
 }
 position {
 string symbol
 float qty
 float avg_price
 float unrealized_pnl
 }
 risk_event {
 datetime ts
 string type
 string severity
 string action
 }
```

SQL DDL is in `sql/schema.sql`.

## Service boundaries
- `data_ingestion`: streaming + polling fallback, stale flag hooks.
- `data_qa`: checksum/sequence/gap guards.
- `raw_store`: immutable object + append-only interface.
- `feature_store`: versioned feature vectors + leakage lock.
- `models`: probabilistic forecasts/regime/calibration placeholders.
- `policy`: utility-based target sizing (`position_size ∝ risk_budget / σ_h`).
- `risk_engine`: hard limits + deterministic kill-switch state.
- `execution`: pre-trade checks + paper/live mode separation.
- `reconciliation`: orders/fills/balances consistency.
- `compliance`: MiCA/Travel Rule hooks and provider authorization veto.
- `security`: no-withdrawal + IP allowlist checks.
- `ops`: alerts, metrics, audit events, rollback hook surface.

## Connectors implemented (skeletons + config stubs)
- CEX/derivatives: Binance, Coinbase, Kraken, OKX, Bybit, Deribit, Hyperliquid.
- DEX/on-chain: 0x, 1inch, Uniswap, The Graph, Dune, Glassnode, Nansen.
- RPC/anchors: Alchemy, Infura, Chainlink.
- Macro/news: ECB Data Portal API, FRED, GDELT.
- Normalized optional adapters: CoinAPI, Kaiko, CoinGecko.

## Compliance and EU controls
- MiCA-aware provider authorization gate (configurable register URL and whitelist).
- Transitional/national rules can be represented via provider policy lists.
- Travel Rule support hook for transfer metadata workflow.
- Hard veto path: unauthorized provider => no-trade/restricted mode.

## Risk and kill-switch
- Config placeholders marked `UNSPECIFIED`; live mode validation rejects missing mandatory limits.
- Deterministic blocks include safe-mode default, integrity failures, and missing limits.
- Continuous metrics scaffolding: VaR/CVaR/exposure/liquidity/correlation limits are configurable and intentionally UNSPECIFIED until set by operator.

## Infra stack (local dev)
`infra/docker-compose.yml` provides NATS, Redis, Postgres, ClickHouse, MinIO, Prometheus, Grafana.

## Running locally (paper mode)
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e . pytest`
3. `cp .env.example .env` and keep paper defaults.
4. `python scripts/run_paper.py`
5. `pytest`

## Live mode guardrail
Live mode requires all of:
- `ROBOT_TRADING_MODE=live`
- `ROBOT_EXPLICIT_LIVE_ENABLE=true`
- Mandatory risk limits explicitly set (not `UNSPECIFIED`)
- Authorized provider policy configured

## Reporting format examples

```mermaid
xychart-beta
 title "Ilustračné equity curves (normalized) – reportovací formát"
 x-axis ["M1","M2","M3","M4","M5","M6","M7","M8","M9","M10","M11","M12"]
 y-axis "Equity" 80 --> 130
 line [100,101,103,104,106,108,107,109,112,115,118,120]
 line [100,99,100,102,101,103,104,105,104,106,107,108]
 line [100,102,101,103,105,104,106,108,110,109,111,113]
```

```mermaid
pie title Ilustračné rizikové budgety portfólia (example)
 "Trend engine" : 35
 "Mean-reversion engine" : 25
 "Carry/Basis" : 20
 "Tail hedge" : 10
 "Cash/Safety buffer" : 10
```

## MVP roadmap

```mermaid
gantt
 title MVP roadmap autonómneho robota (30/90/180 dní)
 dateFormat YYYY-MM-DD
 axisFormat %d.%m
 section 30 dní
 Data ingestion + QA + raw store :a1, 2026-02-11, 30d
 OMS/EMS minimum + paper trading :a2, 2026-02-11, 30d
 Risk engine v1 (hard limits, kill) :a3, 2026-02-11, 30d
 section 90 dní
 Feature store + baseline forecast :b1, 2026-03-13, 60d
 Regime detector + strategy engines :b2, 2026-03-13, 60d
 Backtest (fees+slip+funding+latency) :b3, 2026-03-13, 60d
 Canary live (malé limity) :b4, 2026-04-15, 30d
 section 180 dní
 SOR + advanced execution algos :c1, 2026-05-15, 60d
 Options/hedging module (ak dostupné) :c2, 2026-05-15, 60d
 Compliance + reporting automation :c3, 2026-05-15, 60d
 Model governance + auto-rollback :c4, 2026-06-15, 60d
```

## External keys/env stubs
See `.env.example` for required variable names. Proprietary/licensed providers remain optional and configurable.
