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
class ConstraintReason:
    code: str
    severity: str
    message: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "active": bool(self.active),
        }


@dataclass(frozen=True)
class CompiledCapitalConstraints:
    contract_id: str
    deterministic: bool
    bounded_compute: bool
    hard_clamp: bool
    allow_new_risk: bool
    max_total_exposure_quote: float
    max_new_trade_notional_quote: float
    max_single_order_notional_quote: float
    risk_multiplier: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[ConstraintReason, ...] = field(default_factory=tuple)
    limits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "deterministic": bool(self.deterministic),
            "bounded_compute": bool(self.bounded_compute),
            "hard_clamp": bool(self.hard_clamp),
            "allow_new_risk": bool(self.allow_new_risk),
            "max_total_exposure_quote": float(self.max_total_exposure_quote),
            "max_new_trade_notional_quote": float(self.max_new_trade_notional_quote),
            "max_single_order_notional_quote": float(self.max_single_order_notional_quote),
            "risk_multiplier": float(self.risk_multiplier),
            "reason_codes": [str(item) for item in self.reason_codes],
            "reasons": [row.to_dict() for row in self.reasons],
            "limits": dict(self.limits),
        }


class CapitalConstraintCompiler:
    """Phase 38 deterministic contract compiler for survival/risk/execution constraints."""

    def __init__(self, *, default_exposure_cap_ratio: float = 0.75) -> None:
        self.default_exposure_cap_ratio = _clamp(float(default_exposure_cap_ratio), 0.05, 1.0)

    def compile(
        self,
        *,
        world: Any,
        plan: Mapping[str, Any] | None,
        shield: Mapping[str, Any] | None,
        survival_doctrine: Mapping[str, Any] | None,
        netting_envelope: Mapping[str, Any] | None,
    ) -> CompiledCapitalConstraints:
        world_portfolio = getattr(world, "portfolio_state", None)
        world_risk = getattr(world, "risk_state", None)
        equity_quote = max(1.0, _safe_float(getattr(world_portfolio, "equity_quote", 0.0), 0.0))
        existing_exposure = max(0.0, _safe_float(getattr(world_portfolio, "exposure_quote", 0.0), 0.0))
        base_cap = equity_quote * self.default_exposure_cap_ratio
        plan_map = _safe_mapping(plan)
        shield_map = _safe_mapping(shield)
        survival = _safe_mapping(survival_doctrine)
        netting = _safe_mapping(netting_envelope)
        netting_cap = max(0.0, _safe_float(netting.get("risk_cap_quote", base_cap), base_cap))
        max_total = min(base_cap, netting_cap if netting_cap > 0.0 else base_cap)

        survival_veto = bool(survival.get("safety_veto", False))
        shield_hard_stop = bool(shield_map.get("hard_stop_forced", shield_map.get("kill_switch", False)))
        risk_hard_stop = bool(getattr(world_risk, "hard_stop", False))
        risk_observe_only = bool(getattr(world_risk, "observe_only", False))
        hard_clamp = bool(survival_veto or shield_hard_stop or risk_hard_stop)
        recommendation_mode = str(survival.get("recommendation_mode", "normal") or "normal")

        reason_codes: list[str] = []
        reasons: list[ConstraintReason] = []
        if hard_clamp:
            max_total = 0.0
            reason_codes.append("hard_clamp_active")
            reasons.append(
                ConstraintReason(
                    code="hard_clamp_active",
                    severity="critical",
                    message="hard safety veto or hard stop active",
                    active=True,
                )
            )
        if risk_observe_only:
            reason_codes.append("observe_only_mode")
            reasons.append(
                ConstraintReason(
                    code="observe_only_mode",
                    severity="high",
                    message="observe-only risk mode disables new-risk expansion",
                    active=True,
                )
            )
        if bool(netting.get("capped_exposure_quote", 0.0)) and (
            _safe_float(netting.get("capped_exposure_quote", 0.0), 0.0) + 1e-9
            < _safe_float(netting.get("gross_exposure_quote", 0.0), 0.0)
        ):
            reason_codes.append("portfolio_netting_cap_applied")
            reasons.append(
                ConstraintReason(
                    code="portfolio_netting_cap_applied",
                    severity="high",
                    message="portfolio netting exceeded risk cap and was clipped",
                    active=True,
                )
            )
        target_notional = max(0.0, _safe_float(plan_map.get("target_notional_quote", 0.0), 0.0))
        available_new = max(0.0, max_total - existing_exposure)
        max_new_trade = 0.0 if hard_clamp else min(target_notional, available_new if available_new > 0.0 else 0.0)
        if recommendation_mode in {"survival", "defensive"} and not hard_clamp:
            max_new_trade *= 0.5
            reason_codes.append(f"survival_mode:{recommendation_mode}")
            reasons.append(
                ConstraintReason(
                    code=f"survival_mode:{recommendation_mode}",
                    severity="medium",
                    message="survival doctrine contracts new trade notional",
                    active=True,
                )
            )
        allow_new_risk = bool((not hard_clamp) and (not risk_observe_only) and recommendation_mode not in {"survival"})
        if not allow_new_risk:
            reason_codes.append("new_risk_disallowed")
        max_single_order = min(max_new_trade, max_total * 0.40 if max_total > 0.0 else 0.0)
        risk_multiplier = 0.0 if hard_clamp else 0.35 if recommendation_mode in {"survival", "defensive"} else 1.0
        if not reason_codes:
            reason_codes.append("constraints_compiled")

        limits = {
            "equity_quote": equity_quote,
            "existing_exposure_quote": existing_exposure,
            "base_exposure_cap_quote": base_cap,
            "netting_cap_quote": netting_cap,
            "target_notional_quote": target_notional,
            "available_new_exposure_quote": available_new,
        }
        contract_id = _stable_hash(
            {
                "phase": 38,
                "hard_clamp": bool(hard_clamp),
                "allow_new_risk": bool(allow_new_risk),
                "max_total_exposure_quote": round(max_total, 6),
                "max_new_trade_notional_quote": round(max_new_trade, 6),
                "max_single_order_notional_quote": round(max_single_order, 6),
                "risk_multiplier": round(risk_multiplier, 6),
                "reason_codes": sorted(set(reason_codes)),
            }
        )[:24]
        return CompiledCapitalConstraints(
            contract_id=contract_id,
            deterministic=True,
            bounded_compute=True,
            hard_clamp=hard_clamp,
            allow_new_risk=allow_new_risk,
            max_total_exposure_quote=max_total,
            max_new_trade_notional_quote=max_new_trade,
            max_single_order_notional_quote=max_single_order,
            risk_multiplier=risk_multiplier,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            reasons=tuple(reasons),
            limits=limits,
        )
