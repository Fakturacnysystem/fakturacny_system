#!/usr/bin/env bash
set -euo pipefail

load_env_assignments_if_missing() {
  local candidate="$1"
  local line=""
  local name=""
  local value=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -n "${line//[[:space:]]/}" ]] || continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    if [[ "${line}" =~ ^[[:space:]]*export[[:space:]]+ ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ "${line}" == *=* ]] || continue
    name="${line%%=*}"
    value="${line#*=}"
    name="${name#"${name%%[![:space:]]*}"}"
    name="${name%"${name##*[![:space:]]}"}"
    value="${value%$'\r'}"
    if [[ ${#value} -ge 2 ]]; then
      if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    if [[ -n "${!name:-}" ]]; then
      continue
    fi
    export "${name}=${value}"
  done < "${candidate}"
}

load_env_file_if_present() {
  local candidate=""
  local candidates=()
  if [[ -n "${TRADING_ENV_FILE:-}" ]]; then
    candidates+=("${TRADING_ENV_FILE}")
  elif [[ -n "${SECRETS_DIR:-}" ]]; then
    candidates+=("${SECRETS_DIR}/trading-engine.env")
  else
    candidates+=("/app/secrets/trading-engine.env" "./secrets/trading-engine.env")
    candidates+=(
      "${HOME}/.config/trading-bot/runtime.env"
      "${HOME}/.config/trading-bot/trading-engine.env"
    )
  fi
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      load_env_assignments_if_missing "${candidate}"
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
  else
    candidates+=("/app/secrets/${name}" "./secrets/${name}")
  fi
  candidates+=(
    "${HOME}/.config/trading-bot/${name}"
    "${HOME}/.config/trading-bot/secrets/${name}"
  )
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

resolve_repo_root() {
  local script_source=""
  script_source="${BASH_SOURCE[0]:-$0}"
  cd "$(dirname "${script_source}")/.." && pwd
}

resolve_python_bin() {
  local repo_root=""
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "${PYTHON_BIN}"
    return 0
  fi
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "${VIRTUAL_ENV}/bin/python"
    return 0
  fi
  if [[ -n "${REPO_VENV_DIR:-}" && -x "${REPO_VENV_DIR}/bin/python" ]]; then
    echo "${REPO_VENV_DIR}/bin/python"
    return 0
  fi
  repo_root="$(resolve_repo_root)"
  if [[ -x "${repo_root}/.venv/bin/python" ]]; then
    echo "${repo_root}/.venv/bin/python"
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
