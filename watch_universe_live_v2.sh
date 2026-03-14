#!/usr/bin/env bash
set -u

REFRESH_SECONDS=8
TOTAL_PHASES=25

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

progress_bar() {
  local percent="$1"
  local width=36
  local filled=$(( percent * width / 100 ))
  local empty=$(( width - filled ))
  printf "["
  for _ in $(seq 1 "$filled"); do printf "#"; done
  for _ in $(seq 1 "$empty"); do printf "-"; done
  printf "] %s%%" "$percent"
}

count_completed_phases() {
  local count
  count=$(find docs/reports -maxdepth 1 -type f -name 'PHASE_*_STRICT_COMPLETION_REPORT.md' 2>/dev/null | wc -l | tr -d ' ')
  echo "${count:-0}"
}

latest_phase_number() {
  local latest
  latest=$(find docs/reports -maxdepth 1 -type f -name 'PHASE_*_STRICT_COMPLETION_REPORT.md' 2>/dev/null \
    | sed -E 's#.*PHASE_([0-9]+)_.*#\1#' | sort -n | tail -1)
  echo "${latest:-0}"
}

infer_current_phase_progress() {
  local latest_phase current_phase score=0
  latest_phase=$(latest_phase_number)
  current_phase=$(( latest_phase + 1 ))

  case "$current_phase" in
    9)
      [[ -f src/autonomous_investment_robot/services/universe_core/execution_intel.py ]] && score=$((score+35))
      [[ -f tests/test_universe_execution_phase9.py ]] && score=$((score+25))
      [[ -f docs/universe_core_phase9_completion_report.md ]] && score=$((score+25))
      command -v rg >/dev/null 2>&1 && rg -n "ExecutionStressIndex|DynamicOrderSlicer|LiquidityVacuumDetector|PanicFlattenProtocol" src/autonomous_investment_robot/services/universe_core >/dev/null 2>&1 && score=$((score+15))
      ;;
    10)
      [[ -f docs/universe_core_phase10_completion_report.md ]] && score=100 || score=15
      ;;
    *)
      [[ -f docs/universe_core_phase${current_phase}_completion_report.md ]] && score=100 || score=0
      ;;
  esac

  (( score > 100 )) && score=100
  echo "$score"
}

overall_progress() {
  local completed current_progress
  completed=$(count_completed_phases)
  current_progress=$(infer_current_phase_progress)
  python3 - <<PY
completed=${completed}
total=${TOTAL_PHASES}
curr=${current_progress}
value=((completed + (curr/100.0)) / total) * 100.0
print(f"{value:.1f}")
PY
}

top1_readiness() {
  local completed
  completed=$(count_completed_phases)
  if (( completed >= 15 )); then
    echo "78"
  elif (( completed >= 12 )); then
    echo "65"
  elif (( completed >= 9 )); then
    echo "52"
  elif (( completed >= 8 )); then
    echo "45"
  else
    echo "30"
  fi
}

git_counts() {
  local modified untracked
  modified=$(git status --short 2>/dev/null | grep -c '^ M\|^M ' || true)
  untracked=$(git status --short 2>/dev/null | grep -c '^?? ' || true)
  echo "$modified|$untracked"
}

latest_commit() {
  git log -1 --oneline 2>/dev/null || echo "N/A"
}

recent_commits() {
  git log --oneline -5 2>/dev/null
}

latest_reports() {
  ls -1t docs/reports/PHASE_*_STRICT_COMPLETION_REPORT.md 2>/dev/null | head -5
}

tail_latest_report() {
  local file
  file=$(ls -1t docs/reports/PHASE_*_STRICT_COMPLETION_REPORT.md 2>/dev/null | head -1)
  [[ -n "${file:-}" ]] && tail -8 "$file"
}

pytest_status_line() {
  if [[ -f .pytest_cache/v/cache/lastfailed ]]; then
    local size
    size=$(wc -c < .pytest_cache/v/cache/lastfailed 2>/dev/null || echo "0")
    if [[ "$size" -gt 5 ]]; then
      echo "lastfailed cache indicates prior failures"
    else
      echo "pytest cache clean / no remembered failures"
    fi
  else
    echo "pytest cache unavailable"
  fi
}

