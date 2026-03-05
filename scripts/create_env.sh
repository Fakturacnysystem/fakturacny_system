#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${1:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter '$PYTHON_BIN' was not found." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists, leaving it unchanged"
fi

echo "Environment created in $VENV_DIR"
echo "Activate it with: source $VENV_DIR/bin/activate"
echo "To install dependencies, run: pip install -e ."
