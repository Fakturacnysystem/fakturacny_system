#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_true_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
  if [[ "${!name}" != "true" ]]; then
    echo "Env var must be set to true: ${name}" >&2
    exit 1
  fi
}

run_robot() {
  PYTHONPATH=src python3 -m autonomous_investment_robot "$@"
}
