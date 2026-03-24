#!/usr/bin/env bash
set -euo pipefail

files="$(git ls-files)"
if [ -z "$files" ]; then
  exit 0
fi

if rg -n --no-messages \
  --regexp="-----BEGIN [A-Z ]*PRIVATE KEY-----" \
  --regexp="AKIA[0-9A-Z]{16}" \
  --regexp="ghp_[0-9A-Za-z]{36}" \
  --regexp="sk-(live|test)-[0-9A-Za-z]{16,}" \
  --regexp="AIza[0-9A-Za-z\\-_]{35}" \
  $files; then
  echo "Potential secret detected in tracked files"
  exit 1
fi
