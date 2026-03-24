from __future__ import annotations

from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import BackendSelector, DistributedHealthReport


class DistributedRuntimeService:
    def __init__(self, *, enabled: bool = False, backend: str = "single_process") -> None:
        self.enabled = bool(enabled)
        self.backend = backend

    def selector(self) -> BackendSelector:
        return BackendSelector(
            backend=self.backend,
            enabled=self.enabled,
            reason="distributed_runtime_disabled_by_default" if not self.enabled else "distributed_runtime_enabled",
            metadata={"proof_only": not self.enabled},
        )

    def health_report(self) -> DistributedHealthReport:
        selector = self.selector()
        mode = "distributed" if selector.enabled else "single_process"
        return DistributedHealthReport(
            ts=datetime.now(timezone.utc),
            mode=mode,
            selector=selector,
            stream_health="disabled" if not selector.enabled else "unknown",
            storage_health="disabled" if not selector.enabled else "unknown",
            worker_health="disabled" if not selector.enabled else "unknown",
            metadata={"proof_only": not selector.enabled},
        )
