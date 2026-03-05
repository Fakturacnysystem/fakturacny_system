#!/usr/bin/env python3
"""
PROFIT ALL-IN-ONE (Kraken Spot)

This script does 3 things:
1) Builds a "profit universe" (top liquid, low-spread Kraken spot pairs) and writes a new config.
2) Patches policy to skip tiny intents that would become `min_order_block` spam.
3) Ensures Kraken rate-limit cooldown handling is present (exchange correctness guard).

Usage (from repo root):
  pip install pyyaml requests
  python3 scripts/profit_all_in_one.py \
    --in-config config.kraken_spot.live.yaml \
    --out-config config.kraken_spot.live_profit.yaml \
    --quote EUR --top 5 --majors-only \
    --min-order-notional 15 \
    --rate-limit-cooldown 3 \
    --apply-patches
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

KRAKEN_API = "https://api.kraken.com"

# Kraken spot uses XBT instead of BTC.
DEFAULT_MAJORS = {"XBT", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK"}
EXCLUDE_BASE = {"USDT", "USDC", "DAI", "EUR", "USD"}
EXCLUDE_QUOTE = {"USDT", "USDC", "DAI"}


def _require_deps() -> None:
    missing: list[str] = []
    if requests is None:
        missing.append("requests")
    if yaml is None:
        missing.append("pyyaml")
    if missing:
        raise SystemExit(f"Missing dependency: {', '.join(missing)}. Install: pip install {' '.join(missing)}")


def kraken_get(path: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    _require_deps()
    assert requests is not None
    r = requests.get(f"{KRAKEN_API}{path}", params=params or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")
    result = data.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected Kraken result payload for {path}")
    return result


def split_pair(meta: dict[str, Any]) -> tuple[str, str] | None:
    wsname = str(meta.get("wsname", "") or "")
    if "/" in wsname:
        base, quote = wsname.split("/", 1)
        return base.upper(), quote.upper()

    base = str(meta.get("base", "") or "").upper()
    quote = str(meta.get("quote", "") or "").upper()
    if base and quote:
        # Kraken internals often include X/Z prefixes (e.g. XXBT, ZEUR).
        if len(base) >= 4 and base[0] in {"X", "Z"}:
            base = base[1:]
        if len(quote) >= 4 and quote[0] in {"X", "Z"}:
            quote = quote[1:]
        return base, quote

    alt = str(meta.get("altname", "") or "")
    if "/" in alt:
        base, quote = alt.split("/", 1)
        return base.upper(), quote.upper()
    return None


def pick_profit_universe(*, quote: str, top: int, majors_only: bool, noslash: bool = True) -> list[str]:
    quote = quote.upper()
    if quote not in {"EUR", "USD", "AUTO"}:
        raise RuntimeError("quote must be EUR, USD, or AUTO")

    if quote == "AUTO":
        eur = pick_profit_universe(quote="EUR", top=top, majors_only=majors_only, noslash=noslash)
        if len(eur) >= max(1, top):
            return eur
        usd = pick_profit_universe(quote="USD", top=top, majors_only=majors_only, noslash=noslash)
        return eur if len(eur) >= len(usd) else usd

    pairs = kraken_get("/0/public/AssetPairs")
    candidates: list[tuple[str, str]] = []  # (pair_key, symbol_out)
    for key, meta in pairs.items():
        if not isinstance(meta, dict):
            continue
        parsed = split_pair(meta)
        if parsed is None:
            continue
        base, q = parsed
        if q != quote:
            continue
        if base in EXCLUDE_BASE or q in EXCLUDE_QUOTE:
            continue
        if majors_only and base not in DEFAULT_MAJORS:
            continue
        if str(meta.get("status", "online")) != "online":
            continue
        out = f"{base}{q}" if noslash else f"{base}/{q}"
        candidates.append((key, out))

    if not candidates:
        raise RuntimeError("No candidates found. Try --no-majors-only or different --quote.")

    tick: dict[str, Any] = {}
    batch = 40
    for i in range(0, len(candidates), batch):
        chunk = candidates[i : i + batch]
        pair_param = ",".join(k for k, _ in chunk)
        res = kraken_get("/0/public/Ticker", params={"pair": pair_param})
        tick.update(res)

    scored: list[tuple[float, str]] = []  # (score, symbol_out)
    for key, symbol_out in candidates:
        t = tick.get(key)
        if not isinstance(t, dict):
            continue
        try:
            bid = float(t["b"][0])
            ask = float(t["a"][0])
            last = float(t["c"][0])
            vol_base_24h = float(t["v"][1])
        except Exception:
            continue
        if bid <= 0 or ask <= 0 or last <= 0:
            continue

        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0
        vol_quote_24h = vol_base_24h * last
        score = math.log1p(vol_quote_24h) / (1.0 + (spread_bps / 20.0))
        scored.append((score, symbol_out))

    scored.sort(reverse=True, key=lambda x: x[0])
    out = [sym for _, sym in scored[: max(1, top)]]
    if not out:
        raise RuntimeError("No universe selected. Check Kraken ticker data.")
    return out


def set_universe(cfg: dict[str, Any], universe: list[str]) -> None:
    if isinstance(cfg.get("universe"), list):
        cfg["universe"] = universe
        return
    policy = cfg.get("policy")
    if isinstance(policy, dict) and isinstance(policy.get("universe"), list):
        policy["universe"] = universe
        return
    cfg["universe"] = universe


def backup_file(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return bak


def ensure_import(text: str, module: str) -> str:
    if re.search(rf"(?m)^\s*import\s+{re.escape(module)}\s*$", text):
        return text
    if re.search(rf"(?m)^\s*from\s+{re.escape(module)}\s+import\s+", text):
        return text
    lines = text.splitlines()
    insert_at = 0
    for i, ln in enumerate(lines[:40]):
        if ln.startswith("from __future__ import"):
            insert_at = i + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, f"import {module}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def patch_policy_min_notional(repo_root: Path, min_notional: float) -> bool:
    path = repo_root / "src/autonomous_investment_robot/services/policy/service.py"
    if not path.exists():
        print(f"[skip] policy file missing: {path}")
        return False

    txt = path.read_text(encoding="utf-8")
    if "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE" in txt and "min_order_floor_skip" in txt:
        print("[ok] policy min-notional floor already present")
        return True

    txt = ensure_import(txt, "os")
    anchor = "        target = min(abs(combined), self.settings.base_risk_budget)\n        return OrderIntent("
    if anchor not in txt:
        print("[fail] anchor not found in policy/service.py (target + return OrderIntent)")
        return False

    snippet = (
        "        target = min(abs(combined), self.settings.base_risk_budget)\n"
        "        min_order_floor = max(0.0, float(os.getenv(\"AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE\", \"0\") or \"0\"))\n"
        "        if min_order_floor > 0.0 and target < min_order_floor:\n"
        "            self.last_veto_reasons.append(\"min_order_floor_skip\")\n"
        "            self.last_veto_counts[\"min_order_floor_skip\"] = self.last_veto_counts.get(\"min_order_floor_skip\", 0) + 1\n"
        "            self.last_no_intent_debug = {\n"
        "                \"reason\": \"min_order_floor_skip\",\n"
        "                \"min_order_floor\": min_order_floor,\n"
        "                \"target_notional\": target,\n"
        "                \"side\": side,\n"
        "            }\n"
        "            return None\n"
        "        return OrderIntent("
    )

    patched = txt.replace(anchor, snippet, 1)
    backup_file(path)
    path.write_text(patched, encoding="utf-8")
    print(f"[patched] policy min-notional floor via AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE (default {min_notional})")
    return True


def patch_kraken_rate_limit_cooldown(repo_root: Path, cooldown_s: int) -> bool:
    path = repo_root / "src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py"
    if not path.exists():
        print(f"[skip] kraken live file missing: {path}")
        return False

    txt = path.read_text(encoding="utf-8")
    has_cooldown = (
        "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S" in txt
        and "rate_limit_cooldown" in txt
        and "_activate_rate_limit_cooldown" in txt
    )
    if has_cooldown:
        print("[ok] Kraken rate-limit cooldown already present")
        return True

    print(
        "[warn] Kraken cooldown hooks not detected in live_kraken_spot_service.py; "
        "skipping auto-patch (manual patch recommended)."
    )
    return False


def patch_run_script_env(repo_root: Path, min_notional: float, cooldown_s: int) -> bool:
    path = repo_root / "scripts/run_kraken_spot_live.sh"
    if not path.exists():
        print(f"[skip] run script missing: {path}")
        return False

    txt = path.read_text(encoding="utf-8")
    backup_file(path)

    # Deduplicate AUTONOMOUS_MIN_NET_EDGE_BPS exports; keep last.
    lines = txt.splitlines()
    min_edge_idx = [i for i, ln in enumerate(lines) if ln.strip().startswith("export AUTONOMOUS_MIN_NET_EDGE_BPS=")]
    if len(min_edge_idx) > 1:
        keep = min_edge_idx[-1]
        lines = [ln for i, ln in enumerate(lines) if i == keep or not ln.strip().startswith("export AUTONOMOUS_MIN_NET_EDGE_BPS=")]
        txt = "\n".join(lines) + "\n"
        print("[patched] deduplicated AUTONOMOUS_MIN_NET_EDGE_BPS exports")

    def ensure_export(name: str, default_val: str) -> None:
        nonlocal txt
        pattern = rf"(?m)^\s*export\s+{re.escape(name)}="
        if re.search(pattern, txt):
            return
        export_line = f'export {name}="${{{name}:-{default_val}}}"\n'
        if "export PYTHONUNBUFFERED=1" in txt:
            txt = txt.replace("export PYTHONUNBUFFERED=1\n", f"{export_line}export PYTHONUNBUFFERED=1\n")
        else:
            txt = txt.rstrip() + "\n" + export_line

    ensure_export("AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", f"{min_notional:g}")
    ensure_export("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", str(int(cooldown_s)))

    path.write_text(txt, encoding="utf-8")
    print("[patched] run script exports for min-order-notional and rate-limit cooldown")
    return True


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-config", required=True, help="Input config YAML")
    ap.add_argument("--out-config", required=True, help="Output config YAML (profit universe)")
    ap.add_argument("--quote", choices=["EUR", "USD", "AUTO"], default="EUR")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument(
        "--majors-only",
        dest="majors_only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use majors-only filtering (default true). Use --no-majors-only to broaden.",
    )
    ap.add_argument("--min-order-notional", type=float, default=15.0)
    ap.add_argument("--rate-limit-cooldown", type=int, default=3)
    ap.add_argument("--apply-patches", action="store_true", help="Patch repo files (creates .bak backups)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    _require_deps()
    assert yaml is not None

    repo_root = Path(__file__).resolve().parents[1]
    in_cfg = Path(args.in_config)
    out_cfg = Path(args.out_config)

    cfg = yaml.safe_load(in_cfg.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise SystemExit("Config root must be a dict")
    if args.top <= 0:
        raise SystemExit("--top must be > 0")
    if args.min_order_notional < 0:
        raise SystemExit("--min-order-notional must be >= 0")
    if args.rate_limit_cooldown < 0:
        raise SystemExit("--rate-limit-cooldown must be >= 0")

    universe = pick_profit_universe(
        quote=str(args.quote),
        top=int(args.top),
        majors_only=bool(args.majors_only),
        noslash=True,
    )
    set_universe(cfg, universe)
    out_cfg.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"[ok] wrote {out_cfg}")
    print("[ok] profit universe:", universe)

    if args.apply_patches:
        ok1 = patch_policy_min_notional(repo_root, float(args.min_order_notional))
        ok2 = patch_kraken_rate_limit_cooldown(repo_root, int(args.rate_limit_cooldown))
        ok3 = patch_run_script_env(repo_root, float(args.min_order_notional), int(args.rate_limit_cooldown))
        if not (ok1 and ok2 and ok3):
            print("[warn] some patches may have failed; check git diff and .bak backups")
        else:
            print("[ok] patches applied")

    print("\nNEXT:")
    print("  1) Rotate Kraken API keys (withdrawals OFF)")
    print("  2) pytest -q")
    print(f"  3) AUTONOMOUS_GUARDS_MODE=fatal_only python3 -m autonomous_investment_robot live --config {out_cfg.name}")
    print(
        "  4) Ensure env: "
        f"AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE={float(args.min_order_notional):g}, "
        f"AUTONOMOUS_RATE_LIMIT_COOLDOWN_S={int(args.rate_limit_cooldown)}"
    )


if __name__ == "__main__":
    main()
