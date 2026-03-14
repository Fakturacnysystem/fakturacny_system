#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-qwen2.5-coder:14b}"
PROMPT_FILE="${2:-/tmp/qwen_ultra_trading_prompt.txt}"

CTX="/tmp/local_agent_strict_context.txt"
OUT="/tmp/local_agent_strict_output.md"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama is not installed" >&2
  exit 1
fi

if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: ollama server is not running on 127.0.0.1:11434" >&2
  echo "Start it with: ollama serve" >&2
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

{
  echo "You are a senior autonomous trading systems engineer working locally on this repository."
  echo
  echo "Repository root: $(pwd)"
  echo
  echo "HARD INVARIANTS:"
  echo "- NEVER sell below entry price after fees and required minimum net profit floor."
  echo "- KEEP all fatal risk, drawdown, and exposure guards intact."
  echo "- NO weakening of hard sell-profit lock."
  echo "- Kraken SPOT only, long-only."
  echo "- No profit guarantees."
  echo
  echo "CURRENT FACTS:"
  echo "- Runtime blocker is dominated by entry_insufficient_quote."
  echo "- Usable quote is often below required minimum entry quote."
  echo "- Capital is trapped in existing holdings instead of free quote."
  echo "- Holdings include BTC, SOL, ADA, 0G."
  echo "- BTC and ADA appear profitable enough for safe recycle sells."
  echo "- SOL is marginal."
  echo "- 0G should not be force-sold below invariant floor."
  echo
  echo "MISSION:"
  echo "Read the repository first, then implement a capital-recycling and affordability-aware live trading improvement so the bot can operate at maximum safe throughput within all hard guards."
  echo
  echo "PRIMARY OBJECTIVES:"
  echo "1. Recycle capital from profitable existing spot holdings into free quote."
  echo "2. Reduce or eliminate impossible entry attempts caused by insufficient free quote."
  echo "3. Preserve the invariant that no sell may happen below entry after fees / min profit floor."
  echo "4. Increase autonomous live throughput only where affordable and safe."
  echo
  echo "REQUIRED IMPLEMENTATION FOCUS:"
  echo "- Sell-recycle logic from profitable holdings only."
  echo "- Prefer unlocking quote from existing profitable positions before suppressing all new entries."
  echo "- Maintain TP-only behavior unless a stricter existing invariant already applies."
  echo "- Improve affordability checks using exact free quote, reserve ratios, fee-aware required quote, and minimum notional."
  echo "- Resize entries to tradable affordable size before exchange submission."
  echo "- Reject impossible entries locally before submit."
  echo "- Reduce repeated churn when free quote is insufficient."
  echo "- Narrow active tradable universe for tiny accounts when needed."
  echo "- Prefer BTC / ADA / SOL recycle only if net-profit invariant remains satisfied."
  echo "- Never force-loss recycle on underwater assets."
  echo
  echo "CONFIG / RUNTIME INTENT:"
  echo "- Aim for an aggressive live profile, but only within hard safety limits."
  echo "- Use sell-recycle to unlock quote first."
  echo "- Lower sell targets only if still strictly above buy+fees+min_net_profit."
  echo "- Keep or improve cooldown and affordability diagnostics."
  echo
  echo "WORKFLOW:"
  echo "1. Read relevant files first."
  echo "2. Identify exact code paths causing entry_insufficient_quote churn."
  echo "3. Propose exact file-level changes."
  echo "4. Generate unified diffs where useful."
  echo "5. Run tests relevant to the changed logic."
  echo "6. Run runtime audit commands."
  echo "7. Summarize changes with hard evidence only."
  echo
  echo "RELEVANT FILES TO READ FIRST:"
  echo "- src/autonomous_investment_robot/core/orchestrator.py"
  echo "- src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py"
  echo "- src/autonomous_investment_robot/services/portfolio/sizing.py"
  echo "- src/autonomous_investment_robot/config/settings.py"
  echo "- scripts/run_kraken_ultra_profit_full_throttle.sh"
  echo "- scripts/runtime_audit.py"
  echo
  echo "ALSO INSPECT:"
  find src scripts tests -type f 2>/dev/null | sort | head -n 1400
  echo
  echo "AFFORDABILITY / SELL-RECYCLE SEARCH:"
  rg -n "entry_insufficient_quote|entry_affordability_hold|insufficient_balance|free_quote|fee_reserve|min_order|min_notional|quote reserve|sizing|sell_min_profit|tp_only|capital|recycle|profit" src scripts tests config* || true
  echo
  echo "LATEST RUNTIME AUDIT:"
  python3 scripts/runtime_audit.py --run-dir runs/kraken_ultra_profit_full_throttle --event-limit 500 2>/dev/null || true
  echo
  echo "USER TASK:"
  cat "$PROMPT_FILE"
} > "$CTX"

ollama run "$MODEL" < "$CTX" | tee "$OUT"
echo
echo "Saved output to: $OUT"
