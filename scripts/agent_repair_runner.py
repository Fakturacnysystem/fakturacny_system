#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs" / "auto_repair"
DEFAULT_BLUEPRINT = ROOT / "docs" / "AURORA_BLUEPRINT_MASTER_AGENT_SPEC.md"


@dataclass
class CommandResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImportCheck:
    module: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_cmd(
    cmd: list[str],
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> CommandResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def read_blueprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "size_bytes": 0,
            "head": "",
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "head": text[:4000],
    }


def list_key_paths() -> dict[str, list[str]]:
    patterns = {
        "core": [
            "src/autonomous_investment_robot/core/orchestrator.py",
            "src/autonomous_investment_robot/main.py",
            "src/autonomous_investment_robot/__main__.py",
        ],
        "distributed": [
            "src/autonomous_investment_robot/services/distributed",
            "src/autonomous_investment_robot/services/storage",
            "tests/test_distributed_e2e.py",
            "tests/test_postgres_mirror.py",
        ],
        "mastermind": [
            "src/autonomous_investment_robot/services/mastermind/service.py",
            "src/autonomous_investment_robot/services/mlops/service.py",
        ],
        "infra": [
            "infra/docker-compose.yml",
            "scripts/validate_compose_runtime.sh",
            "scripts/smoke_test_distributed_cluster.sh",
        ],
    }

    out: dict[str, list[str]] = {}
    for group, items in patterns.items():
        out[group] = []
        for item in items:
            p = ROOT / item
            if p.exists():
                out[group].append(item)
    return out


