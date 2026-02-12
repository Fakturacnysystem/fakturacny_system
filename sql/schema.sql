-- Metadata + timeseries reference DDL (Postgres-compatible baseline)
CREATE TABLE IF NOT EXISTS raw_tick (
  venue TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  mid DOUBLE PRECISION,
  bid DOUBLE PRECISION,
  ask DOUBLE PRECISION,
  spread DOUBLE PRECISION,
  PRIMARY KEY (venue, symbol, ts)
);

CREATE TABLE IF NOT EXISTS raw_trade (
  venue TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  price DOUBLE PRECISION,
  qty DOUBLE PRECISION,
  side TEXT
);

CREATE TABLE IF NOT EXISTS orderbook_snapshot (
  venue TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  depth INTEGER,
  checksum TEXT,
  sequence BIGINT,
  PRIMARY KEY (venue, symbol, ts)
);

CREATE TABLE IF NOT EXISTS orderbook_level (
  venue TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  side TEXT,
  price DOUBLE PRECISION,
  qty DOUBLE PRECISION,
  num_orders INTEGER
);

CREATE TABLE IF NOT EXISTS featureset (
  feature_version TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  PRIMARY KEY (feature_version, symbol, ts)
);

CREATE TABLE IF NOT EXISTS feature_value (
  feature_version TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  name TEXT,
  value DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS forecast (
  model_version TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  horizon TEXT,
  mu DOUBLE PRECISION,
  sigma DOUBLE PRECISION,
  entropy DOUBLE PRECISION,
  PRIMARY KEY (model_version, symbol, ts, horizon)
);

CREATE TABLE IF NOT EXISTS forecast_quantile (
  model_version TEXT,
  symbol TEXT,
  ts TIMESTAMPTZ,
  horizon TEXT,
  q DOUBLE PRECISION,
  value DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS order_intent (
  intent_id TEXT PRIMARY KEY,
  symbol TEXT,
  side TEXT,
  qty DOUBLE PRECISION,
  reason TEXT,
  data_hash TEXT,
  model_version TEXT,
  feature_version TEXT,
  created_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  venue TEXT,
  symbol TEXT,
  side TEXT,
  qty DOUBLE PRECISION,
  limit_price DOUBLE PRECISION,
  status TEXT
);

CREATE TABLE IF NOT EXISTS fill (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT,
  ts TIMESTAMPTZ,
  qty DOUBLE PRECISION,
  price DOUBLE PRECISION,
  fee DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS position (
  symbol TEXT PRIMARY KEY,
  qty DOUBLE PRECISION,
  avg_price DOUBLE PRECISION,
  unrealized_pnl DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS risk_event (
  ts TIMESTAMPTZ,
  type TEXT,
  severity TEXT,
  action TEXT,
  payload JSONB
);
