from __future__ import annotations

from autonomous_investment_robot.core.contracts import ProviderCapabilityMatrix, VenueConstraints


_VENUE_DEFAULTS: dict[str, dict[str, object]] = {
    "binance_um_perps": {
        "min_order_size": 0.001,
        "min_notional": 5.0,
        "quantity_step": 0.001,
        "price_tick": 0.1,
        "maker_assumption": "post_only_not_guaranteed",
        "taker_assumption": "marketable_limit_or_market",
        "reduce_only_supported": True,
        "post_only_supported": False,
        "replace_supported": False,
        "expire_supported": True,
        "confidence": "static_default",
    },
    "kraken_derivatives": {
        "min_order_size": 1.0,
        "min_notional": 10.0,
        "quantity_step": 1.0,
        "price_tick": 0.5,
        "maker_assumption": "post_only_supported",
        "taker_assumption": "marketable_limit_or_market",
        "reduce_only_supported": True,
        "post_only_supported": True,
        "replace_supported": False,
        "expire_supported": True,
        "confidence": "static_default",
    },
    "kraken_spot": {
        "min_order_size": 0.0001,
        "min_notional": 10.0,
        "quantity_step": 0.00000001,
        "price_tick": 0.1,
        "maker_assumption": "post_only_supported",
        "taker_assumption": "marketable_limit_or_market",
        "reduce_only_supported": False,
        "post_only_supported": True,
        "replace_supported": False,
        "expire_supported": True,
        "confidence": "static_default",
    },
}


class VenueConstraintsNormalizer:
    def for_provider(self, provider_id: str, symbol: str) -> VenueConstraints:
        if provider_id not in _VENUE_DEFAULTS:
            raise ValueError(f"unsupported_provider:{provider_id}")
        raw = dict(_VENUE_DEFAULTS[provider_id])
        return VenueConstraints(
            provider_id=provider_id,
            symbol=symbol,
            min_order_size=float(raw["min_order_size"]),
            min_notional=float(raw["min_notional"]),
            quantity_step=float(raw["quantity_step"]),
            price_tick=float(raw["price_tick"]),
            maker_assumption=str(raw["maker_assumption"]),
            taker_assumption=str(raw["taker_assumption"]),
            reduce_only_supported=bool(raw["reduce_only_supported"]),
            post_only_supported=bool(raw["post_only_supported"]),
            replace_supported=bool(raw["replace_supported"]),
            expire_supported=bool(raw["expire_supported"]),
            confidence=str(raw["confidence"]),
            metadata={"source": "static_constraints_defaults"},
        )

    def normalize_target_notional(self, *, target_notional: float, constraints: VenueConstraints, reduce_only: bool = False) -> tuple[float, dict[str, object]]:
        notional = max(0.0, float(target_notional))
        reasons: list[str] = []
        if notional <= 0.0:
            return 0.0, {"constraints_blocked": True, "reasons": ["non_positive_notional"], "constraints": constraints.metadata}
        if notional < constraints.min_notional and not reduce_only:
            return 0.0, {
                "constraints_blocked": True,
                "reasons": ["below_min_notional"],
                "min_notional": constraints.min_notional,
                "confidence": constraints.confidence,
            }
        rounded = notional
        if not reduce_only and constraints.min_notional > 0.0:
            rounded = round(notional / constraints.min_notional) * constraints.min_notional
            rounded = max(constraints.min_notional, rounded)
            if abs(rounded - notional) > 1e-9:
                reasons.append("rounded_to_venue_min_notional_grid")
        return float(rounded), {
            "constraints_blocked": False,
            "reasons": reasons,
            "min_notional": constraints.min_notional,
            "quantity_step": constraints.quantity_step,
            "price_tick": constraints.price_tick,
            "confidence": constraints.confidence,
        }


def provider_capability_matrix(provider_id: str) -> ProviderCapabilityMatrix:
    if provider_id not in _VENUE_DEFAULTS:
        raise ValueError(f"unsupported_provider:{provider_id}")
    if provider_id == "kraken_derivatives":
        return ProviderCapabilityMatrix(
            provider_id=provider_id,
            unrealized_pnl_truth_support="partial_when_field_absent",
            realized_pnl_truth_support="exchange_history_authoritative_when_available",
            lifecycle_completeness="strong_without_replace",
            replace_supported=False,
            expire_supported=True,
            fee_truth_confidence="exchange_history_authoritative_when_available",
            user_stream_confidence="rest_history_only",
            metadata={"proof": "tracked_single_process_scope"},
        )
    if provider_id == "kraken_spot":
        return ProviderCapabilityMatrix(
            provider_id=provider_id,
            unrealized_pnl_truth_support="spot_fifo_cost_basis_plus_live_bid",
            realized_pnl_truth_support="spot_trade_history_fifo_authoritative_when_balances_match",
            lifecycle_completeness="rest_history_without_replace",
            replace_supported=False,
            expire_supported=True,
            fee_truth_confidence="spot_trade_history_authoritative",
            user_stream_confidence="rest_history_only",
            metadata={"proof": "spot_private_trade_history_and_balance"},
        )
    return ProviderCapabilityMatrix(
        provider_id=provider_id,
        unrealized_pnl_truth_support="partial_when_field_absent",
        realized_pnl_truth_support="exchange_history_authoritative_when_available",
        lifecycle_completeness="strong_without_replace",
        replace_supported=False,
        expire_supported=True,
        fee_truth_confidence="exchange_history_authoritative_when_available",
        user_stream_confidence="user_stream_plus_rest_repair",
        metadata={"proof": "tracked_single_process_scope"},
    )
