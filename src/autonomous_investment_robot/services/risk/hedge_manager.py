from __future__ import annotations

from dataclasses import dataclass
import math
import os
import time


@dataclass
class HedgeConfig:
    enabled: bool = True
    max_ratio: float = 0.80
    step_ratio: float = 0.20
    dd_step: float = 0.008
    min_notional: float = 10.0
    max_notional_per_symbol: float = 200.0
    close_profit_net: float = 0.02
    funding_window_s: float = 1200.0
    funding_adverse_scale: float = 0.6

    @classmethod
    def from_env(cls) -> "HedgeConfig":
        def _b(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return bool(default)
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

        def _f(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None:
                return float(default)
            try:
                return float(str(raw).strip())
            except Exception:
                return float(default)

        return cls(
            enabled=_b("AUTONOMOUS_HEDGE_ENABLED", True),
            max_ratio=max(0.0, min(1.0, _f("AUTONOMOUS_HEDGE_MAX_RATIO", 0.80))),
            step_ratio=max(0.01, min(1.0, _f("AUTONOMOUS_HEDGE_STEP_RATIO", 0.20))),
            dd_step=max(1e-6, _f("AUTONOMOUS_HEDGE_DD_STEP", 0.008)),
            min_notional=max(0.0, _f("AUTONOMOUS_HEDGE_MIN_NOTIONAL", 10.0)),
            max_notional_per_symbol=max(0.0, _f("AUTONOMOUS_HEDGE_MAX_NOTIONAL_PER_SYMBOL", 200.0)),
            close_profit_net=max(0.02, _f("AUTONOMOUS_HEDGE_CLOSE_PROFIT_NET", 0.02)),
            funding_window_s=max(60.0, _f("AUTONOMOUS_HEDGE_FUNDING_WINDOW_S", 1200.0)),
            funding_adverse_scale=max(0.0, min(1.0, _f("AUTONOMOUS_HEDGE_FUNDING_ADVERSE_SCALE", 0.6))),
        )


@dataclass
class HedgeState:
    hedge_notional_quote: float = 0.0
    hedge_ratio: float = 0.0
    last_open_ts: float = 0.0


@dataclass
class HedgeOpenAction:
    symbol: str
    side: str
    target_notional_quote: float
    reduce_only: bool
    reason: str
    metadata: dict[str, float | str | bool]


@dataclass
class HedgeDecision:
    should_open: bool
    action: HedgeOpenAction | None
    reason: str


class HedgeManager:
    """Opens hedge tranches for stuck positions. Never performs loss-closing actions."""

    def __init__(self, config: HedgeConfig | None = None) -> None:
        self.config = config or HedgeConfig.from_env()
        self._states: dict[str, HedgeState] = {}

    def _for(self, symbol: str) -> HedgeState:
        key = str(symbol or "").upper()
        if key not in self._states:
            self._states[key] = HedgeState()
        return self._states[key]

    def _desired_ratio(self, unrealized_pnl_ratio: float, pressure: float) -> float:
        adverse = max(0.0, abs(min(0.0, float(unrealized_pnl_ratio))))
        steps = int(adverse / max(self.config.dd_step, 1e-9))
        base = min(self.config.max_ratio, steps * self.config.step_ratio)
        weighted = max(base, min(self.config.max_ratio, pressure * self.config.max_ratio))
        return max(0.0, min(self.config.max_ratio, weighted))

    def maybe_open_hedge(
        self,
        *,
        symbol: str,
        perps_symbol: str,
        spot_signed_exposure_quote: float,
        unrealized_pnl_ratio: float,
        pressure: float,
        funding_rate: float,
        funding_eta_s: float | None,
        now_ts: float | None = None,
        perps_available: bool = True,
    ) -> HedgeDecision:
        if not self.config.enabled:
            return HedgeDecision(should_open=False, action=None, reason="hedge_disabled")
        if not perps_available or not perps_symbol:
            return HedgeDecision(should_open=False, action=None, reason="perps_unavailable")

        exposure = abs(float(spot_signed_exposure_quote))
        if exposure < self.config.min_notional:
            return HedgeDecision(should_open=False, action=None, reason="exposure_too_small")

        desired_ratio = self._desired_ratio(unrealized_pnl_ratio, pressure)
        if desired_ratio <= 0.0:
            return HedgeDecision(should_open=False, action=None, reason="no_hedge_needed")

        # Funding-aware conservative scaling near funding cutover.
        eta = float(funding_eta_s) if funding_eta_s is not None else (self.config.funding_window_s + 1.0)
        adverse_funding = (spot_signed_exposure_quote > 0.0 and funding_rate > 0.0) or (
            spot_signed_exposure_quote < 0.0 and funding_rate < 0.0
        )
        if adverse_funding and eta <= self.config.funding_window_s:
            desired_ratio *= self.config.funding_adverse_scale

        desired_hedge_notional = min(
            exposure * desired_ratio,
            self.config.max_notional_per_symbol if self.config.max_notional_per_symbol > 0.0 else exposure,
        )
        if desired_hedge_notional <= 0.0:
            return HedgeDecision(should_open=False, action=None, reason="desired_hedge_zero")

        state = self._for(symbol)
        increment = max(0.0, desired_hedge_notional - state.hedge_notional_quote)
        if increment < self.config.min_notional:
            return HedgeDecision(should_open=False, action=None, reason="hedge_increment_too_small")

        now = time.time() if now_ts is None else float(now_ts)
        side = "sell" if spot_signed_exposure_quote > 0.0 else "buy"
        action = HedgeOpenAction(
            symbol=str(perps_symbol),
            side=side,
            target_notional_quote=increment,
            reduce_only=False,
            reason="stuck_position_hedge_tranche_open",
            metadata={
                "source_symbol": str(symbol),
                "desired_ratio": float(desired_ratio),
                "hedge_notional_target": float(desired_hedge_notional),
                "hedge_increment": float(increment),
                "unrealized_pnl_ratio": float(unrealized_pnl_ratio),
                "pressure": float(pressure),
                "funding_rate": float(funding_rate),
                "funding_eta_s": float(eta),
            },
        )
        state.hedge_notional_quote = min(desired_hedge_notional, state.hedge_notional_quote + increment)
        state.hedge_ratio = 0.0 if exposure <= 0.0 else min(1.0, state.hedge_notional_quote / exposure)
        state.last_open_ts = now
        return HedgeDecision(should_open=True, action=action, reason="hedge_open")

    def can_close_hedge(
        self,
        *,
        profit_gate_allowed: bool,
        expected_net_profit_ratio: float,
    ) -> bool:
        if not profit_gate_allowed:
            return False
        return float(expected_net_profit_ratio) >= float(self.config.close_profit_net)

    def note_hedge_reduced(self, symbol: str, reduced_notional_quote: float) -> None:
        st = self._for(symbol)
        st.hedge_notional_quote = max(0.0, st.hedge_notional_quote - max(0.0, float(reduced_notional_quote)))
        if st.hedge_notional_quote <= 1e-9:
            st.hedge_notional_quote = 0.0
            st.hedge_ratio = 0.0

    def snapshot(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for sym, st in self._states.items():
            out[sym] = {
                "hedge_notional_quote": float(st.hedge_notional_quote),
                "hedge_ratio": float(st.hedge_ratio),
                "last_open_ts": float(st.last_open_ts),
            }
        return out
