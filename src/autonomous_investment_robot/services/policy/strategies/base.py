from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Signal:
    target_notional: float
    confidence: float
    expected_edge_bps: float
    why: dict


class Strategy(Protocol):
    name: str

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        ...
