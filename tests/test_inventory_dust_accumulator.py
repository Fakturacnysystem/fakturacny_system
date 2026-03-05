from __future__ import annotations

import json
import time
from dataclasses import dataclass

from autonomous_investment_robot.config.settings import (
    ExecutionSettings,
    KrakenSpotExecutionSettings,
    LiveUnlockSettings,
    PolicySettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.services.governance.service import GovernanceDecision
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskDecision


@dataclass
class _ExecResult:
    status: str
    reason: str = ""
    order: dict | None = None


class _FakeLive:
    killed = False
    kill_reason = ""

    def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
        now = time.time()
        bid = 100.0
        ask = 100.2
        return {
            "pair": symbol,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0,
            "spread_bps": ((ask - bid) / ((ask + bid) / 2.0)) * 10000.0,
            "depth_notional": 500_000.0,
            "ts": now,
            "stale": False,
            "level": "L2",
            "source": "ws",
        }

    def sync_fill_ledger(self, pair: str, mark_price: float):  # noqa: ARG002
        return {
            "pair": pair,
            "position_notional_signed": 0.0,
            "exposure_notional": 0.0,
            "net_pnl_after_fees_quote": 0.0,
            "fees_quote": 0.0,
            "filled_notional_quote": 0.0,
            "min_trade_notional_quote": 0.0,
            "execution_qa": {
                "implementation_shortfall_bps": 0.0,
                "latency_p50_ms": 1.0,
                "latency_p95_ms": 2.0,
                "fill_probability": 0.9,
                "orders_filled": 0.0,
            },
        }

    def reconcile_live_state(self, internal_exposure: float):  # noqa: ARG002
        return True, "ok"

    def _available_quote_balance(self, pair: str):  # noqa: ARG002
        return "ZUSD", 10_000.0


def _settings(run_dir: str) -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        explicit_live_enable=True,
        ack_live_risks=True,
        canary_mode=True,
        safe_mode_default=False,
        universe=["XBTEUR"],
        storage=StorageSettings(run_dir=run_dir),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
                canary_required_before_full=False,
            )
        ),
        execution=ExecutionSettings(
            mode="live_testnet",
            fee_bps=1.0,
            slippage_bps=0.5,
            maker_preference=False,
            kraken_spot=KrakenSpotExecutionSettings(allow_unknown_permissions=True, dry_run_long_only=False),
        ),
        policy=PolicySettings(confidence_threshold=0.0, safety_buffer_bps=-40.0, base_risk_budget=50.0),
        risk=RiskLimits(
            max_daily_loss_pct=10.0,
            max_weekly_loss_pct=20.0,
            max_drawdown_pct=20.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_symbol_exposure_notional=1500.0,
            max_cluster_exposure_notional=2000.0,
            max_orders_per_min=200,
            leverage=0,
            target_portfolio_vol=0.5,
            cvar_limit_pct=50.0,
            stress_loss_limit_pct=50.0,
            max_spread_bps=1000.0,
            min_depth_notional=0.0,
            stale_data_seconds=120.0,
            min_margin_buffer=0.5,
            max_funding_cost_per_day=999.0,
            max_oi_spike_pct=999.0,
            max_liquidation_spike=99999999.0,
            divergence_threshold_bps=999.0,
            crowding_score_kill=999.0,
        ),
        tco=TCOSettings(max_total_cost_bps=200.0, max_impact_bps=100.0),
    )


def _configure_env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "1")
    monkeypatch.setenv("AUTONOMOUS_LIVE_POLL_SECONDS", "0.5")
    monkeypatch.setenv("AUTONOMOUS_PORTFOLIO_OPTIMIZER", "false")
    monkeypatch.setenv("AUTONOMOUS_GUARDS_MODE", "fatal_only")
    monkeypatch.setenv("AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", "10")
    monkeypatch.setenv("AUTONOMOUS_REBALANCE_DEADZONE_FACTOR", "0")
    monkeypatch.setenv("AUTONOMOUS_REBALANCE_DEADZONE_FLOOR", "0")
    monkeypatch.setenv("AUTONOMOUS_SELF_TUNER_ENABLED", "false")
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")


