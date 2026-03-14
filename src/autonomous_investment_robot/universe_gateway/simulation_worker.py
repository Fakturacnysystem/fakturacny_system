from __future__ import annotations

import logging
import os
import signal
import time
from typing import Any

from autonomous_investment_robot.universe_gateway.contracts import EventEnvelope
from autonomous_investment_robot.universe_gateway.event_bus import UniverseEventBus
from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore

LOGGER = logging.getLogger(__name__)


class SimulationWorker:
    def __init__(self, *, bus: UniverseEventBus, store: UniverseProjectionStore, interval_s: float = 10.0) -> None:
        self.bus = bus
        self.store = store
        self.interval_s = max(1.0, float(interval_s))
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def _compute_scenarios(self) -> list[dict[str, float]]:
        capital = self.store.get_latest(domain="capital")
        decision = self.store.get_latest(domain="decision")
        equity = float(capital.get("equity", 0.0) or 0.0)
        profit = float(capital.get("profit", 0.0) or 0.0)
        drawdown = abs(float(capital.get("drawdown_pct", 0.0) or 0.0))
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        base = max(1.0, abs(equity) if equity else 1_000.0)
        return [
            {
                "branch_probability": 0.52,
                "expected_pnl": (profit * 0.7) + (base * confidence * 0.002),
                "risk_score": min(100.0, drawdown + (100.0 - confidence * 100.0) * 0.35),
            },
            {
                "branch_probability": 0.31,
                "expected_pnl": (profit * 1.1) + (base * confidence * 0.003),
                "risk_score": min(100.0, drawdown + (100.0 - confidence * 100.0) * 0.5),
            },
            {
                "branch_probability": 0.17,
                "expected_pnl": (profit * -0.6) - (base * 0.0015),
                "risk_score": min(100.0, drawdown + 66.0),
            },
        ]

    def run_forever(self) -> None:
        LOGGER.info("universe_simulation_worker_start interval_s=%s", self.interval_s)
        while not self._stopping:
            scenarios = self._compute_scenarios()
            payload = {"scenarios": scenarios, "generated_at": time.time()}
            self.store.upsert_latest(domain="simulation", payload=payload)

            envelope = EventEnvelope.build(
                event_type="simulation_branch_update",
                run_id=str(self.store.get_latest(domain="system").get("run_id", "latest") or "latest"),
                symbol="",
                mode="Paper",
                confidence=0.72,
                source_module="simulation-worker",
                payload=payload,
            )
            self.bus.publish_event(domain="simulation", envelope=envelope)
            self.bus.publish_ws(
                channel="simulation",
                payload={
                    "type": "simulation",
                    "event_type": envelope.event_type,
                    "timestamp": envelope.timestamp,
                    "payload": payload,
                },
            )
            time.sleep(self.interval_s)
        LOGGER.info("universe_simulation_worker_stop")


def run_worker_forever() -> int:
    logging.basicConfig(level=os.getenv("AUTONOMOUS_LOG_LEVEL", "INFO").upper())
    bus = UniverseEventBus.from_env()
    store = UniverseProjectionStore.from_env()
    worker = SimulationWorker(
        bus=bus,
        store=store,
        interval_s=float(os.getenv("AUTONOMOUS_UNIVERSE_SIMULATION_INTERVAL_S", "10") or "10"),
    )

    def _handle_signal(_sig: int, _frame: Any) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker.run_forever()
    return 0
