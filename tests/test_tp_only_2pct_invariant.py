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
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.governance.service import GovernanceDecision
from autonomous_investment_robot.services.risk_engine.service import RiskDecision


class _FakeConnector:
    def __init__(self) -> None:
        self.bid = 101.0
        self.ask = 101.2
        self._balance = {"ZEUR": "1000.0", "XXBT": "0.01"}
        self.add_calls = 0

    @property
    def has_credentials(self):  # noqa: D401
        return True

    def verify_live_permissions(self):
        return True, "ok"

    def asset_pairs(self):
        return {
            "XBTEUR": {
                "ordermin": "0.0001",
                "pair_decimals": 2,
                "lot_decimals": 8,
                "base": "XXBT",
                "quote": "ZEUR",
                "ordertype": ["limit", "market"],
            }
        }

    def ticker(self, pair=None):  # noqa: ARG002
        return {"XBTEUR": {"a": [str(self.ask), "1.0"], "b": [str(self.bid), "1.0"], "v": ["0", "1000"]}}

    def balance(self):
        return dict(self._balance)

    def add_order(self, params):
        self.add_calls += 1
        return {"txid": [f"T{self.add_calls}"], "descr": {"order": str(params)}}

    def open_orders(self):
        return {"open": {}}

    def cancel_order(self, txid):  # noqa: ARG002
        return {"count": 1}

    def cancel_all(self):
        return {"count": 0}

    def query_orders(self, txid):  # noqa: ARG002
        return {}

    def trades_history(self, start=None):  # noqa: ARG002
        return {}

    def trade_volume(self, pair=None, fee_info=True):  # noqa: ARG002
        return {"fees": {"XBTEUR": {"fee": "0.26"}}}


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


def test_execution_layer_blocks_sell_below_two_percent(monkeypatch, tmp_path):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_TP_ONLY_MODE", "1")
    monkeypatch.setenv("AUTONOMOUS_MIN_TAKE_PROFIT_PCT", "2.0")
    fake = _FakeConnector()
    svc = LiveKrakenSpotService(_settings(str(tmp_path / "run_exec")), run_id="r", connector=fake)
    ledger = svc._ledger_for("XBTEUR")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 100.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    ledger.position_open_ts = time.time() - 300.0

    fake.bid = 101.0
    fake.ask = 101.2
    out = svc.execute_intent(OrderIntent(symbol="XBTEUR", side="sell", target_notional=1.0, why={}))
    assert out.status in {"skipped", "blocked"}
    assert out.reason == "profit_lock_sell_below_entry"
    assert fake.add_calls == 0


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
            "bid": 101.0,
            "ask": 101.2,
            "mid": 101.1,
            "spread_bps": 19.78,
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
            "net_pnl_after_fees_quote": 1.0,
            "fees_quote": 0.0,
            "filled_notional_quote": 100.0,
            "min_trade_notional_quote": 0.25,
            "avg_entry_price": 100.0,
            "position_qty": 1.0,
            "position_age_s": 300.0,
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


def test_orchestrator_blocks_sell_when_tp_not_met(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "1")
    monkeypatch.setenv("AUTONOMOUS_LIVE_POLL_SECONDS", "0.5")
    monkeypatch.setenv("AUTONOMOUS_PORTFOLIO_OPTIMIZER", "false")
    monkeypatch.setenv("AUTONOMOUS_GUARDS_MODE", "fatal_only")
    monkeypatch.setenv("AUTONOMOUS_TP_ONLY_MODE", "1")
    monkeypatch.setenv("AUTONOMOUS_MIN_TAKE_PROFIT_PCT", "2.0")
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    orc = RobotOrchestrator(_settings(str(tmp_path / "run_orc")))

    called = {"n": 0}

    def _exec(_intent):
        called["n"] += 1
        return _ExecResult(status="submitted", reason="should_not_happen")

    orc.execution.execute_live = _exec  # type: ignore[method-assign]
    orc.risk.evaluate = lambda *a, **k: RiskDecision(True, "passed", adjusted_notional=50.0, details={})  # type: ignore[method-assign]
    orc.governance.enforce_policy_constraints = lambda **k: GovernanceDecision(True, "ok", {}, fatal=False)  # type: ignore[method-assign]
    orc.policy.make_intent = lambda *_args, **_kwargs: OrderIntent("XBTEUR", "sell", 50.0, {"components": []})  # type: ignore[method-assign]

    out = orc._live_loop(_FakeLive(), symbol="XBTEUR", mode=orc.settings.execution_mode_enum())
    assert out["status"] == "ok"
    assert called["n"] == 0
    audit_text = (tmp_path / "run_orc" / "audit.log").read_text(encoding="utf-8")
    assert "profit_lock_sell_below_min_profit" in audit_text or "tp_ladder_block" in audit_text