suggestions_block() {
  local completed
  completed=$(count_completed_phases)

  echo "- Finish current active phase with strict report + commit checkpoint"
  echo "- Keep Universe Core additive; avoid broad repo churn"
  echo "- Focus next on execution alpha, rollout governance, and market brain"

  if (( completed < 9 )); then
    echo "- Highest impact now: Phase 9 execution hardening"
  elif (( completed < 10 )); then
    echo "- Highest impact now: Phase 10 rollout governance and activation control"
  elif (( completed < 12 )); then
    echo "- Highest impact now: Global Market Brain + causal context"
  else
    echo "- Highest impact now: future simulation + cross-reality fusion"
  fi

  echo "- Track live metrics: slippage, fill quality, shield escalations, replay determinism"
  echo "- Require every phase to end with: tests green + strict report + commit + tag"
}

while true; do
  clear

  COMPLETED="$(count_completed_phases)"
  LATEST_PHASE="$(latest_phase_number)"
  CURRENT_PHASE=$(( LATEST_PHASE + 1 ))
  CURR_PROGRESS="$(infer_current_phase_progress)"
  OVERALL="$(overall_progress)"
  TOP1="$(top1_readiness)"
  COUNTS="$(git_counts)"
  MODIFIED="${COUNTS%%|*}"
  UNTRACKED="${COUNTS##*|}"

  echo -e "${BOLD}${CYAN}==================== UNIVERSE CORE LIVE DASHBOARD v2 ====================${NC}"
  echo
  echo -e "${BOLD}Repo:${NC} $(pwd)"
  echo -e "${BOLD}Branch:${NC} $(git branch --show-current 2>/dev/null || echo N/A)"
  echo -e "${BOLD}Last commit:${NC} $(latest_commit)"
  echo

  echo -e "${BOLD}${BLUE}PROJECT STATUS${NC}"
  printf "Completed phases        : %s / %s\n" "$COMPLETED" "$TOTAL_PHASES"
  printf "Latest completed phase  : %s\n" "$LATEST_PHASE"
  printf "Current active phase    : %s\n" "$CURRENT_PHASE"
  printf "Overall completion      : "
  progress_bar "${OVERALL%.*}"
  printf "  ${DIM}(%.1f%% estimated)${NC}\n" "$OVERALL"
  printf "Current phase progress  : "
  progress_bar "$CURR_PROGRESS"
  printf "\n"
  printf "Top 1%% readiness        : "
  progress_bar "$TOP1"
  printf "  ${DIM}(architectural maturity estimate)${NC}\n"
  echo

  echo -e "${BOLD}${MAGENTA}REPO HEALTH${NC}"
  echo -e "Modified tracked files  : ${YELLOW}${MODIFIED}${NC}"
  echo -e "Untracked files         : ${YELLOW}${UNTRACKED}${NC}"
  echo -e "Pytest quick state      : $(pytest_status_line)"
  echo

  echo -e "${BOLD}${GREEN}LATEST STRICT REPORTS${NC}"
  latest_reports | sed 's/^/  - /'
  echo

  echo -e "${BOLD}${BLUE}LIVE REPORT TAIL${NC}"
  tail_latest_report 2>/dev/null | sed 's/^/  /'
  echo

  echo -e "${BOLD}${CYAN}RECENT COMMITS${NC}"
  recent_commits | sed 's/^/  /'
  echo

  echo -e "${BOLD}${MAGENTA}TOP IMPROVEMENT SUGGESTIONS${NC}"
  suggestions_block | sed 's/^/  • /'
  echo

  echo -e "${BOLD}${GREEN}USEFUL COMMANDS${NC}"
  echo "  git status --short"
  echo "  git diff --stat src/autonomous_investment_robot/services/universe_core tests docs"
  echo "  pytest -q tests/test_universe_core.py"
  echo "  pytest -q"
  echo

  echo -e "${DIM}Refresh: ${REFRESH_SECONDS}s | Stop: Ctrl+C${NC}"
  echo -e "${BOLD}${CYAN}=======================================================================${NC}"

  sleep "$REFRESH_SECONDS"
done
