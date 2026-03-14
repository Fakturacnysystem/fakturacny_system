#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[smoke_test_live_compute_roundtrip] Running deterministic distributed roundtrip smoke test..."
pytest -q tests/test_distributed_e2e.py
echo "[smoke_test_live_compute_roundtrip] OK"
