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

    def __init__(self) -> None:
        self._bid = 100.0
        self._ask = 100.2

    def market_snapshot(self, symbol: str, max_age_s: float = 1.0):  # noqa: ARG002
        now = time.time()
        return {
            "pair": symbol,
            "bid": self._bid,
            "ask": self._ask,
            "mid": (self._bid + self._ask) / 2.0,
            "spread_bps": ((self._ask - self._bid) / ((self._ask + self._bid) / 2.0)) * 10000.0,
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
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")


def _force_intent(orc: RobotOrchestrator):
    def _intent(_fc, _features, _fee, _slip):
        return OrderIntent(
            symbol="XBTEUR",
            side="buy",
            target_notional=25.0,
            why={
                "components": [
                    {
                        "strategy": "unit",
                        "weight": 1.0,
                        "final_edge_bps": 35.0,
                        "cost_total_bps": 2.0,
                    }
                ]
            },
        )

    orc.policy.make_intent = _intent  # type: ignore[method-assign]


def test_risk_reject_is_warn_only_in_fatal_only_mode(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    orc = RobotOrchestrator(_settings(str(tmp_path / "run1")))
    _force_intent(orc)

    calls = []

    def _exec(intent):
        calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(False, "drawdown_safe_mode", adjusted_notional=0.0, flatten=True, details={"dd": 12.0})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {})  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(calls) == 1

    audit = (tmp_path / "run1" / "audit.log").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in audit if x.strip()]
    assert any(r.get("event_type") == "risk_reject" and r.get("payload", {}).get("overridden_by_fatal_only") is True for r in rows)
    assert any(r.get("event_type") == "policy_violation_warn" and r.get("payload", {}).get("kind") == "risk" for r in rows)


