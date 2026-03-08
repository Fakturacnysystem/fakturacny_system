from __future__ import annotations

from dataclasses import dataclass
import time

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


@dataclass
class _ExecResult:
    status: str
    reason: str
    order: dict | None = None


class _FakeLive:
    killed = False
    kill_reason = ""

    def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
        now = time.time()
        return {
            "pair": symbol,
            "bid": 98.0,
            "ask": 98.2,
            "mid": 98.1,
            "spread_bps": 20.40,
            "depth_notional": 500000.0,
            "ts": now,
            "stale": False,
            "level": "L2",
            "source": "ws",
        }

    def sync_fill_ledger(self, pair: str, mark_price: float):  # noqa: ARG002
        return {
            "pair": pair,
            "position_notional_signed": 100.0,
            "exposure_notional": 100.0,
            "net_pnl_after_fees_quote": -2.0,
            "fees_quote": 0.0,
            "filled_notional_quote": 100.0,
            "min_trade_notional_quote": 0.25,
            "avg_entry_price": 100.0,
            "position_qty": 1.0,
            "position_age_s": 120.0,
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
        return "ZEUR", 1000.0


def test_freeze_buy_underwater_blocks_new_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "1")
    monkeypatch.setenv("AUTONOMOUS_LIVE_POLL_SECONDS", "0.5")
    monkeypatch.setenv("AUTONOMOUS_PORTFOLIO_OPTIMIZER", "false")
    monkeypatch.setenv("AUTONOMOUS_GUARDS_MODE", "fatal_only")
    monkeypatch.setenv("AUTONOMOUS_FREEZE_BUY_WHEN_UNREALIZED_PCT", "-1.0")
    monkeypatch.setenv("AUTONOMOUS_FREEZE_BUY_COOLDOWN_S", "600")
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")

    orc = RobotOrchestrator(_settings(str(tmp_path / "run")))
    calls = {"n": 0}

    def _exec(_intent):
        calls["n"] += 1
        return _ExecResult(status="submitted", reason="should_not_happen")

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *a, **k: RiskDecision(True, "passed", adjusted_notional=25.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **k: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]
    orc.policy.make_intent = lambda *_args, **_kwargs: OrderIntent("XBTEUR", "buy", 25.0, {"components": []})  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert calls["n"] == 0
    audit = (tmp_path / "run" / "audit.log").read_text(encoding="utf-8")
    assert "freeze_buy_underwater" in audit

