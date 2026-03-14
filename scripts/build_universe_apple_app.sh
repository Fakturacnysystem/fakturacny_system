#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/apps/universe-control-center-apple"
XCODE_APP="${XCODE_APP:-/Applications/Xcode.app}"
DEVELOPER_DIR_PATH="${XCODE_APP}/Contents/Developer"

if ! command -v xcodegen >/dev/null 2>&1; then
  echo "[build_universe_apple_app] xcodegen missing. Install with: brew install xcodegen" >&2
  exit 2
fi
if [[ ! -d "${XCODE_APP}" ]]; then
  echo "[build_universe_apple_app] full Xcode not found at ${XCODE_APP}" >&2
  echo "[build_universe_apple_app] install Xcode from App Store, then rerun this script" >&2
  exit 2
fi

cd "${APP_DIR}"
xcodegen generate
DEVELOPER_DIR="${DEVELOPER_DIR_PATH}" xcodebuild -project UniverseControlCenterApple.xcodeproj -scheme UniverseControlCenter -destination 'generic/platform=macOS' CODE_SIGNING_ALLOWED=NO build
DEVELOPER_DIR="${DEVELOPER_DIR_PATH}" xcodebuild -project UniverseControlCenterApple.xcodeproj -scheme UniverseControlCenter -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
