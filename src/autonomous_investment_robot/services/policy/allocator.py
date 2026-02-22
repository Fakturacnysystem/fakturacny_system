from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AllocatorState:
    weights: dict[str, float] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    cooldown: dict[str, int] = field(default_factory=dict)


class BanditAllocator:
    def __init__(self, decay: float, max_weight: float, min_samples: int, fatal_sigma_loss: float, cooldown_steps: int) -> None:
        self.decay = decay
        self.max_weight = max_weight
        self.min_samples = min_samples
        self.fatal_sigma_loss = fatal_sigma_loss
        self.cooldown_steps = cooldown_steps
        self.state = AllocatorState()

    def update_performance(self, strategy: str, net_pnl_bps: float) -> None:
        prev = self.state.scores.get(strategy, 0.0)
        self.state.scores[strategy] = self.decay * prev + (1 - self.decay) * net_pnl_bps
        self.state.counts[strategy] = self.state.counts.get(strategy, 0) + 1
        if net_pnl_bps < -self.fatal_sigma_loss:
            self.state.cooldown[strategy] = self.cooldown_steps

    def step_cooldowns(self) -> None:
        for k in list(self.state.cooldown.keys()):
            self.state.cooldown[k] -= 1
            if self.state.cooldown[k] <= 0:
                del self.state.cooldown[k]

    def allocate(self, strategies: list[str]) -> dict[str, float]:
        raw = {}
        for s in strategies:
            if s in self.state.cooldown:
                raw[s] = 0.0
                continue
            if self.state.counts.get(s, 0) < self.min_samples:
                raw[s] = 1.0
            else:
                raw[s] = max(0.0, self.state.scores.get(s, 0.0) + 1.0)
        total = sum(raw.values()) or 1.0
        weights = {k: min(self.max_weight, v / total) for k, v in raw.items()}
        renorm = sum(weights.values()) or 1.0
        self.state.weights = {k: v / renorm for k, v in weights.items()}
        return self.state.weights
