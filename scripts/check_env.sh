#!/usr/bin/env bash
set -euo pipefail
missing=()
for k in KRAKEN_API_KEY KRAKEN_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; do
  if [[ -z "${!k:-}" ]]; then missing+=("$k"); fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  printf '%s\n' "${missing[@]}"
fi
