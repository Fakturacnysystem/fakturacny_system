# Market Matrix

| Config | Provider | Market | Mode | Symbols | Quote | Leverage |
|---|---|---|---|---:|---|---:|
| `config.kraken_spot.live.yaml` | `paper_sim_provider` | `spot` | `live` | 2 | `EUR` | 0 |
| `config.kraken_spot.live_canary.yaml` | `paper_sim_provider` | `spot` | `live_testnet` | 2 | `USD` | 0 |
| `config.kraken_spot.live_growth.yaml` | `paper_sim_provider` | `spot` | `live` | 1 | `USD` | 0 |
| `config.kraken_spot.live_pro_growth.yaml` | `paper_sim_provider` | `spot` | `live` | 1 | `USD` | 0 |
| `config.kraken_spot.live_profit.yaml` | `paper_sim_provider` | `spot` | `live` | 8 | `` | 0 |
| `config.kraken_spot.live_readonly.yaml` | `paper_sim_provider` | `spot` | `live_readonly` | 2 | `USD` | 0 |
| `config.kraken_spot.paper.yaml` | `paper_sim_provider` | `spot` | `paper` | 1 | `USD` | 0 |
| `config.paper.yaml` | `paper_sim_provider` | `spot` | `paper` | 1 | `USD` | 0 |
| `config.perps_intraday.live.yaml` | `paper_sim_provider` | `spot` | `live` | 1 | `USD` | 0 |
| `config.perps_intraday.live_canary.yaml` | `paper_sim_provider` | `spot` | `live` | 1 | `USD` | 0 |
| `config.perps_intraday.live_readonly.yaml` | `paper_sim_provider` | `spot` | `live_readonly` | 1 | `USD` | 0 |
| `config.perps_intraday.paper.yaml` | `paper_sim_provider` | `spot` | `paper` | 2 | `USD` | 0 |
| `config.perps_intraday.testnet.yaml` | `paper_sim_provider` | `spot` | `live_testnet` | 1 | `USD` | 0 |

## Universe Details

### `config.kraken_spot.live.yaml`

`XBTEUR, ETHEUR`

### `config.kraken_spot.live_canary.yaml`

`XBTUSD, ETHUSD`

### `config.kraken_spot.live_growth.yaml`

`XBTUSD`

### `config.kraken_spot.live_pro_growth.yaml`

`XBTUSD`

### `config.kraken_spot.live_profit.yaml`

`ADAXBT, ALGOXBT, DOTXBT, SOLXBT, XXRPXXBT, XXLMXXBT, LINKXBT, XETHXXBT`

### `config.kraken_spot.live_readonly.yaml`

`XBTUSD, ETHUSD`

### `config.kraken_spot.paper.yaml`

`XBTUSD`

### `config.paper.yaml`

`BTCUSDT`

### `config.perps_intraday.live.yaml`

`BTCUSDT`

### `config.perps_intraday.live_canary.yaml`

`BTCUSDT`

### `config.perps_intraday.live_readonly.yaml`

`BTCUSDT`

### `config.perps_intraday.paper.yaml`

`BTCUSDT, ETHUSDT`

### `config.perps_intraday.testnet.yaml`

`BTCUSDT`

## Cross-Asset Normalization Defaults (Phase 20)

- Canonical class aliases include:
  - `spot -> crypto_spot`
  - `perp|perpetual -> crypto_perp`
  - `future -> futures`
  - `equity|stock -> xstock`
  - `forex -> fx`
- Default deterministic class caps in allocator:
  - `crypto_spot: 0.80`
  - `crypto_perp: 0.60`
  - `futures: 0.60`
  - `xstock: 0.45`
  - `xstock_etf: 0.40`
  - `fx: 0.50`
