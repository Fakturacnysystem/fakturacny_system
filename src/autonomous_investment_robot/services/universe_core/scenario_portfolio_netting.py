from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NettedScenarioExposure:
    symbol: str
    expected_pnl_quote: float
    worst_case_pnl_quote: float
    best_case_pnl_quote: float
    stress_score: float
    existing_exposure_quote: float
    planned_notional_quote: float
    gross_exposure_quote: float
    capped_exposure_quote: float
    capped: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expected_pnl_quote": float(self.expected_pnl_quote),
            "worst_case_pnl_quote": float(self.worst_case_pnl_quote),
            "best_case_pnl_quote": float(self.best_case_pnl_quote),
            "stress_score": float(self.stress_score),
            "existing_exposure_quote": float(self.existing_exposure_quote),
            "planned_notional_quote": float(self.planned_notional_quote),
            "gross_exposure_quote": float(self.gross_exposure_quote),
            "capped_exposure_quote": float(self.capped_exposure_quote),
            "capped": bool(self.capped),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class PortfolioStressEnvelope:
    envelope_id: str
    deterministic: bool
    bounded_compute: bool
    fail_closed: bool
    risk_cap_quote: float
    gross_exposure_quote: float
    capped_exposure_quote: float
    expected_portfolio_pnl_quote: float
    worst_case_portfolio_pnl_quote: float
    best_case_portfolio_pnl_quote: float
    stress_index: float
    escalation_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    netted_exposures: tuple[NettedScenarioExposure, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "deterministic": bool(self.deterministic),
            "bounded_compute": bool(self.bounded_compute),
            "fail_closed": bool(self.fail_closed),
            "risk_cap_quote": float(self.risk_cap_quote),
            "gross_exposure_quote": float(self.gross_exposure_quote),
            "capped_exposure_quote": float(self.capped_exposure_quote),
            "expected_portfolio_pnl_quote": float(self.expected_portfolio_pnl_quote),
            "worst_case_portfolio_pnl_quote": float(self.worst_case_portfolio_pnl_quote),
            "best_case_portfolio_pnl_quote": float(self.best_case_portfolio_pnl_quote),
            "stress_index": float(self.stress_index),
            "escalation_reason_codes": [str(item) for item in self.escalation_reason_codes],
            "netted_exposures": [row.to_dict() for row in self.netted_exposures],
        }


