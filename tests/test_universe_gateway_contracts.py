from __future__ import annotations

from autonomous_investment_robot.universe_gateway.contracts import EventEnvelope


def test_event_envelope_build_and_parse_roundtrip() -> None:
    env = EventEnvelope.build(
        event_type="decision_tick",
        run_id="run-1",
        symbol="BTCUSD",
        mode="Canary",
        confidence=0.84,
        source_module="universe-mind",
        payload={"action": "enter"},
    )

    as_dict = env.to_dict()
    parsed = EventEnvelope.from_mapping(as_dict)

    assert parsed.event_id == env.event_id
    assert parsed.event_type == "decision_tick"
    assert parsed.run_id == "run-1"
    assert parsed.symbol == "BTCUSD"
    assert parsed.mode == "Canary"
    assert parsed.confidence == 0.84
    assert parsed.payload["action"] == "enter"


def test_event_envelope_clamps_confidence() -> None:
    env = EventEnvelope.build(
        event_type="risk",
        run_id="r",
        symbol="",
        mode="Paper",
        confidence=2.5,
        source_module="shield",
        payload={},
    )
    assert env.confidence == 1.0
