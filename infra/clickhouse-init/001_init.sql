CREATE TABLE IF NOT EXISTS raw_ticks (
  venue String,
  symbol String,
  ts DateTime,
  mid Float64,
  bid Float64,
  ask Float64,
  spread Float64
) ENGINE = MergeTree ORDER BY (symbol, ts);

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
  mu Float64,
  sigma Float64,
  confidence Float64
) ENGINE = MergeTree ORDER BY (symbol, ts);
