from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServiceBoundary:
    name: str
    owns_topics: tuple[str, ...] = ()
    consumes_topics: tuple[str, ...] = ()
    description: str = ""
    runtime_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "owns_topics": list(self.owns_topics),
            "consumes_topics": list(self.consumes_topics),
            "description": str(self.description),
            "runtime_required": bool(self.runtime_required),
        }


@dataclass(frozen=True)
class DistributedServiceMap:
    """Prepared service-extraction map for Variant 2 decomposition."""

    services: tuple[ServiceBoundary, ...] = field(default_factory=tuple)

    @classmethod
    def default(cls) -> "DistributedServiceMap":
        return cls(
            services=(
                ServiceBoundary(
                    name="market_scanner_service",
                    owns_topics=("autobot.tasks.scan",),
                    consumes_topics=(),
                    description="Builds candidate universe and scan tasks.",
                ),
                ServiceBoundary(
                    name="forecast_service",
                    owns_topics=("autobot.results.rankings", "autobot.results.signals"),
                    consumes_topics=("autobot.tasks.scan", "autobot.tasks.forecast"),
                    description="Computes rankings/forecast outputs for live node.",
                ),
                ServiceBoundary(
                    name="risk_service",
                    owns_topics=("autobot.events.audit",),
                    consumes_topics=("autobot.results.signals",),
                    description="Computes risk budgets and policy bounds.",
                ),
                ServiceBoundary(
                    name="execution_service",
                    owns_topics=("autobot.events.audit",),
                    consumes_topics=("autobot.results.signals",),
                    description="Submits and manages live orders.",
                    runtime_required=True,
                ),
                ServiceBoundary(
                    name="portfolio_service",
                    owns_topics=("autobot.events.audit",),
                    consumes_topics=("autobot.results.rankings",),
                    description="Allocation/rotation logic across symbols and market classes.",
                ),
                ServiceBoundary(
                    name="optimizer_service",
                    owns_topics=("autobot.tasks.optimize",),
                    consumes_topics=("autobot.events.audit",),
                    description="Bounded optimization recommendations from runtime telemetry.",
                ),
                ServiceBoundary(
                    name="advisory_service",
                    owns_topics=("autobot.events.audit",),
                    consumes_topics=("autobot.tasks.optimize",),
                    description="Optional LLM advisory layer (Groq/OpenAI-compatible).",
                ),
                ServiceBoundary(
                    name="audit_service",
                    owns_topics=("autobot.events.audit",),
                    consumes_topics=(),
                    description="Runtime audit export and mirror persistence.",
                    runtime_required=True,
                ),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {"services": [svc.to_dict() for svc in self.services]}
