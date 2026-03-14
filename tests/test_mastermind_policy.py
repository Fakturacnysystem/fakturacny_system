from __future__ import annotations

from autonomous_investment_robot.services.policy.mastermind_policy import MastermindConfig, MastermindPolicy
from autonomous_investment_robot.services.policy.service import OrderIntent


def _intent() -> OrderIntent:
    return OrderIntent(
        symbol="XBTEUR",
        side="buy",
        target_notional=20.0,
        why={
            "components": [
                {
                    "strategy": "carry",
                    "signal_side": "buy",
                    "signal_notional": 20.0,
                    "final_edge_bps": 3.0,
                    "confidence": 0.5,
                    "cost_total_bps": 1.0,
                },
                {
                    "strategy": "pairs_stat_arb",
                    "signal_side": "buy",
                    "signal_notional": 18.0,
                    "final_edge_bps": 5.0,
                    "confidence": 0.8,
                    "cost_total_bps": 1.5,
                },
            ]
        },
    )


def test_mastermind_mode_switching() -> None:
    m = MastermindPolicy(MastermindConfig(enabled=True, max_entry_orders_per_min=6))
    assert m.mode(exits_only=True, rate_limit_storm=False, ws_healthy=True) == "exits_only"
    assert m.mode(exits_only=False, rate_limit_storm=True, ws_healthy=True) == "normal"
    assert m.mode(exits_only=False, rate_limit_storm=False, ws_healthy=True) == "aggressive_hf"


def test_mastermind_selects_best_strategy_component() -> None:
    m = MastermindPolicy(MastermindConfig(enabled=True, max_entry_orders_per_min=6))
    out = m.choose(base_intent=_intent(), now_ts=1000.0, mode="aggressive_hf")
    assert out.allowed is True
    assert out.intent is not None
    assert out.selected_strategy == "pairs_stat_arb"
    assert out.intent.target_notional == 18.0


def test_mastermind_entry_budget_blocks_excess_entries() -> None:
    m = MastermindPolicy(MastermindConfig(enabled=True, max_entry_orders_per_min=1))
    m.note_entry_submission(now_ts=1000.0)
    out = m.choose(base_intent=_intent(), now_ts=1010.0, mode="aggressive_hf")
    assert out.allowed is False
    assert out.reason == "mastermind_entry_budget"


def test_mastermind_choose_propagates_mission_bridge_advisory() -> None:
    m = MastermindPolicy(MastermindConfig(enabled=True, max_entry_orders_per_min=6))
    intent = _intent()
    intent.why["mission_bridge"] = {
        "mission": "observation_only",
        "reason_codes": ["observe_only_guard", "risk_off_posture"],
        "no_trade_preferred": True,
        "allow_new_risk": False,
    }
    out = m.choose(base_intent=intent, now_ts=1000.0, mode="aggressive_hf")
    assert out.allowed is True
    assert out.intent is not None
    mastermind_payload = out.intent.why.get("mastermind", {})
    assert mastermind_payload.get("mission_advisory", {}).get("mission") == "observation_only"
    assert mastermind_payload.get("mission_advisory", {}).get("reason_codes") == [
        "observe_only_guard",
        "risk_off_posture",
    ]
    assert mastermind_payload.get("mission_advisory", {}).get("no_trade_preferred") is True
    assert mastermind_payload.get("mission_advisory", {}).get("allow_new_risk") is False


def test_mastermind_blocks_entry_side_flip_by_default() -> None:
    m = MastermindPolicy(MastermindConfig(enabled=True, max_entry_orders_per_min=6))
    intent = OrderIntent(
        symbol="SOLEUR",
        side="buy",
        target_notional=2.0,
        why={
            "components": [
                {
                    "strategy": "pairs_stat_arb",
                    "signal_side": "sell",
                    "signal_notional": 10.0,
                    "final_edge_bps": 50.0,
                    "confidence": 0.9,
                    "cost_total_bps": 1.0,
                }
            ]
        },
    )
    out = m.choose(base_intent=intent, now_ts=1000.0, mode="aggressive_hf")
    assert out.allowed is True
    assert out.intent is not None
    assert out.intent.side == "buy"
    assert out.intent.target_notional == 2.0
    mastermind_payload = out.intent.why.get("mastermind", {})
    assert mastermind_payload.get("entry_side_flip_blocked") is True
    assert mastermind_payload.get("entry_side_flip_original_signal_side") == "sell"


def test_mastermind_allows_entry_side_flip_when_enabled() -> None:
    m = MastermindPolicy(
        MastermindConfig(enabled=True, max_entry_orders_per_min=6, allow_entry_side_flip=True)
    )
    intent = OrderIntent(
        symbol="SOLEUR",
        side="buy",
        target_notional=2.0,
        why={
            "components": [
                {
                    "strategy": "pairs_stat_arb",
                    "signal_side": "sell",
                    "signal_notional": 10.0,
                    "final_edge_bps": 50.0,
                    "confidence": 0.9,
                    "cost_total_bps": 1.0,
                }
            ]
        },
    )
    out = m.choose(base_intent=intent, now_ts=1000.0, mode="aggressive_hf")
    assert out.allowed is True
    assert out.intent is not None
    assert out.intent.side == "sell"
    assert out.intent.target_notional == 10.0
