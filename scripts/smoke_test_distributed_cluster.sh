#!/usr/bin/env bash
# smoke_test_distributed_cluster.sh
# Blocked-safe smoke test for future distributed cluster setup.
# Currently: internal implementation is ABSENT (services/distributed/ is empty).
# This script validates as much as possible without running cluster,
# and classifies remaining blockers explicitly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Distributed Cluster Smoke Test ==="
echo ""
echo "HONEST STATUS: Internal distributed wiring is NOT implemented."
echo "This script verifies infra prerequisites and reports what is blocked."
echo ""

PASS=0
FAIL=0
BLOCKED=0

check() {
    local label="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  PASS     $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL     $label"
        FAIL=$((FAIL + 1))
    fi
}

blocked() {
    echo "  BLOCKED  $1"
    BLOCKED=$((BLOCKED + 1))
}

echo "--- Infra prerequisites ---"
check "docker available" "command -v docker"
check "docker compose available" "docker compose version"
check "infra/docker-compose.yml valid" "docker compose -f infra/docker-compose.yml config -q"
check "redis service reachable" "docker compose -f infra/docker-compose.yml exec -T redis redis-cli ping"
check "postgres service reachable" "docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U robot -d robot"
echo ""

echo "--- Python distributed backend ---"
if [ -f "src/autonomous_investment_robot/services/distributed/redis_backend.py" ]; then
    check "redis_backend.py importable" ".venv/bin/python -c 'from autonomous_investment_robot.services.distributed.redis_backend import RedisStreams'"
else
    blocked "services/distributed/redis_backend.py (NOT IMPLEMENTED)"
fi
echo ""

echo "--- Environment variables ---"
if [ -n "${REDIS_URL:-}" ]; then
    echo "  PASS     REDIS_URL set"
    PASS=$((PASS + 1))
else
    blocked "REDIS_URL env var (not set — required for Redis backend)"
fi
if [ -n "${POSTGRES_DSN:-}" ]; then
    echo "  PASS     POSTGRES_DSN set"
    PASS=$((PASS + 1))
else
    blocked "POSTGRES_DSN env var (not set — required for Postgres mirror)"
fi
echo ""

echo "--- End-to-end distributed roundtrip ---"
blocked "live-node -> Redis -> compute-node roundtrip (NOT IMPLEMENTED)"
blocked "Postgres mirror write proof (NOT IMPLEMENTED)"
blocked "Distributed event store backend (NOT IMPLEMENTED)"
echo ""

echo "=== Summary ==="
echo "  PASSED:  $PASS"
echo "  FAILED:  $FAIL"
echo "  BLOCKED: $BLOCKED"
echo ""
echo "To unblock distributed mode:"
echo "  1. Implement services/distributed/redis_backend.py"
echo "  2. Implement services/storage/postgres_mirror.py"
echo "  3. Add REDIS_URL and POSTGRES_DSN to .env"
echo "  4. Run: cd infra && docker compose up -d"
echo "  5. Re-run this script"
echo ""
echo "See docs/redis_postgres_validation.md and docs/architecture_truth.md for full details."
