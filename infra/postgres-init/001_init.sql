CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  venue TEXT,
  symbol TEXT,
  side TEXT,
  notional DOUBLE PRECISION,
  state TEXT,
  idempotency_key TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_events (
  ts TIMESTAMPTZ DEFAULT now(),
  order_id TEXT,
  state TEXT,
  payload JSONB
);

CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT,
  venue TEXT,
  ts TIMESTAMPTZ,
  notional DOUBLE PRECISION,
  fee DOUBLE PRECISION,
  slippage_cost DOUBLE PRECISION,
  idempotency_key TEXT
);

CREATE TABLE IF NOT EXISTS positions (
  symbol TEXT PRIMARY KEY,
  exposure_notional DOUBLE PRECISION,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_events (
  ts TIMESTAMPTZ DEFAULT now(),
  type TEXT,
  severity TEXT,
  action TEXT,
  payload JSONB
);

CREATE TABLE IF NOT EXISTS compliance_events (
  ts TIMESTAMPTZ DEFAULT now(),
  provider TEXT,
  allowed BOOLEAN,
  reason TEXT
);
