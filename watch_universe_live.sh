#!/usr/bin/env bash
set -u

TOTAL_PHASES=25
COMPLETED_PHASES=8
ACTIVE_PHASE_LABEL="Phase 9 implementation + Phase 10-15 planning"
REFRESH_SECONDS=10

progress_bar() {
  local percent=$1
  local width=40
  local filled=$(( percent * width / 100 ))
  local empty=$(( width - filled ))
  printf "["
  printf "%0.s#" $(seq 1 $filled)
  printf "%0.s-" $(seq 1 $empty)
  printf "] %s%%" "$percent"
}

infer_phase9_progress() {
  local score=0

  [[ -f src/autonomous_investment_robot/services/universe_core/execution_intel.py ]] && score=$((score+35))
  [[ -f tests/test_universe_execution_phase9.py ]] && score=$((score+25))
  [[ -f docs/universe_core_phase9_completion_report.md ]] && score=$((score+25))

  if command -v rg >/dev/null 2>&1; then
    rg -n "ExecutionStressIndex|DynamicOrderSlicer|LiquidityVacuumDetector|PanicFlattenProtocol" \
      src/autonomous_investment_robot/services/universe_core >/dev/null 2>&1 && score=$((score+15))
  fi

  if (( score > 100 )); then score=100; fi
  echo "$score"
}

infer_total_progress() {
  local p9
  p9="$(infer_phase9_progress)"
  python3 - <<PY
completed=${COMPLETED_PHASES}
total=${TOTAL_PHASES}
phase9=${p9}
value=((completed + (phase9/100.0)) / total) * 100.0
print(f"{value:.1f}")
PY
}

last_commit() {
  git log -1 --oneline 2>/dev/null || echo "N/A"
}

changed_counts() {
  local modified untracked
  modified=$(git status --short 2>/dev/null | grep -c '^ M\|^M ' || true)
  untracked=$(git status --short 2>/dev/null | grep -c '^?? ' || true)
  echo "$modified|$untracked"
}

latest_phase_reports() {
  ls -1t docs/reports/PHASE_*_STRICT_COMPLETION_REPORT.md 2>/dev/null | head -5
}

universe_core_files() {
  find src/autonomous_investment_robot/services/universe_core -maxdepth 1 -type f 2>/dev/null | sed 's#^.*/##' | sort
}

pytest_quick_summary() {
  if [[ -f .pytest_cache/v/cache/lastfailed ]]; then
    echo "pytest cache: available"
  else
    echo "pytest cache: not found"
  fi
}

while true; do
  clear

  TOTAL_PROGRESS="$(infer_total_progress)"
  PHASE9_PROGRESS="$(infer_phase9_progress)"
  COUNTS="$(changed_counts)"
  MODIFIED_COUNT="${COUNTS%%|*}"
  UNTRACKED_COUNT="${COUNTS##*|}"

  printf "\n==================== UNIVERSE LIVE DASHBOARD ====================\n\n"

  printf "Repo: %s\n" "$(pwd)"
  printf "Branch: %s\n" "$(git branch --show-current 2>/dev/null || echo N/A)"
  printf "Last commit: %s\n\n" "$(last_commit)"

  printf "Completed phases: %s / %s\n" "$COMPLETED_PHASES" "$TOTAL_PHASES"
  printf "Overall project progress: "
  progress_bar "${TOTAL_PROGRESS%.*}"
  printf "   (odhad %.1f%%)\n" "$TOTAL_PROGRESS"

  printf "Phase 9 progress:        "
  progress_bar "$PHASE9_PROGRESS"
  printf "\n"

  printf "Active workstream: %s\n\n" "$ACTIVE_PHASE_LABEL"

  printf "Working tree:\n"
  printf "  Modified files : %s\n" "$MODIFIED_COUNT"
  printf "  Untracked files: %s\n\n" "$UNTRACKED_COUNT"

  printf "Universe Core files:\n"
  universe_core_files | sed 's/^/  - /'
  printf "\n"

  printf "Latest strict reports:\n"
  latest_phase_reports | sed 's/^/  - /'
  [[ $? -ne 0 ]] && echo "  - none found"
  printf "\n"

  printf "Quick test state:\n"
  printf "  %s\n\n" "$(pytest_quick_summary)"

  printf "Suggested manual checks:\n"
  printf "  1. git status --short\n"
  printf "  2. git diff --stat src/autonomous_investment_robot/services/universe_core tests docs\n"
  printf "  3. pytest -q tests/test_universe_core.py\n"
  printf "  4. pytest -q\n\n"

  printf "Refresh interval: %ss\n" "$REFRESH_SECONDS"
  printf "Stop: Ctrl+C\n"
  printf "=================================================================\n"

  sleep "$REFRESH_SECONDS"
done
