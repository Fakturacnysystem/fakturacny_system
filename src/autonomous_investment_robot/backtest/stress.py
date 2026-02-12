from __future__ import annotations


def apply_flash_crash(rows: list[dict], drop_pct: float = 0.2) -> list[dict]:
    shocked = [r.copy() for r in rows]
    if len(shocked) > 2:
        idx = len(shocked) // 2
        shocked[idx]["price"] *= (1 - drop_pct)
    return shocked