def test_dust_accumulator_triggers_once(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    run_dir = tmp_path / "run_dust"
    orc = RobotOrchestrator(_settings(str(run_dir)))
    live = _FakeLive()

    execute_calls: list[float] = []

    def _exec(intent):
        execute_calls.append(float(intent.target_notional))
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional})

    def _risk(*args, **kwargs):
        intent = kwargs.get("intent")
        notional = float(getattr(intent, "target_notional", 0.0))
        return RiskDecision(True, "passed", adjusted_notional=notional, details={})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = _risk  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = (  # type: ignore[method-assign]
        lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)
    )

    def _make_intent_small(_fc, _features, _fee, _slip):
        return OrderIntent(
            "XBTEUR",
            "buy",
            3.0,
            {
                "components": [
                    {
                        "strategy": "unit",
                        "weight": 1.0,
                        "final_edge_bps": 35.0,
                        "cost_total_bps": 1.0,
                    }
                ]
            },
        )

    orc.policy.make_intent = _make_intent_small  # type: ignore[method-assign]
    out1 = orc._live_loop(live, symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out1["status"] == "ok"
    assert execute_calls == []

    dust_path = run_dir / "dust_accumulator.json"
    dust_after_first = json.loads(dust_path.read_text(encoding="utf-8"))
    assert dust_after_first["XBTEUR"]["buy"] == 3.0

    def _make_intent_second(_fc, _features, _fee, _slip):
        return OrderIntent(
            "XBTEUR",
            "buy",
            8.0,
            {
                "components": [
                    {
                        "strategy": "unit",
                        "weight": 1.0,
                        "final_edge_bps": 35.0,
                        "cost_total_bps": 1.0,
                    }
                ]
            },
        )

    orc.policy.make_intent = _make_intent_second  # type: ignore[method-assign]
    out2 = orc._live_loop(live, symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out2["status"] == "ok"
    assert len(execute_calls) == 1
    assert execute_calls[0] >= 11.0

    dust_after_second = json.loads(dust_path.read_text(encoding="utf-8"))
    assert dust_after_second["XBTEUR"]["buy"] == 0.0

    events = [
        json.loads(line)
        for line in (run_dir / "audit.log").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(row.get("event_type") == "dust_accumulate" for row in events)
    assert any(
        row.get("event_type") == "live_exec"
        and row.get("payload", {}).get("status") == "skipped"
        and row.get("payload", {}).get("reason") == "dust_accumulate"
        for row in events
    )
    assert any(row.get("event_type") == "dust_release" for row in events)


def test_exit_take_profit_pct_forces_immediate_sell(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_EXIT_TAKE_PROFIT_PCT", "5")
    monkeypatch.setenv("AUTONOMOUS_EXIT_TAKE_PROFIT_FULL_CLOSE", "true")
    monkeypatch.setenv("AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", "0.1")
    monkeypatch.setenv("AUTONOMOUS_REBALANCE_DEADZONE_FACTOR", "0")
    monkeypatch.setenv("AUTONOMOUS_REBALANCE_DEADZONE_FLOOR", "0")
    run_dir = tmp_path / "run_tp"
    orc = RobotOrchestrator(_settings(str(run_dir)))

    class _ProfitLive(_FakeLive):
        def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
            now = time.time()
            bid = 105.0
            ask = 105.2
            return {
                "pair": symbol,
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
                "spread_bps": ((ask - bid) / ((ask + bid) / 2.0)) * 10000.0,
                "depth_notional": 500_000.0,
                "ts": now,
                "stale": False,
                "level": "L2",
                "source": "ws",
            }

        def sync_fill_ledger(self, pair: str, mark_price: float):  # noqa: ARG002
            return {
                "pair": pair,
                "position_notional_signed": 105.0,
                "exposure_notional": 105.0,
                "avg_entry_price": 100.0,
                "net_pnl_after_fees_quote": 5.0,
                "fees_quote": 0.0,
                "filled_notional_quote": 105.0,
                "min_trade_notional_quote": 1.0,
                "execution_qa": {
                    "implementation_shortfall_bps": 0.0,
                    "latency_p50_ms": 1.0,
                    "latency_p95_ms": 2.0,
                    "fill_probability": 0.9,
                    "orders_filled": 0.0,
                },
            }

    live = _ProfitLive()
    execute_calls: list[OrderIntent] = []

    def _exec(intent):
        execute_calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional, "side": intent.side})

    def _risk(*args, **kwargs):
        intent = kwargs.get("intent")
        notional = float(getattr(intent, "target_notional", 0.0))
        return RiskDecision(True, "passed", adjusted_notional=notional, details={})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = _risk  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = (  # type: ignore[method-assign]
        lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)
    )
    orc.policy.make_intent = lambda *_args, **_kwargs: OrderIntent("XBTEUR", "buy", 2.0, {"components": []})  # type: ignore[method-assign]

    out = orc._live_loop(live, symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(execute_calls) == 1
    assert execute_calls[0].side == "sell"
    assert float(execute_calls[0].target_notional) >= 105.0

    events = [
        json.loads(line)
        for line in (run_dir / "audit.log").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        row.get("event_type") == "exit_manager"
        and row.get("payload", {}).get("reason") == "take_profit_target"
        for row in events
    )


def test_orchestrator_profit_lock_skips_sell_before_execution(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "500")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", "false")
    run_dir = tmp_path / "run_profit_lock_orchestrator"
    orc = RobotOrchestrator(_settings(str(run_dir)))

    class _UnderwaterSellLive(_FakeLive):
        def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
            now = time.time()
            bid = 101.0
            ask = 101.2
            return {
                "pair": symbol,
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
                "spread_bps": ((ask - bid) / ((ask + bid) / 2.0)) * 10000.0,
                "depth_notional": 500_000.0,
                "ts": now,
                "stale": False,
                "level": "L2",
                "source": "ws",
            }

        def sync_fill_ledger(self, pair: str, mark_price: float):  # noqa: ARG002
            return {
                "pair": pair,
                "position_notional_signed": 105.0,
                "position_qty": 1.0,
                "exposure_notional": 105.0,
                "avg_entry_price": 100.0,
                "net_pnl_after_fees_quote": 1.0,
                "fees_quote": 0.0,
                "filled_notional_quote": 105.0,
                "min_trade_notional_quote": 0.5,
                "execution_qa": {
                    "implementation_shortfall_bps": 0.0,
                    "latency_p50_ms": 1.0,
                    "latency_p95_ms": 2.0,
                    "fill_probability": 0.9,
                    "orders_filled": 0.0,
                },
            }

    live = _UnderwaterSellLive()
    execute_calls: list[OrderIntent] = []

    def _exec(intent):
        execute_calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional, "side": intent.side})

    def _risk(*args, **kwargs):
        intent = kwargs.get("intent")
        notional = float(getattr(intent, "target_notional", 0.0))
        return RiskDecision(True, "passed", adjusted_notional=notional, details={})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = _risk  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = (  # type: ignore[method-assign]
        lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)
    )
    orc.policy.make_intent = lambda *_args, **_kwargs: OrderIntent("XBTEUR", "sell", 2.0, {"components": []})  # type: ignore[method-assign]

    out = orc._live_loop(live, symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert execute_calls == []

    events = [
        json.loads(line)
        for line in (run_dir / "audit.log").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        row.get("event_type") == "live_exec"
        and row.get("payload", {}).get("status") == "skipped"
        and row.get("payload", {}).get("reason") == "profit_lock_sell_below_entry"
        for row in events
    )


def test_orchestrator_profit_lock_relaxes_to_min_after_hold_window(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "200")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS", "500")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S", "90")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", "false")
    run_dir = tmp_path / "run_profit_lock_relaxed_orchestrator"
    orc = RobotOrchestrator(_settings(str(run_dir)))

    class _HeldSellLive(_FakeLive):
        def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
            now = time.time()
            bid = 103.0
            ask = 103.2
            return {
                "pair": symbol,
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
                "spread_bps": ((ask - bid) / ((ask + bid) / 2.0)) * 10000.0,
                "depth_notional": 500_000.0,
                "ts": now,
                "stale": False,
                "level": "L2",
                "source": "ws",
            }

        def sync_fill_ledger(self, pair: str, mark_price: float):  # noqa: ARG002
            return {
                "pair": pair,
                "position_notional_signed": 103.0,
                "position_qty": 1.0,
                "exposure_notional": 103.0,
                "avg_entry_price": 100.0,
                "position_age_s": 120.0,
                "net_pnl_after_fees_quote": 3.0,
                "fees_quote": 0.0,
                "filled_notional_quote": 103.0,
                "min_trade_notional_quote": 0.5,
                "execution_qa": {
                    "implementation_shortfall_bps": 0.0,
                    "latency_p50_ms": 1.0,
                    "latency_p95_ms": 2.0,
                    "fill_probability": 0.9,
                    "orders_filled": 0.0,
                },
            }

    live = _HeldSellLive()
    execute_calls: list[OrderIntent] = []

    def _exec(intent):
        execute_calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional, "side": intent.side})

    def _risk(*args, **kwargs):
        intent = kwargs.get("intent")
        notional = float(getattr(intent, "target_notional", 0.0))
        return RiskDecision(True, "passed", adjusted_notional=notional, details={})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = _risk  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = (  # type: ignore[method-assign]
        lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)
    )
    orc.policy.make_intent = lambda *_args, **_kwargs: OrderIntent("XBTEUR", "sell", 2.0, {"components": []})  # type: ignore[method-assign]

    out = orc._live_loop(live, symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(execute_calls) == 1
    assert execute_calls[0].side == "sell"
