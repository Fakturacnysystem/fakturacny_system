from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _pct_to_bps(pct_value: Any) -> float:
    # Kraken fee payloads commonly return percentages (0.26 => 26 bps).
    return max(0.0, _safe_float(pct_value, 0.0) * 100.0)


@dataclass
class FeeProfile:
    spot_maker_fee_bps: float
    spot_taker_fee_bps: float
    perps_maker_fee_bps: float
    perps_taker_fee_bps: float
    source: str
    trade_volume_quote: float
    updated_ts: float

    @property
    def spot_worst_case_bps(self) -> float:
        return max(float(self.spot_maker_fee_bps), float(self.spot_taker_fee_bps))

    @property
    def perps_worst_case_bps(self) -> float:
        return max(float(self.perps_maker_fee_bps), float(self.perps_taker_fee_bps))


class FeeProfileService:
    """Refreshes account fee tiers and exposes safe worst-case fee bps."""

    def __init__(
        self,
        *,
        connector_spot: Any | None = None,
        connector_perps: Any | None = None,
        default_entry_fee_bps: float = 30.0,
        default_exit_fee_bps: float = 30.0,
        refresh_interval_s: float = 21600.0,
        volume_jump_ratio: float = 0.25,
    ) -> None:
        self.connector_spot = connector_spot
        self.connector_perps = connector_perps
        base_fee = max(0.0, float(default_entry_fee_bps), float(default_exit_fee_bps), 30.0)
        self.refresh_interval_s = max(60.0, float(refresh_interval_s))
        self.volume_jump_ratio = max(0.0, float(volume_jump_ratio))
        self.profile = FeeProfile(
            spot_maker_fee_bps=base_fee,
            spot_taker_fee_bps=base_fee,
            perps_maker_fee_bps=base_fee,
            perps_taker_fee_bps=base_fee,
            source="fallback",
            trade_volume_quote=0.0,
            updated_ts=0.0,
        )
        self._last_refresh_ts = 0.0
        self._last_trade_volume_quote = 0.0

    def classify_liquidity_role(
        self,
        *,
        fill_payload: dict[str, Any] | None,
        order_payload: dict[str, Any] | None = None,
    ) -> str:
        """Classify fill liquidity role as maker/taker with conservative fallback."""
        fill = fill_payload or {}
        order = order_payload or {}
        for key in ("liquidity", "liquidityRole", "liquidity_role"):
            val = str(fill.get(key, "") or "").strip().lower()
            if val in {"maker", "m"}:
                return "maker"
            if val in {"taker", "t"}:
                return "taker"
        for key in ("maker", "is_maker", "isMaker"):
            if key in fill:
                try:
                    return "maker" if bool(fill.get(key)) else "taker"
                except Exception:
                    pass
        oflags = str(order.get("oflags", "") or order.get("flags", "") or "").lower()
        order_type = str(order.get("ordertype", order.get("orderType", "")) or "").lower()
        if "post" in oflags:
            return "maker"
        if order_type in {"market", "mkt"}:
            return "taker"
        # Unknown => conservative taker assumption.
        return "taker"

    def _spot_payload(self, pair: str | None) -> dict[str, Any]:
        if self.connector_spot is None or not hasattr(self.connector_spot, "trade_volume"):
            return {}
        try:
            raw = self.connector_spot.trade_volume(pair=pair, fee_info=True)
        except Exception:
            return {}
        if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
            return dict(raw.get("result", {}))
        return dict(raw) if isinstance(raw, dict) else {}

    def _parse_spot_fees(self, payload: dict[str, Any], pair: str | None) -> tuple[float, float, float]:
        taker_bps = self.profile.spot_taker_fee_bps
        maker_bps = self.profile.spot_maker_fee_bps
        volume_quote = max(0.0, _safe_float(payload.get("volume", payload.get("vol", 0.0)), 0.0))

        fees = payload.get("fees", {})
        fees_maker = payload.get("fees_maker", {})
        if isinstance(fees, dict) and fees:
            fee_row: dict[str, Any] | None = None
            if pair and isinstance(fees.get(pair), dict):
                fee_row = fees.get(pair)
            elif fees:
                first = next(iter(fees.values()))
                if isinstance(first, dict):
                    fee_row = first
            if isinstance(fee_row, dict):
                taker_bps = max(taker_bps, _pct_to_bps(fee_row.get("fee")))
        if isinstance(fees_maker, dict) and fees_maker:
            fee_row_maker: dict[str, Any] | None = None
            if pair and isinstance(fees_maker.get(pair), dict):
                fee_row_maker = fees_maker.get(pair)
            elif fees_maker:
                first_maker = next(iter(fees_maker.values()))
                if isinstance(first_maker, dict):
                    fee_row_maker = first_maker
            if isinstance(fee_row_maker, dict):
                maker_bps = max(maker_bps, _pct_to_bps(fee_row_maker.get("fee")))

        # Safety: if maker could not be determined, treat maker as taker floor.
        maker_bps = max(0.0, min(maker_bps, taker_bps))
        taker_bps = max(taker_bps, maker_bps)
        return maker_bps, taker_bps, volume_quote

    def _parse_perps_fees(self, payload: dict[str, Any]) -> tuple[float, float]:
        maker = self.profile.perps_maker_fee_bps
        taker = self.profile.perps_taker_fee_bps
        # Kraken futures payloads differ by endpoint, so parse defensively.
        for key in ("makerFee", "maker_fee", "maker", "feeMaker"):
            if key in payload:
                maker = max(maker, _pct_to_bps(payload.get(key)))
        for key in ("takerFee", "taker_fee", "taker", "feeTaker"):
            if key in payload:
                taker = max(taker, _pct_to_bps(payload.get(key)))
        if taker <= 0.0 and maker > 0.0:
            taker = maker
        maker = max(0.0, min(maker, taker if taker > 0.0 else maker))
        taker = max(taker, maker)
        return maker, taker

    def _perps_payload(self) -> dict[str, Any]:
        if self.connector_perps is None:
            return {}
        # Prefer explicit fee endpoint if available.
        for method_name in ("fee_schedule", "fees", "account_overview"):
            if not hasattr(self.connector_perps, method_name):
                continue
            try:
                payload = getattr(self.connector_perps, method_name)()
            except Exception:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
                return dict(payload.get("result", {}))
            if isinstance(payload, dict):
                return dict(payload)
        return {}

    def refresh(
        self,
        *,
        pair: str | None = None,
        force: bool = False,
        trade_volume_hint: float | None = None,
    ) -> FeeProfile:
        now = time.time()
        if not force and (now - self._last_refresh_ts) < self.refresh_interval_s:
            return self.profile

        source_parts: list[str] = []
        spot_payload = self._spot_payload(pair)
        if spot_payload:
            source_parts.append("spot_trade_volume")
        spot_maker, spot_taker, volume_quote = self._parse_spot_fees(spot_payload, pair)

        perps_payload = self._perps_payload()
        if perps_payload:
            source_parts.append("perps_account")
        perps_maker, perps_taker = self._parse_perps_fees(perps_payload)

        if trade_volume_hint is not None:
            volume_quote = max(volume_quote, max(0.0, float(trade_volume_hint)))

        self.profile = FeeProfile(
            spot_maker_fee_bps=float(max(0.0, spot_maker)),
            spot_taker_fee_bps=float(max(0.0, spot_taker)),
            perps_maker_fee_bps=float(max(0.0, perps_maker)),
            perps_taker_fee_bps=float(max(0.0, perps_taker)),
            source="+".join(source_parts) if source_parts else "fallback",
            trade_volume_quote=float(max(0.0, volume_quote)),
            updated_ts=float(now),
        )
        self._last_refresh_ts = float(now)
        self._last_trade_volume_quote = max(self._last_trade_volume_quote, float(volume_quote))
        return self.profile

    def maybe_refresh(
        self,
        *,
        pair: str | None = None,
        now_ts: float | None = None,
        trade_volume_hint: float | None = None,
    ) -> FeeProfile:
        now = time.time() if now_ts is None else float(now_ts)
        if (now - self._last_refresh_ts) >= self.refresh_interval_s:
            return self.refresh(pair=pair, force=True, trade_volume_hint=trade_volume_hint)
        if trade_volume_hint is None:
            return self.profile
        hint = max(0.0, float(trade_volume_hint))
        if self._last_trade_volume_quote <= 0.0:
            self._last_trade_volume_quote = hint
            return self.profile
        jump = (hint - self._last_trade_volume_quote) / max(self._last_trade_volume_quote, 1e-9)
        if jump >= self.volume_jump_ratio:
            return self.refresh(pair=pair, force=True, trade_volume_hint=hint)
        return self.profile

    def worst_case_entry_fee_bps(self, *, market: str = "spot") -> float:
        market_n = str(market or "spot").strip().lower()
        if market_n == "perps":
            return float(self.profile.perps_worst_case_bps)
        return float(self.profile.spot_worst_case_bps)

    def worst_case_exit_fee_bps(self, *, market: str = "spot") -> float:
        # Same conservative assumption for exits.
        return self.worst_case_entry_fee_bps(market=market)
