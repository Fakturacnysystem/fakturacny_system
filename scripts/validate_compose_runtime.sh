#!/usr/bin/env bash
# validate_compose_runtime.sh
# Blocked-safe validator for Docker Compose infra stack.
# Can run on any host. Reports what is running vs what is expected.
# Does NOT fake success if infra is unavailable.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PASS=0
FAIL=0

check() {
    local label="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  PASS  $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Compose runtime validation ==="
echo ""

echo "--- Docker availability ---"
check "docker CLI present" "command -v docker"
check "docker daemon running" "docker info"
check "docker compose plugin" "docker compose version"
echo ""

echo "--- Compose file syntax ---"
check "infra/docker-compose.yml valid" "docker compose -f infra/docker-compose.yml config -q"
echo ""

echo "--- Service health (requires running stack) ---"
check "redis alive" "docker compose -f infra/docker-compose.yml exec -T redis redis-cli ping"
check "postgres alive" "docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U robot -d robot"
check "prometheus alive" "curl -sf http://localhost:9090/-/healthy"
check "grafana alive" "curl -sf http://localhost:3000/api/health"
echo ""

echo "--- Python environment ---"
check ".venv present" "test -d .venv"
check "pytest available" ".venv/bin/pytest --version"
check "full test suite green" ".venv/bin/pytest -q --tb=no"
echo ""

echo "=== Result ==="
echo "  PASSED: $PASS"
echo "  FAILED: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "STATUS: ALL CHECKS PASSED"
    exit 0
elif [ "$FAIL" -le 4 ]; then
    echo "STATUS: PARTIAL - likely missing infra (Docker/Redis/Postgres not running)"
    echo "  Run: cd infra && docker compose up -d"
    exit 1
else
    echo "STATUS: BLOCKED - multiple failures, check Docker and environment"
    exit 2
fi
