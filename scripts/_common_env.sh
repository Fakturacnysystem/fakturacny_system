#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

resolve_python_bin() {
  local python_bin="${PYTHON_BIN:-}"
  if [[ -n "${python_bin}" && -x "${python_bin}" ]]; then
    printf '%s\n' "${python_bin}"
    return 0
  fi
  if [[ -x ".venv/bin/python" ]]; then
    printf '%s\n' ".venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  echo "No python interpreter available (expected .venv/bin/python or python3)." >&2
  return 1
}

run_robot() {
  local python_bin
  python_bin="$(resolve_python_bin)"
  PYTHONPATH=src "${python_bin}" -m autonomous_investment_robot "$@"
}
