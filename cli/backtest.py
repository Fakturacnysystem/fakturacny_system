from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.backtest.portfolio_engine import (  # noqa: E402
    export_portfolio_report,
    load_prices,
    run_portfolio_backtest,
)
from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--input", default="")
    p.add_argument("--output-dir", default="")
    args = p.parse_args()

    cfg = _load_yaml_like(args.config)
    if not isinstance(cfg, dict):
        cfg = {}
    bt_cfg = cfg.get("backtest", {}) if isinstance(cfg.get("backtest", {}), dict) else {}

    input_path = args.input.strip() or str(bt_cfg.get("input", "") or "")
    if not input_path:
        fixtures = cfg.get("fixtures", {}) if isinstance(cfg.get("fixtures", {}), dict) else {}
        input_path = str(fixtures.get("ohlcv_csv", "") or "")
    if not input_path:
        print(json.dumps({"status": "error", "reason": "missing_input"}, indent=2))
        return 1

    out_dir = args.output_dir.strip() or str(bt_cfg.get("output_dir", "") or "")
    if not out_dir:
        storage = cfg.get("storage", {}) if isinstance(cfg.get("storage", {}), dict) else {}
        out_dir = str(storage.get("run_dir", "runs/kraken_spot_live") or "runs/kraken_spot_live") + "/backtests"

    fee_bps = float(bt_cfg.get("fee_bps", 2.0) or 2.0)
    slippage_bps = float(bt_cfg.get("slippage_bps", 3.0) or 3.0)
    funding_bps = float(bt_cfg.get("funding_bps", 0.0) or 0.0)
    profit_target_net = float(bt_cfg.get("profit_target_net", 0.02) or 0.02)

    prices = load_prices(input_path)
    report = run_portfolio_backtest(
        prices,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        funding_bps=funding_bps,
        profit_target_net=max(0.02, profit_target_net),
    )
    files = export_portfolio_report(report, output_dir=out_dir)
    print(
        json.dumps(
            {
                "status": "ok",
                "input": input_path,
                "summary": report.summary,
                "files": files,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