def import_checks() -> list[ImportCheck]:
    modules = [
        "autonomous_investment_robot",
        "autonomous_investment_robot.core.orchestrator",
        "autonomous_investment_robot.services.mastermind.service",
        "autonomous_investment_robot.services.mlops.service",
        "autonomous_investment_robot.services.distributed.compute_worker",
    ]
    results: list[ImportCheck] = []

    for module in modules:
        cmd = [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                import importlib
                importlib.import_module("{module}")
                print("OK")
                """
            ),
        ]
        try:
            res = run_cmd(cmd, timeout=120)
            if res.returncode == 0:
                results.append(ImportCheck(module=module, ok=True))
            else:
                results.append(
                    ImportCheck(
                        module=module,
                        ok=False,
                        error=(res.stderr or res.stdout).strip()[:2000],
                    )
                )
        except Exception as exc:
            results.append(ImportCheck(module=module, ok=False, error=repr(exc)))

    return results


def clean_caches() -> dict[str, Any]:
    removed = []
    for pattern in ["__pycache__", ".pytest_cache"]:
        if pattern == "__pycache__":
            for p in ROOT.rglob(pattern):
                if p.is_dir():
                    subprocess.run(["rm", "-rf", str(p)], check=False)
                    removed.append(str(p.relative_to(ROOT)))
        else:
            p = ROOT / pattern
            if p.exists():
                subprocess.run(["rm", "-rf", str(p)], check=False)
                removed.append(pattern)

    return {"removed": removed}


def run_pytest(maxfail: int = 1) -> CommandResult:
    return run_cmd(
        [
            sys.executable,
            "-m",
            "pytest",
            "-x",
            f"--maxfail={maxfail}",
            "-q",
        ],
        timeout=1800,
    )


def extract_first_failure(pytest_output: str) -> dict[str, Any]:
    text = pytest_output or ""
    lines = text.splitlines()

    summary = next((ln for ln in reversed(lines) if "failed" in ln or "passed" in ln), "")
    test_line = next((ln for ln in lines if ln.startswith("FAILED ")), "")
    err_line = ""

    attr_re = re.compile(r"(AttributeError: .+)")
    import_re = re.compile(r"(ImportError: .+|ModuleNotFoundError: .+)")

    for ln in lines:
        if attr_re.search(ln):
            err_line = attr_re.search(ln).group(1)
            break
        if import_re.search(ln):
            err_line = import_re.search(ln).group(1)
            break

    location = ""
    for i, ln in enumerate(lines):
        if ln.startswith(">") and i + 1 < len(lines):
            location = lines[i + 1].strip()
            break

    return {
        "failed_test": test_line.replace("FAILED ", "", 1).strip(),
        "error": err_line,
        "location_hint": location,
        "summary": summary.strip(),
    }


def generate_repair_hints(import_results: list[ImportCheck], failure: dict[str, Any]) -> list[str]:
    hints: list[str] = []

    for item in import_results:
        if item.ok:
            continue
        err = item.error or ""
        if "cannot import name 'MastermindService'" in err:
            hints.append(
                "V src/autonomous_investment_robot/services/mastermind/service.py chýba trieda MastermindService. "
                "Treba doplniť kompatibilný wrapper s metódou advise(symbol, features, regime)."
            )
        elif "cannot import name 'MLOpsService'" in err:
            hints.append(
                "V src/autonomous_investment_robot/services/mlops/service.py chýba trieda MLOpsService. "
                "Treba doplniť kompatibilný wrapper a detector.psi(...)."
            )
        elif "ModuleNotFoundError: No module named 'openai'" in err:
            hints.append(
                "Chýba balík openai alebo treba odstrániť tvrdú závislosť a spraviť lazy import/fallback."
            )

    ferr = failure.get("error", "") or ""
    if "AttributeError: 'MLOpsService' object has no attribute 'detector'" in ferr:
        hints.append(
            "MLOpsService musí mať atribút detector s metódou psi(reference, current). "
            "Minimálne fallback implementácia má vrátiť float."
        )

    if not hints:
        hints.append("Žiadny známy compatibility gap sa nenašiel. Pozri pytest stdout/stderr.")

    return hints


def make_report(
    run_id: str,
    blueprint_info: dict[str, Any],
    key_paths: dict[str, list[str]],
    cache_cleanup: dict[str, Any],
    imports: list[ImportCheck],
    pytest_result: CommandResult,
    failure: dict[str, Any],
    hints: list[str],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "blueprint": blueprint_info,
        "key_paths": key_paths,
        "cleanup": cache_cleanup,
        "import_checks": [x.to_dict() for x in imports],
        "pytest": pytest_result.to_dict(),
        "first_failure": failure,
        "repair_hints": hints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repo-aware auto repair runner")
    parser.add_argument("--blueprint", default=str(DEFAULT_BLUEPRINT))
    parser.add_argument("--maxfail", type=int, default=1)
    parser.add_argument("--skip-clean", action="store_true")
    args = parser.parse_args()

    ensure_dir(RUNS_DIR)
    run_id = f"auto_repair_{utc_now()}"
    run_dir = RUNS_DIR / run_id
    ensure_dir(run_dir)

    blueprint_info = read_blueprint(Path(args.blueprint))
    key_paths = list_key_paths()

    cleanup_info = {"removed": []}
    if not args.skip_clean:
        cleanup_info = clean_caches()

    imports = import_checks()
    pytest_result = run_pytest(maxfail=args.maxfail)
    merged_pytest_output = "\n".join(
        part for part in [pytest_result.stdout, pytest_result.stderr] if part
    )
    failure = extract_first_failure(merged_pytest_output)
    hints = generate_repair_hints(imports, failure)

    report = make_report(
        run_id=run_id,
        blueprint_info=blueprint_info,
        key_paths=key_paths,
        cache_cleanup=cleanup_info,
        imports=imports,
        pytest_result=pytest_result,
        failure=failure,
        hints=hints,
    )

    write_json(run_dir / "report.json", report)
    write_json(run_dir / "import_checks.json", [x.to_dict() for x in imports])
    write_text(run_dir / "pytest.stdout.log", pytest_result.stdout)
    write_text(run_dir / "pytest.stderr.log", pytest_result.stderr)
    write_text(run_dir / "repair_hints.txt", "\n".join(f"- {h}" for h in hints))

    print(f"[OK] report: {run_dir / 'report.json'}")
    print(f"[OK] pytest stdout: {run_dir / 'pytest.stdout.log'}")
    print(f"[OK] pytest stderr: {run_dir / 'pytest.stderr.log'}")
    print("")
    print("=== FIRST FAILURE ===")
    print(json.dumps(failure, indent=2, ensure_ascii=False))
    print("")
    print("=== REPAIR HINTS ===")
    for h in hints:
        print(f"- {h}")

    return 0 if pytest_result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
