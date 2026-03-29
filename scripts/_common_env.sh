#!/usr/bin/env bash
set -euo pipefail

load_env_file_if_present() {
  local candidate=""
  local candidates=()
  if [[ -n "${TRADING_ENV_FILE:-}" ]]; then
    candidates+=("${TRADING_ENV_FILE}")
  fi
  if [[ -n "${SECRETS_DIR:-}" ]]; then
    candidates+=("${SECRETS_DIR}/trading-engine.env")
  fi
  candidates+=("/app/secrets/trading-engine.env" "./secrets/trading-engine.env")
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      set -a
      # shellcheck disable=SC1090
      . "${candidate}"
      set +a
      return 0
    fi
  done
  return 1
}

load_secret_file_env_if_missing() {
  local name="$1"
  local candidate=""
  local candidates=()
  if [[ -n "${!name:-}" ]]; then
    return 0
  fi
  if [[ -n "${SECRETS_DIR:-}" ]]; then
    candidates+=("${SECRETS_DIR}/${name}")
  fi
  candidates+=("/app/secrets/${name}" "./secrets/${name}")
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      export "${name}=$(tr -d '\r' < "${candidate}")"
      return 0
    fi
  done
  return 1
}

load_runtime_env_from_supported_sources() {
  load_env_file_if_present || true
  local names=(
    KRAKEN_SPOT_API_KEY
    KRAKEN_SPOT_API_SECRET
    ENABLE_LIVE_TRADING
    ACK_I_UNDERSTAND_RISKS
    ENABLE_FULL_LIVE_STAGE
    KRAKEN_SPOT_EVENT_FEED_PATH
  )
  local name=""
  for name in "${names[@]}"; do
    load_secret_file_env_if_missing "${name}" || true
  done
}

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

env_is_true() {
  local name="$1"
  [[ "${!name:-}" == "true" ]]
}

collect_missing_tiny_live_prereqs() {
  local missing=()
  [[ -n "${KRAKEN_SPOT_API_KEY:-}" ]] || missing+=("KRAKEN_SPOT_API_KEY")
  [[ -n "${KRAKEN_SPOT_API_SECRET:-}" ]] || missing+=("KRAKEN_SPOT_API_SECRET")
  env_is_true ENABLE_LIVE_TRADING || missing+=("ENABLE_LIVE_TRADING")
  env_is_true ACK_I_UNDERSTAND_RISKS || missing+=("ACK_I_UNDERSTAND_RISKS")
  local item=""
  for item in "${missing[@]:-}"; do
    [[ -n "${item}" ]] || continue
    printf '%s\n' "${item}"
  done
}

run_robot() {
  local py_bin
  py_bin="$(resolve_python_bin)"
  PYTHONPATH=src "${py_bin}" -m autonomous_investment_robot "$@"
}

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "${PYTHON_BIN}"
    return 0
  fi
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "${VIRTUAL_ENV}/bin/python"
    return 0
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  echo "python3 executable not found" >&2
  exit 1
}
