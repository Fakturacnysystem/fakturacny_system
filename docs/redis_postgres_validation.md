# Redis / Postgres / Distributed Backend – Validation Status

**Last updated:** 2026-03-16
**Honest classification:** INTERNAL WIRING ABSENT — EXTERNALLY BLOCKED

---

## Current state (hard truth)

| Backend | Status | Code wiring | Runtime proof |
|---------|--------|-------------|---------------|
| Redis | NOT WIRED | No import anywhere in src/ | None |
| PostgreSQL | NOT WIRED | No import (asyncpg/psycopg/sqlalchemy) in src/ | None |
| ClickHouse | NOT WIRED | No import in src/ | None |
| MinIO | NOT WIRED | No import in src/ | None |
| NATS | NOT WIRED | No import in src/ | None |
| Prometheus | WIRED (metrics file) | OpsService exports .prom file | Local file only |
| Grafana | INFRA ONLY | No active queries; dashboards defined | None |

**Current persistence:** Local JSONL append-only logs in `run_dir`. Single-machine only.

---

## Infrastructure definition

All infra services are defined in `infra/docker-compose.yml`. They start cleanly but the Python
process does not connect to any of them (except Prometheus via file export).

---

## Internal blockers (fixable without external infra)

None remaining for Redis/Postgres. The directories exist as stubs:

```
src/autonomous_investment_robot/services/distributed/   # empty
src/autonomous_investment_robot/services/storage/       # empty
```

To connect Redis, an implementer needs to:
1. Add `redis>=5.0` to `pyproject.toml [project.dependencies]`
2. Implement `services/distributed/redis_backend.py` with a `RedisStreams` class
3. Add `REDIS_URL` env var support in `config/settings.py`
4. Wire backend selection in `EventStore` or a new `BackendRouter`

To connect Postgres, an implementer needs to:
1. Add `psycopg[binary]>=3.0` to dependencies
2. Implement `services/storage/postgres_mirror.py`
3. Add `POSTGRES_DSN` env var support in settings
4. Wire as a mirror sink in EventStore writes

---

## External blockers (cannot be resolved without infra)

- Docker runtime: required to start Redis/Postgres containers
- Redis runtime proof: requires `REDIS_URL` pointing to live Redis
- Postgres runtime proof: requires `POSTGRES_DSN` pointing to live Postgres

---

## Proof commands (run after infra is available)

```bash
# Start infra stack
cd infra && docker compose up -d redis postgres prometheus grafana

# Verify Redis is up
redis-cli -u redis://localhost:6379 ping
# Expected: PONG

# Verify Postgres is up
psql postgresql://robot:robot@localhost:5432/robot -c "SELECT 1;"
# Expected: 1 row

# Run paper robot and verify Prometheus metrics file
PYTHONPATH=src python3 -m autonomous_investment_robot run \
  --config config.perps_intraday.paper.yaml --once
# Expected: metrics file written to run_dir/metrics.prom

# Verify Prometheus scrapes (after prometheus container running)
curl http://localhost:9090/api/v1/query?query=robot_orders_submitted_total
# Expected: JSON with metric value
```

---

## Expected proof artifacts

After full distributed wiring (future work):
- `runs/<run_id>/redis_backend_proof.json` — confirms backend=redis_streams
- `runs/<run_id>/postgres_mirror_proof.json` — confirms row-level write
- `runs/<run_id>/distributed_roundtrip.json` — live→compute→result roundtrip

---

## Completion classification

| Item | Classification |
|------|---------------|
| Internal implementation | ABSENT (stubs only) |
| Infra definition | PRESENT (docker-compose.yml) |
| Internal blockers | NONE (nothing to fix without infra) |
| External blockers | Docker + Redis + Postgres runtime |
| Honest completion % | 5% (infra defined, zero code wiring) |