def test_governance_block_becomes_warn_only_in_fatal_only_mode(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    orc = RobotOrchestrator(_settings(str(tmp_path / "run2")))
    _force_intent(orc)

    calls = []

    def _exec(intent):
        calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(True, "passed", adjusted_notional=20.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(False, "mandate_notional_limit", {"max_notional": 5.0}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(calls) == 1

    audit = (tmp_path / "run2" / "audit.log").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in audit if x.strip()]
    assert any(r.get("event_type") == "governance_reject" for r in rows)
    assert any(r.get("event_type") == "policy_violation_warn" and r.get("payload", {}).get("kind") == "governance" for r in rows)


def test_modeled_execution_kpis_non_zero_without_fills(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    orc = RobotOrchestrator(_settings(str(tmp_path / "run3")))
    _force_intent(orc)

    def _exec(intent):
        return _ExecResult(status="submitted", reason="accepted_no_fill", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(True, "passed", adjusted_notional=20.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert float(orc.ops.metrics.get("intents_total", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("executions_attempted_total", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("executions_submitted_total", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("fills_confirmed_total", 0.0)) == 0.0
    assert float(orc.ops.metrics.get("expected_total_cost_bps", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("expected_net_edge_bps", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("expected_fill_prob", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("cost_to_alpha_ratio_modeled", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("fill_rate", 1.0)) == 0.0
    assert orc.ops.metrics.get("slippage_vs_model_bps") is None


def test_self_tuner_scales_down_on_insufficient_balance(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_SELF_TUNER_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_SELF_TUNER_WINDOW_EVENTS", "50")
    monkeypatch.setenv("AUTONOMOUS_SELF_TUNER_MIN_SAMPLES", "1")
    monkeypatch.setenv("AUTONOMOUS_SELF_TUNER_EVERY_STEPS", "1")

    orc = RobotOrchestrator(_settings(str(tmp_path / "run4")))
    _force_intent(orc)

    def _exec(_intent):
        return _ExecResult(status="blocked", reason="insufficient_balance_block", order=None)

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(True, "passed", adjusted_notional=20.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert float(orc.ops.metrics.get("self_tuner_insufficient_rate", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("self_tuner_size_scale", 1.0)) < 1.0


def test_exchange_invalid_blocks_do_not_count_as_trade_attempt(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    orc = RobotOrchestrator(_settings(str(tmp_path / "run5")))
    _force_intent(orc)

    def _exec(_intent):
        return _ExecResult(status="blocked", reason="min_order_block", order=None)

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(True, "passed", adjusted_notional=20.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert float(orc.ops.metrics.get("intents_total", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("executions_attempted_total", 0.0)) == 0.0


def test_rate_limit_cooldown_blocks_do_not_count_as_trade_attempt(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    orc = RobotOrchestrator(_settings(str(tmp_path / "run5b")))
    _force_intent(orc)

    def _exec(_intent):
        return _ExecResult(status="blocked", reason="rate_limit_cooldown", order=None)

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(True, "passed", adjusted_notional=20.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert float(orc.ops.metrics.get("intents_total", 0.0)) > 0.0
    assert float(orc.ops.metrics.get("executions_attempted_total", 0.0)) == 0.0
    assert float(orc.ops.metrics.get("orders_rejected_total", 0.0)) == 0.0
    assert float(orc.ops.metrics.get("reject_rate", 0.0)) == 0.0


def test_entry_safe_mode_override(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_GUARDS_MODE", "strict")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_SAFE_MODE", "0")
    orc = RobotOrchestrator(_settings(str(tmp_path / "run6")))
    _force_intent(orc)

    calls = []

    def _exec(intent):
        calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(False, "safe_mode_default", adjusted_notional=0.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(calls) == 1
    assert float(orc.ops.metrics.get("safe_mode_entry_overridden_total", 0.0)) >= 1.0

    rows = [
        json.loads(x)
        for x in (tmp_path / "run6" / "audit.log").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    assert any(
        r.get("event_type") == "policy_violation_warn"
        and r.get("payload", {}).get("overridden_by") == "entry_safe_mode"
        for r in rows
    )


def test_volstop_throttle_scales_notional_and_sets_cooldown(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_GUARDS_MODE", "strict")
    monkeypatch.setenv("AUTONOMOUS_MODE_LABEL", "growth")
    monkeypatch.setenv("AUTONOMOUS_VOLSTOP_THROTTLE_SCALE", "0.3")
    monkeypatch.setenv("AUTONOMOUS_VOLSTOP_COOLDOWN_S", "30")
    orc = RobotOrchestrator(_settings(str(tmp_path / "run7")))
    _force_intent(orc)

    calls = []

    def _exec(intent):
        calls.append(intent)
        return _ExecResult(status="submitted", reason="ok", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *args, **kwargs: RiskDecision(False, "cooldown_active", adjusted_notional=0.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **kwargs: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(calls) == 1
    assert 0.0 < float(calls[0].target_notional) < 25.0

    rows = [
        json.loads(x)
        for x in (tmp_path / "run7" / "audit.log").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    assert any(
        r.get("event_type") == "policy_violation_warn"
        and r.get("payload", {}).get("overridden_by") == "growth_volstop_throttle"
        for r in rows
    )


def test_scheduler_probe_submits_when_no_intent_for_interval(tmp_path, monkeypatch):
    _configure_env(monkeypatch)
    monkeypatch.setenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "3")
    monkeypatch.setenv("AUTONOMOUS_LIVE_POLL_SECONDS", "0.6")
    monkeypatch.setenv("ORDER_SUBMISSION_INTERVAL_SECONDS", "1")
    orc = RobotOrchestrator(_settings(str(tmp_path / "run8")))

    calls = []

    def _exec(intent):
        calls.append(intent)
        return _ExecResult(status="submitted", reason="scheduler_probe_ok", order={"notional": intent.target_notional})

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.policy.make_intent = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert len(calls) >= 1
    assert float(orc.ops.metrics.get("submissions_per_minute", 0.0)) >= 1.0

    rows = [
        json.loads(x)
        for x in (tmp_path / "run8" / "audit.log").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    assert any(r.get("event_type") == "scheduler_probe" for r in rows)
