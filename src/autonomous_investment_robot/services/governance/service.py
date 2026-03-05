from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


@dataclass
class GovernanceDecision:
    allowed: bool
    reason: str
    details: dict[str, Any]
    fatal: bool = False


class GovernanceService:
    def __init__(self, run_dir: str, jurisdiction: str = "SK") -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.jurisdiction = jurisdiction
        self.audit_path = self.run_dir / "governance_audit.jsonl"
        self.compliance_path = self.run_dir / "compliance_report.json"
        self.tax_path = self.run_dir / "tax_report.json"

    def enforce_policy_constraints(
        self,
        *,
        symbol: str,
        target_notional: float,
        max_notional: float,
        leverage: int,
        max_leverage: int,
        drawdown_pct: float,
        max_drawdown_pct: float,
        allowed_symbols: set[str] | None = None,
    ) -> GovernanceDecision:
        if not symbol or not isinstance(symbol, str):
            return GovernanceDecision(False, "symbol_mapping_invalid", {"symbol": symbol}, fatal=True)
        if not math.isfinite(float(target_notional)) or float(target_notional) <= 0.0:
            return GovernanceDecision(
                False,
                "exchange_constraint_invalid",
                {"target_notional": target_notional},
                fatal=True,
            )
        if allowed_symbols is not None and symbol not in allowed_symbols:
            return GovernanceDecision(False, "symbol_not_in_mandate", {"symbol": symbol})
        if target_notional > max(0.0, float(max_notional)):
            return GovernanceDecision(False, "mandate_notional_limit", {"target_notional": target_notional, "max_notional": max_notional})
        if int(leverage) > int(max_leverage):
            return GovernanceDecision(False, "mandate_leverage_limit", {"leverage": leverage, "max_leverage": max_leverage})
        if abs(min(0.0, float(drawdown_pct))) > float(max_drawdown_pct):
            return GovernanceDecision(False, "mandate_drawdown_limit", {"drawdown_pct": drawdown_pct, "max_drawdown_pct": max_drawdown_pct})
        return GovernanceDecision(True, "ok", {})

    def audit_trade(self, payload: dict[str, Any]) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "jurisdiction": self.jurisdiction,
            **payload,
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def write_compliance_report(self, *, provider: str, provider_permissions: dict[str, Any], rules: dict[str, Any]) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "jurisdiction": self.jurisdiction,
            "provider": provider,
            "provider_permissions": provider_permissions,
            "rules": rules,
        }
        self.compliance_path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
        return str(self.compliance_path)

    def write_tax_report(self, trades: list[dict[str, Any]]) -> str:
        by_symbol: dict[str, dict[str, float]] = {}
        for t in trades:
            sym = str(t.get("symbol", "") or "")
            if not sym:
                continue
            row = by_symbol.setdefault(sym, {"realized_pnl_quote": 0.0, "fees_quote": 0.0, "turnover_quote": 0.0, "trades": 0.0})
            row["realized_pnl_quote"] += float(t.get("realized_pnl_quote", 0.0) or 0.0)
            row["fees_quote"] += float(t.get("fees_quote", 0.0) or 0.0)
            row["turnover_quote"] += float(t.get("notional", 0.0) or 0.0)
            row["trades"] += 1.0
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "jurisdiction": self.jurisdiction,
            "summary": by_symbol,
        }
        self.tax_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        return str(self.tax_path)

    def champion_challenger_gate(
        self,
        *,
        champion_score: float,
        challenger_score: float,
        promotion_margin: float,
        oos_gate_passed: bool,
    ) -> GovernanceDecision:
        if not oos_gate_passed:
            return GovernanceDecision(False, "oos_gate_failed", {"oos_gate_passed": oos_gate_passed})
        if challenger_score < champion_score + promotion_margin:
            return GovernanceDecision(
                False,
                "promotion_margin_not_met",
                {
                    "champion_score": champion_score,
                    "challenger_score": challenger_score,
                    "promotion_margin": promotion_margin,
                },
            )
        return GovernanceDecision(True, "promote_challenger", {"champion_score": champion_score, "challenger_score": challenger_score})
