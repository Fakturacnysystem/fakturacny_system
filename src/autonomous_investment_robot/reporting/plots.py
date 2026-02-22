from __future__ import annotations

from pathlib import Path


def make_equity_plot(rows: list[dict], out_path: str) -> str:
    # Minimal text-based artifact to avoid heavy plotting deps in constrained env.
    path = Path(out_path)
    lines = ["index,equity"] + [f"{i},{r['equity']}" for i, r in enumerate(rows)]
    path.write_text("\n".join(lines))
    return str(path)
