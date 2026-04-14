# Universe Policy

Kraken SPOT live profiles now expose a bounded liquid universe through `market_universe.pair_universe`.

Current committed profiles:

- `config.kraken_spot.readonly_analysis.yaml`
- `config.kraken_spot.tiny_live.yaml`
- `config.kraken_spot.live.yaml`

Current configured liquid board:

- `BTC/USD`
- `ETH/USD`
- `SOL/USD`

Current safeguards:

- `max_active_pairs=1`
- doctrine remains Kraken SPOT only, long only
- only the scheduler-selected symbol enters the live decision path in flat state
- no multi-position expansion was introduced

Foundations reused:

- `MarketUniverseService`
- `cluster_pairs()` in `services/universe/clustering.py`
- existing pair-ranking and pair-rotation artifacts

This file documents a bounded breadth expansion, not a broad portfolio risk expansion.
