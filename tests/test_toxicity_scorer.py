from __future__ import annotations

from autonomous_investment_robot.services.market_microstructure.toxicity import ToxicityScorer


def test_toxicity_score_rises_when_microstructure_deteriorates():
    scorer = ToxicityScorer(window=16)
    _ = scorer.update(symbol="XBTUSD", ts=1.0, mid=100.0, spread_bps=2.0, depth_notional=200_000.0)
    calm = scorer.update(symbol="XBTUSD", ts=2.0, mid=100.02, spread_bps=2.2, depth_notional=198_000.0)
    toxic = scorer.update(symbol="XBTUSD", ts=3.0, mid=99.4, spread_bps=18.0, depth_notional=70_000.0)

    assert 0.0 <= calm.score <= 1.0
    assert 0.0 <= toxic.score <= 1.0
    assert toxic.score > calm.score
    assert toxic.spread_level >= calm.spread_level
    assert toxic.depth_collapse >= calm.depth_collapse


def test_toxicity_score_is_clamped_between_zero_and_one():
    scorer = ToxicityScorer(window=8)
    _ = scorer.update(symbol="ETHUSD", ts=1.0, mid=1.0, spread_bps=0.0, depth_notional=1_000.0)
    out = scorer.update(symbol="ETHUSD", ts=2.0, mid=1000.0, spread_bps=10_000.0, depth_notional=0.0)
    assert 0.0 <= out.score <= 1.0

