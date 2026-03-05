from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class PortfolioBacktestReport:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    per_symbol: dict[str, dict[str, Any]]


def _normalize_prices(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    cols = {str(c).strip().lower(): c for c in frame.columns}
    if "symbol" not in cols:
        frame["symbol"] = "UNKNOWN"
        cols["symbol"] = "symbol"
    if "timestamp" not in cols:
        if "ts" in cols:
            frame["timestamp"] = frame[cols["ts"]]
        else:
            frame["timestamp"] = range(len(frame))
        cols["timestamp"] = "timestamp"
    if "price" not in cols:
        for cand in ("close", "mid", "mark", "last"):
            if cand in cols:
                frame["price"] = frame[cols[cand]]
                break
        if "price" not in frame.columns:
            raise ValueError("missing_price_column")
    frame = frame[[cols.get("symbol", "symbol"), cols.get("timestamp", "timestamp"), "price"]].copy()
    frame.columns = ["symbol", "timestamp", "price"]
    frame["symbol"] = frame["symbol"].astype(str)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["price"])
    frame = frame.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return frame


def load_prices(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if p.suffix.lower() == ".parquet":
        try:
            raw = pd.read_parquet(p)
        except Exception as exc:
            raise RuntimeError(f"parquet_load_failed:{exc}") from exc
    else:
        raw = pd.read_csv(p)
    return _normalize_prices(raw)


def run_portfolio_backtest(
    prices: pd.DataFrame,
    *,
    fee_bps: float,
    slippage_bps: float,
    funding_bps: float = 0.0,
    profit_target_net: float = 0.02,
) -> PortfolioBacktestReport:
    frame = _normalize_prices(prices)
    total_cost = (float(fee_bps) + float(slippage_bps) + float(funding_bps)) / 10000.0
    out_rows: list[dict[str, Any]] = []
    per_symbol: dict[str, dict[str, Any]] = {}

    for symbol, grp in frame.groupby("symbol"):
        equity = 1.0
        prev = None
        trades = 0
        realized_positive = 0
        gross_ret_sum = 0.0
        net_ret_sum = 0.0
        for _, row in grp.iterrows():
            px = float(row["price"])
            ret = 0.0 if prev is None else ((px / max(prev, 1e-12)) - 1.0)
            prev = px
            strat_ret = ret - total_cost
            equity *= (1.0 + strat_ret)
            trades += 1
            gross_ret_sum += ret
            net_ret_sum += strat_ret
            if strat_ret >= profit_target_net:
                realized_positive += 1
            out_rows.append(
                {
                    "symbol": symbol,
                    "timestamp": row["timestamp"],
                    "price": px,
                    "ret": ret,
                    "strategy_ret": strat_ret,
                    "equity": equity,
                }
            )

        if trades <= 0:
            continue
        per_symbol[str(symbol)] = {
            "trades": int(trades),
            "gross_ret_sum": float(gross_ret_sum),
            "net_ret_sum": float(net_ret_sum),
            "equity_end": float(equity),
            "profit_gate_hit_ratio": float(realized_positive / max(1, trades)),
            "profit_target_net": float(profit_target_net),
            "cost_bps_assumed": float((total_cost * 10000.0)),
        }

    avg_equity = 0.0
    if per_symbol:
        avg_equity = sum(v["equity_end"] for v in per_symbol.values()) / len(per_symbol)
    summary = {
        "symbols": int(len(per_symbol)),
        "rows": int(len(out_rows)),
        "avg_equity_end": float(avg_equity),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "funding_bps": float(funding_bps),
        "profit_target_net": float(profit_target_net),
    }
    return PortfolioBacktestReport(rows=out_rows, summary=summary, per_symbol=per_symbol)


def export_portfolio_report(
    report: PortfolioBacktestReport,
    *,
    output_dir: str,
    report_name: str = "portfolio_backtest",
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{report_name}.csv"
    md_path = out / f"{report_name}.md"

    pd.DataFrame(report.rows).to_csv(csv_path, index=False)

    lines: list[str] = [
        "# Portfolio Backtest Report",
        "",
        f"- Symbols: {report.summary.get('symbols', 0)}",
        f"- Rows: {report.summary.get('rows', 0)}",
        f"- Avg equity end: {report.summary.get('avg_equity_end', 0.0):.6f}",
        f"- Fee bps: {report.summary.get('fee_bps', 0.0):.2f}",
        f"- Slippage bps: {report.summary.get('slippage_bps', 0.0):.2f}",
        f"- Funding bps: {report.summary.get('funding_bps', 0.0):.2f}",
        f"- Profit target net: {report.summary.get('profit_target_net', 0.0):.4f}",
        "",
        "## Per Symbol",
        "",
        "| Symbol | Trades | Equity End | Profit-Gate Hit Ratio |",
        "|---|---:|---:|---:|",
    ]
    for symbol, data in sorted(report.per_symbol.items()):
        lines.append(
            f"| {symbol} | {int(data.get('trades', 0))} | {float(data.get('equity_end', 0.0)):.6f} | {float(data.get('profit_gate_hit_ratio', 0.0)):.4f} |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": str(csv_path), "md": str(md_path)}
