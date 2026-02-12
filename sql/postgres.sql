CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  venue TEXT,
  symbol TEXT,
  side TEXT,
  qty DOUBLE PRECISION,
  limit_price DOUBLE PRECISION,
  status TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT,
  ts TIMESTAMPTZ,
  qty DOUBLE PRECISION,
  price DOUBLE PRECISION,
  fee DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS positions (
  symbol TEXT PRIMARY KEY,
  qty DOUBLE PRECISION,
  avg_price DOUBLE PRECISION,
  unrealized_pnl DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS risk_events (
  ts TIMESTAMPTZ DEFAULT now(),
  type TEXT,
  severity TEXT,
  action TEXT,
  payload JSONB
);

CREATE TABLE IF NOT EXISTS reports (
  ts TIMESTAMPTZ DEFAULT now(),
  equity DOUBLE PRECISION,
  drawdown DOUBLE PRECISION,
  exposure DOUBLE PRECISION,
  notes TEXT
);
