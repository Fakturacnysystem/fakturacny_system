from __future__ import annotations

import math


def round_up_to_tick(value: float, tick: float) -> float:
    if tick <= 0:
        return value
    return math.ceil(value / tick) * tick


def round_down_to_tick(value: float, tick: float) -> float:
    if tick <= 0:
        return value
    return math.floor(value / tick) * tick


def round_qty_down(qty: float, step: float) -> float:
    if step <= 0:
        return max(0.0, qty)
    return max(0.0, math.floor(qty / step) * step)


def ensure_positive(value: float, fallback: float = 0.0) -> float:
    return value if value > 0.0 else fallback
