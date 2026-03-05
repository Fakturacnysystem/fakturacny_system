from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    args = p.parse_args()

    pth = Path(args.file)
    if not pth.exists():
        print(json.dumps({"status": "error", "reason": "file_not_found", "file": str(pth)}, indent=2))
        return 1

    df = pd.read_csv(pth)
    rows = int(len(df))
    symbols = int(df["symbol"].nunique()) if "symbol" in df.columns else 0
    out = {
        "status": "ok",
        "file": str(pth),
        "rows": rows,
        "symbols": symbols,
        "columns": list(df.columns),
    }
    if "side" in df.columns:
        out["side_counts"] = {str(k): int(v) for k, v in df["side"].value_counts().to_dict().items()}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
