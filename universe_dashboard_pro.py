#!/usr/bin/env python3
import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path

REFRESH_SECONDS = 2.0
TOTAL_PHASES = 25

ROOT = Path.cwd()
DOCS_REPORTS = ROOT / "docs" / "reports"
UC_DIR = ROOT / "src" / "autonomous_investment_robot" / "services" / "universe_core"

# Current known Codex runs from latest successful monitoring
RUNS = [
    ("Phase 9 execution hardening", "run_3e2d4a7c58604f31a639d1cec0bd4268", "SUCCEEDED"),
    ("Phase 10–15 roadmap planning", "run_4d94ad30ba1c4e09a54a46959aa83265", "SUCCEEDED"),
]

# ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

ALT_ON = "\033[?1049h"
ALT_OFF = "\033[?1049l"
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
HOME = "\033[H"

def run(cmd: str) -> str:
    try:
        out = subprocess.check_output(cmd, shell=True, cwd=ROOT, stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return ""

def count_completed_phases():
    if not DOCS_REPORTS.exists():
        return 0
    return len(list(DOCS_REPORTS.glob("PHASE_*_STRICT_COMPLETION_REPORT.md")))

def latest_phase_number():
    nums = []
    if DOCS_REPORTS.exists():
        for f in DOCS_REPORTS.glob("PHASE_*_STRICT_COMPLETION_REPORT.md"):
            m = re.search(r"PHASE_(\d+)_", f.name)
            if m:
                nums.append(int(m.group(1)))
    return max(nums) if nums else 0

def infer_current_phase_progress():
    latest = latest_phase_number()
    current = latest + 1
    score = 0

    if current == 9:
        if (UC_DIR / "execution_intel.py").exists():
            score += 35
        if (ROOT / "tests" / "test_universe_execution_phase9.py").exists():
            score += 25
        if (ROOT / "docs" / "universe_core_phase9_completion_report.md").exists():
            score += 25
        text = run("rg -n 'ExecutionStressIndex|DynamicOrderSlicer|LiquidityVacuumDetector|PanicFlattenProtocol' src/autonomous_investment_robot/services/universe_core")
        if text:
            score += 15
    elif current == 10:
        if (ROOT / "docs" / "universe_core_phase10_completion_report.md").exists():
            score = 100
        else:
            score = 10
    else:
        if (ROOT / f"docs/universe_core_phase{current}_completion_report.md").exists():
            score = 100
        else:
            score = 0
    return min(score, 100)

def overall_progress():
    completed = count_completed_phases()
    curr = infer_current_phase_progress()
    return round(((completed + curr / 100.0) / TOTAL_PHASES) * 100.0, 1)

def top1_readiness():
    completed = count_completed_phases()
    if completed >= 15:
        return 78
    if completed >= 12:
        return 65
    if completed >= 9:
        return 56
    if completed >= 8:
        return 48
    return 30

def progress_bar(percent: int, width: int = 28, color: str = CYAN):
    filled = int(width * percent / 100)
    empty = width - filled
    return f"{color}{'█'*filled}{DIM}{'░'*empty}{RESET} {percent}%"

def git_branch():
    return run("git branch --show-current") or "N/A"

def last_commit():
    return run("git log -1 --oneline") or "N/A"

def recent_commits():
    out = run("git log --oneline -5")
    return out.splitlines() if out else []

def git_counts():
    status = run("git status --short")
    modified = 0
    untracked = 0
    if status:
        for line in status.splitlines():
            if line.startswith("?? "):
                untracked += 1
            elif "M" in line[:2]:
                modified += 1
    return modified, untracked

def latest_reports():
    if not DOCS_REPORTS.exists():
        return []
    files = sorted(DOCS_REPORTS.glob("PHASE_*_STRICT_COMPLETION_REPORT.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [f.name for f in files[:5]]

def latest_report_tail():
    if not DOCS_REPORTS.exists():
        return []
    files = sorted(DOCS_REPORTS.glob("PHASE_*_STRICT_COMPLETION_REPORT.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return []
    try:
        return files[0].read_text(encoding="utf-8", errors="ignore").splitlines()[-8:]
    except Exception:
        return []

def universe_core_files():
    if not UC_DIR.exists():
        return []
    return sorted([p.name for p in UC_DIR.glob("*.py")])

def pytest_status_hint():
    cache = ROOT / ".pytest_cache" / "v" / "cache" / "lastfailed"
    if cache.exists():
        try:
            size = cache.stat().st_size
            if size > 5:
                return f"{YELLOW}pytest cache remembers prior failures{RESET}"
            return f"{GREEN}pytest cache clean / no remembered failures{RESET}"
        except Exception:
            return f"{YELLOW}pytest cache unreadable{RESET}"
    return f"{DIM}pytest cache unavailable{RESET}"

def suggestions():
    completed = count_completed_phases()
    lines = [
        "Dokončiť vždy: strict report + commit + tag + green full pytest",
        "Držať Universe Core additive, typed, replay-safe a rollback-safe",
        "Neoslabiť hard safety doctrine ani manual live gate",
    ]
    if completed < 9:
        lines.append("Najvyšší impact: Phase 9 execution alpha, slippage resilience, fill quality")
    elif completed < 10:
        lines.append("Najvyšší impact: Phase 10 rollout governance a operator approval artifacts")
    elif completed < 12:
        lines.append("Najvyšší impact: Global Market Brain + causal context + state divergence checks")
    else:
        lines.append("Najvyšší impact: future simulation + cross-reality fusion + capital survival doctrine")
    lines.append("Sledovať: shield escalations, fill quality, execution stress, replay determinism")
    return lines

def fit(text, width):
    if len(text) <= width:
        return text + " " * (width - len(text))
    if width <= 1:
        return text[:width]
    return text[: max(0, width - 1)] + "…"

def box(title, lines, width):
    inner = max(10, width - 2)
    out = []
    out.append(f"┌{fit(f' {title} ', inner).replace('─','-')}┐")
    for line in lines:
        out.append(f"│{fit(line, inner)}│")
    out.append(f"└{'─'*inner}┘")
    return out

def render():
    cols, rows = shutil.get_terminal_size((120, 36))

    completed = count_completed_phases()
    latest = latest_phase_number()
    current = latest + 1
    current_progress = infer_current_phase_progress()
    overall = overall_progress()
    readiness = top1_readiness()
    modified, untracked = git_counts()

    left_width = max(58, cols // 2)
    right_width = cols - left_width - 1

    left = []
    left += box(f"{BOLD}{CYAN}UNIVERSE CORE LIVE STATUS{RESET}", [
        f"{BOLD}Repo:{RESET} {ROOT}",
        f"{BOLD}Branch:{RESET} {git_branch()}",
        f"{BOLD}Last commit:{RESET} {last_commit()}",
        "",
        f"Completed phases       : {completed} / {TOTAL_PHASES}",
        f"Latest completed phase : {latest}",
        f"Current active phase   : {current}",
        f"Overall completion     : {progress_bar(int(overall), 24, GREEN)}  ({overall:.1f}%)",
        f"Top 1% readiness       : {progress_bar(readiness, 24, MAGENTA)}",
    ], left_width)

    left += [""]
    left += box(f"{BOLD}{BLUE}REPO HEALTH{RESET}", [
        f"Modified tracked files : {YELLOW}{modified}{RESET}",
        f"Untracked files        : {YELLOW}{untracked}{RESET}",
        f"Pytest hint            : {pytest_status_hint()}",
        "",
        "Current phase heuristic progress:",
        progress_bar(current_progress, 24, CYAN),
    ], left_width)

    left += [""]
    left += box(f"{BOLD}{GREEN}CURRENT CODEX RUNS{RESET}", [
        f"{GREEN}●{RESET} {RUNS[0][0]}  [{RUNS[0][2]}]",
        f"   {DIM}{RUNS[0][1]}{RESET}",
        f"{GREEN}●{RESET} {RUNS[1][0]}  [{RUNS[1][2]}]",
        f"   {DIM}{RUNS[1][1]}{RESET}",
        "",
        "Poznámka: táto verzia dashboardu číta stav projektu hladko z repa.",
        "Ak budeš chcieť, ďalšia verzia vie ťahať live Codex run statusy z bridge API.",
    ], left_width)

    reports = latest_reports() or ["žiadne strict reporty"]
    right = []
    right += box(f"{BOLD}{MAGENTA}LATEST STRICT REPORTS{RESET}", [f"• {x}" for x in reports], right_width)
    right += [""]
    tail = latest_report_tail() or ["žiadny report tail"]
    right += box(f"{BOLD}{CYAN}LATEST REPORT TAIL{RESET}", tail, right_width)
    right += [""]
    commits = recent_commits() or ["žiadne commity"]
    right += box(f"{BOLD}{BLUE}RECENT COMMITS{RESET}", commits, right_width)
    right += [""]
    right += box(f"{BOLD}{YELLOW}HIGH-VALUE IMPROVEMENTS{RESET}", [f"• {x}" for x in suggestions()], right_width)

    max_lines = max(len(left), len(right), rows - 2)
    left += [""] * (max_lines - len(left))
    right += [""] * (max_lines - len(right))

    frame = []
    frame.append(f"{BOLD}{WHITE}UNIVERSE DASHBOARD PRO{RESET}   {DIM}smooth mode • no flicker • no scroll • ctrl+c to exit{RESET}")
    frame.append("")

    for i in range(max_lines - 2):
        l = fit(left[i], left_width)
        r = fit(right[i], right_width)
        frame.append(f"{l} {r}")

    frame.append("")
    frame.append(f"{DIM}Refresh interval: {REFRESH_SECONDS:.1f}s | Current phase target: Phase {current}{RESET}")
    return "\n".join(frame)

def main():
    sys.stdout.write(ALT_ON + CURSOR_HIDE)
    sys.stdout.flush()
    try:
        last = None
        while True:
            frame = render()
            if frame != last:
                sys.stdout.write(HOME)
                sys.stdout.write(frame)
                sys.stdout.flush()
                last = frame
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(CURSOR_SHOW + ALT_OFF + RESET)
        sys.stdout.flush()

if __name__ == "__main__":
    main()
