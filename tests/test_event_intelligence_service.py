from datetime import datetime, timezone

from autonomous_investment_robot.services.event_intelligence_service.service import EventIntelligenceService


def test_event_intelligence_rejects_weak_manipulative_sources():
    report = EventIntelligenceService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        features={"event_price_move_alignment": 0.2},
        forecast=None,
        events=[
            {
                "source": "anon_channel",
                "trust_score": 0.1,
                "novelty": 0.9,
                "impact_score": 0.8,
                "sentiment": -0.8,
                "manipulation_risk": 0.95,
                "relevance": 1.0,
                "symbols": ["BTCUSDT"],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    assert report.recommended_action == "no_trade"
    assert report.adversarial.adversarial_risk >= 0.7
    assert report.source_trust.weak_source_ratio > 0.0
    assert report.provenance.partial is False


def test_event_intelligence_degrades_when_move_is_already_priced_in():
    report = EventIntelligenceService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        features={"event_price_move_alignment": 1.0, "event_impact_score": 0.9},
        forecast=None,
        events=[
            {
                "source": "major_wire",
                "trust_score": 0.9,
                "novelty": 0.4,
                "impact_score": 0.9,
                "sentiment": 0.6,
                "relevance": 1.0,
                "symbols": ["BTCUSDT"],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    assert report.priced_in.priced_in_probability >= 0.55
    assert report.recommended_action in {"trade_smaller", "no_trade"}
    assert report.partial is False


def test_event_intelligence_records_partial_provenance_without_events():
    report = EventIntelligenceService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        features={"event_novelty": 0.2},
        forecast=None,
        events=[],
    )

    assert report.partial is True
    assert report.provenance.partial is True
    assert "partial_event_intelligence" in report.reasons


def test_event_intelligence_without_events_does_not_inflate_risk():
    report = EventIntelligenceService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        features={"event_novelty": 0.2},
        forecast=None,
        events=[],
    )

    assert report.recommended_action == "continue"
    assert report.overall_risk_score <= 0.1
    assert report.metadata["trust_gap_risk"] == 0.0