class ScenarioPortfolioNettingEngine:
    """Phase 37 deterministic scenario netting under bounded portfolio stress caps."""

    def __init__(
        self,
        *,
        max_symbols: int = 16,
        exposure_cap_ratio: float = 0.75,
    ) -> None:
        self.max_symbols = max(1, int(max_symbols))
        self.exposure_cap_ratio = _clamp(float(exposure_cap_ratio), 0.05, 1.0)

    def net(
        self,
        *,
        world: Any,
        primary_symbol: str,
        primary_plan_notional_quote: float,
        primary_simulation: Mapping[str, Any] | None,
    ) -> PortfolioStressEnvelope:
        symbol = str(primary_symbol or "").strip().upper() or "UNKNOWN"
        simulation = _safe_mapping(primary_simulation)
        pnl = _safe_mapping(simulation.get("pnl_envelope", {}))
        black_swan = _safe_mapping(simulation.get("black_swan", {}))
        confidence = _safe_mapping(simulation.get("confidence", {}))
        equity_quote = max(1.0, _safe_float(getattr(getattr(world, "portfolio_state", None), "equity_quote", 0.0), 0.0))
        existing_exposure = max(0.0, _safe_float(getattr(getattr(world, "portfolio_state", None), "exposure_quote", 0.0), 0.0))
        planned_notional = max(0.0, _safe_float(primary_plan_notional_quote, 0.0))
        risk_state = getattr(world, "risk_state", None)
        hard_stop = bool(getattr(risk_state, "hard_stop", False))
        observe_only = bool(getattr(risk_state, "observe_only", False))
        risk_cap_quote = 0.0 if (hard_stop or observe_only) else (equity_quote * self.exposure_cap_ratio)
        gross_exposure = existing_exposure + planned_notional
        capped_exposure = _clamp(gross_exposure, 0.0, risk_cap_quote if risk_cap_quote > 0.0 else 0.0)
        cap_applied = capped_exposure + 1e-9 < gross_exposure
        expected_pnl = _safe_float(pnl.get("expected", 0.0), 0.0)
        worst_pnl = _safe_float(pnl.get("worst_case", pnl.get("downside_95", 0.0)), 0.0)
        best_pnl = _safe_float(pnl.get("best_case", pnl.get("upside_95", 0.0)), 0.0)
        stress_seed = max(
            0.0,
            _safe_float(black_swan.get("severity", 0.0), 0.0),
            abs(min(0.0, worst_pnl)) / max(1.0, equity_quote),
        )
        confidence_overall = _clamp(_safe_float(confidence.get("overall", 0.0), 0.0), 0.0, 1.0)
        stress_index = _clamp(stress_seed * 0.75 + (1.0 - confidence_overall) * 0.25, 0.0, 1.0)
        fail_closed = not bool(simulation)
        if fail_closed:
            cap_applied = True
            capped_exposure = 0.0
            gross_exposure = 0.0
            expected_pnl = 0.0
            worst_pnl = 0.0
            best_pnl = 0.0
            stress_index = 1.0
        net_reason_codes: list[str] = []
        escalation_reason_codes: list[str] = []
        if fail_closed:
            net_reason_codes.append("portfolio_netting_input_unavailable")
            escalation_reason_codes.append("portfolio_netting_fail_closed")
        if hard_stop:
            net_reason_codes.append("risk_hard_stop")
            escalation_reason_codes.append("portfolio_netting_hard_stop_cap")
        if observe_only:
            net_reason_codes.append("risk_observe_only")
            escalation_reason_codes.append("portfolio_netting_observe_only_cap")
        if cap_applied:
            net_reason_codes.append("risk_cap_applied")
            escalation_reason_codes.append("portfolio_netting_cap_applied")
        if stress_index >= 0.70:
            escalation_reason_codes.append("portfolio_stress_high")
        if not escalation_reason_codes:
            escalation_reason_codes.append("portfolio_netting_within_caps")
        exposure = NettedScenarioExposure(
            symbol=symbol,
            expected_pnl_quote=expected_pnl,
            worst_case_pnl_quote=worst_pnl,
            best_case_pnl_quote=best_pnl,
            stress_score=stress_index,
            existing_exposure_quote=existing_exposure,
            planned_notional_quote=planned_notional,
            gross_exposure_quote=gross_exposure,
            capped_exposure_quote=capped_exposure,
            capped=cap_applied,
            reason_codes=tuple(net_reason_codes),
        )
        envelope_id = _stable_hash(
            {
                "phase": 37,
                "symbol": symbol,
                "equity_quote": round(equity_quote, 6),
                "risk_cap_quote": round(risk_cap_quote, 6),
                "gross_exposure_quote": round(gross_exposure, 6),
                "capped_exposure_quote": round(capped_exposure, 6),
                "expected_pnl_quote": round(expected_pnl, 6),
                "worst_case_pnl_quote": round(worst_pnl, 6),
                "stress_index": round(stress_index, 6),
                "fail_closed": bool(fail_closed),
                "reason_codes": sorted(escalation_reason_codes),
            }
        )[:24]
        return PortfolioStressEnvelope(
            envelope_id=envelope_id,
            deterministic=True,
            bounded_compute=True,
            fail_closed=fail_closed,
            risk_cap_quote=risk_cap_quote,
            gross_exposure_quote=gross_exposure,
            capped_exposure_quote=capped_exposure,
            expected_portfolio_pnl_quote=expected_pnl,
            worst_case_portfolio_pnl_quote=worst_pnl,
            best_case_portfolio_pnl_quote=best_pnl,
            stress_index=stress_index,
            escalation_reason_codes=tuple(dict.fromkeys(escalation_reason_codes)),
            netted_exposures=(exposure,),
        )
