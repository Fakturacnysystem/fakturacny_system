#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-config.kraken_spot.live_profit.yaml}"
CONFIRM_FILE="${AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE:-${ROOT_DIR}/ops/live_operator_confirmation.txt}"
APPROVAL_FILE="${AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE:-${ROOT_DIR}/ops/live_governance_approval.json}"

if [[ ! -f "${CONFIRM_FILE}" ]]; then
  echo "[live_unlock_check] missing confirmation file: ${CONFIRM_FILE}" >&2
  exit 2
fi
if [[ ! -f "${APPROVAL_FILE}" ]]; then
  echo "[live_unlock_check] missing approval artifact: ${APPROVAL_FILE}" >&2
  exit 2
fi

export AUTONOMOUS_LIVE_GO="${AUTONOMOUS_LIVE_GO:-1}"
export AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE="${CONFIRM_FILE}"
export AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE="${APPROVAL_FILE}"

echo "[live_unlock_check] running paper rollback validation"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/safety_preflight.py" --config "${CONFIG_PATH}" --target-mode paper

echo "[live_unlock_check] running live preflight"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/safety_preflight.py" --config "${CONFIG_PATH}" --target-mode live
