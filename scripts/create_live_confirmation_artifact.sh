#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_FILE="${1:-${ROOT_DIR}/ops/live_operator_confirmation.txt}"
APPROVAL_FILE="${2:-${ROOT_DIR}/ops/live_governance_approval.json}"
TARGET_DIR="$(dirname "${TARGET_FILE}")"
APPROVAL_DIR="$(dirname "${APPROVAL_FILE}")"

mkdir -p "${TARGET_DIR}"
mkdir -p "${APPROVAL_DIR}"
cat > "${TARGET_FILE}" <<'EOF'
I_CONFIRM_LIVE_TRADING
This file is a manual operator confirmation artifact required by the live safety gate.
Created by scripts/create_live_confirmation_artifact.sh.
EOF

APPROVER="${USER:-operator}"
APPROVAL_TS="$(date +%s)"
ARTIFACT_ID="approval-${APPROVER}-${APPROVAL_TS}"
cat > "${APPROVAL_FILE}" <<EOF
{
  "artifact_id": "${ARTIFACT_ID}",
  "stage": "limited_live_ready",
  "approved": true,
  "approver": "${APPROVER}",
  "approval_ts": ${APPROVAL_TS},
  "reason_codes": [
    "manual_dual_control_confirmation"
  ],
  "metadata": {
    "source": "create_live_confirmation_artifact.sh"
  }
}
EOF

echo "[create_live_confirmation_artifact] Wrote confirmation artifact: ${TARGET_FILE}"
echo "[create_live_confirmation_artifact] Wrote operator approval artifact: ${APPROVAL_FILE}"
echo "[create_live_confirmation_artifact] To enable live startup in this shell:"
echo "  export AUTONOMOUS_LIVE_GO=1"
echo "  export AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE=${TARGET_FILE}"
echo "  export AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE=${APPROVAL_FILE}"
