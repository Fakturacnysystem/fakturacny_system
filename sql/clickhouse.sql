CREATE TABLE IF NOT EXISTS market_events (
  ts DateTime,
  event_type String,
  symbol String,
  venue String,
  seq UInt64,
  checksum String,
  payload String
) ENGINE = MergeTree ORDER BY (symbol, seq);

CREATE TABLE IF NOT EXISTS features (
  symbol String,
  ts DateTime,
  feature_version String,
  ret_1 Float64,
  ret_3 Float64,
  realized_vol Float64,
  atr_proxy Float64,
  spread_proxy Float64
) ENGINE = MergeTree ORDER BY (symbol, ts);

CREATE TABLE IF NOT EXISTS forecasts (
  model_version String,
  symbol String,
  ts DateTime,
  regime String,
  liquidity_regime String,
  mu Float64,
  sigma Float64,
  confidence Float64
) ENGINE = MergeTree ORDER BY (symbol, ts);
