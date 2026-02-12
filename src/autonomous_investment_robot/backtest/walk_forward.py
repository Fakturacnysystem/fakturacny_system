from __future__ import annotations


def walk_forward_splits(rows: list[dict], train: int, test: int) -> list[tuple[list[dict], list[dict]]]:
    splits = []
    i = 0
    while i + train + test <= len(rows):
        splits.append((rows[i:i+train], rows[i+train:i+train+test]))
        i += test
    return splits
