from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from autonomous_investment_robot.core.contracts import TradeEpisode


class EpisodicTradeMemory:
    def __init__(self, run_dir: str) -> None:
        self.path = Path(run_dir) / "trade_episode_memory.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.episodes: list[TradeEpisode] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                self.episodes.append(TradeEpisode(**payload))

    def record(self, episode: TradeEpisode) -> None:
        self.episodes.append(episode)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(episode), sort_keys=True, default=str) + "\n")

    def recent(self, limit: int = 50) -> list[TradeEpisode]:
        return self.episodes[-limit:]
