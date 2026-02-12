from dataclasses import dataclass


@dataclass
class EngineDecision:
    name: str
    enabled: bool
    reason: str


class BaseEngine:
    name = "base"

    def pre_trade_checks(self) -> list[str]:
        return []


class TrendMomentumEngine(BaseEngine):
    name = "trend_momentum"


class MeanReversionEngine(BaseEngine):
    name = "mean_reversion"


class CarryFundingEngine(BaseEngine):
    name = "carry_funding"


class BasisEngine(BaseEngine):
    name = "basis"


class StatArbEngine(BaseEngine):
    name = "stat_arb"


class OptionsHedgingEngine(BaseEngine):
    name = "options_hedging"
