#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "${SCRIPT_DIR}/_common_env.sh"
load_runtime_env_from_supported_sources

missing_json=""
while IFS= read -r missing_item; do
  [[ -n "${missing_item}" ]] || continue
  if [[ -n "${missing_json}" ]]; then
    missing_json="${missing_json},"
  fi
  missing_json="${missing_json}\"${missing_item}\""
done < <(collect_missing_tiny_live_prereqs)

if [[ -n "${missing_json}" ]]; then
  printf '{"event":"container_bootstrap","mode":"readonly_fallback","reason":"missing_tiny_live_prerequisites","missing":[%s]}\n' "${missing_json}" >&2
  if [[ "${CONTAINER_BOOT_READONLY_ONCE:-false}" == "true" ]]; then
    exec bash "${SCRIPT_DIR}/run_kraken_spot_readonly_analysis.sh"
  fi

  readonly_interval="${READONLY_FALLBACK_INTERVAL_SECONDS:-300}"
  case "${readonly_interval}" in
    ''|*[!0-9]*)
      readonly_interval=300
      ;;
  esac
  if (( readonly_interval < 30 )); then
    readonly_interval=30
  fi

  while true; do
    if ! bash "${SCRIPT_DIR}/run_kraken_spot_readonly_analysis.sh"; then
      printf '{"event":"container_bootstrap","mode":"readonly_fallback","reason":"readonly_iteration_failed"}\n' >&2
    fi
    sleep "${readonly_interval}"
  done
fi

exec bash "${SCRIPT_DIR}/run_kraken_spot_tiny_live.sh"
