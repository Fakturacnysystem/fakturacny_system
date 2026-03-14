from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.core.orchestrator import RobotOrchestrator


def _orchestrator_stub() -> RobotOrchestrator:
    # Avoid full orchestrator boot; this helper method is pure env-driven logic.
    return object.__new__(RobotOrchestrator)


def test_universe_allowlist_uses_fallback_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("AUTONOMOUS_UNIVERSE_ALLOWLIST", raising=False)
    monkeypatch.setenv("AUTONOMOUS_FALLBACK_SYMBOLS", "btcusd,ethusd")
    orch = _orchestrator_stub()
    assert orch._universe_allowlist() == {"BTCUSD", "ETHUSD"}


def test_universe_allowlist_explicit_empty_disables_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_UNIVERSE_ALLOWLIST", "")
    monkeypatch.setenv("AUTONOMOUS_FALLBACK_SYMBOLS", "btcusd,ethusd")
    orch = _orchestrator_stub()
    assert orch._universe_allowlist() is None


def test_universe_allowlist_explicit_values_override_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_UNIVERSE_ALLOWLIST", "adausd")
    monkeypatch.setenv("AUTONOMOUS_FALLBACK_SYMBOLS", "btcusd,ethusd")
    orch = _orchestrator_stub()
    assert orch._universe_allowlist() == {"ADAUSD"}


def test_allowlist_recovery_uses_operator_override_intersection() -> None:
    orch = _orchestrator_stub()
    recovered = orch._recover_allowlist_with_operator_override(
        allowlist={"ATOMUSD", "SOLUSD"},
        operator_override=["SOLUSD", "ADAUSD", "SOLUSD", ""],
    )
    assert recovered == ["SOLUSD"]


def test_allowlist_recovery_returns_empty_without_overlap() -> None:
    orch = _orchestrator_stub()
    recovered = orch._recover_allowlist_with_operator_override(
        allowlist={"XBTUSD"},
        operator_override=["SOLUSD", "ADAUSD"],
    )
    assert recovered == []


class _OpsStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.metrics: dict[str, float] = {}

    def audit_event(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((str(event_type), dict(payload)))

    def set_metric(self, name: str, value: float) -> None:
        self.metrics[str(name)] = float(value)

    def inc_metric(self, name: str, value: float = 1.0) -> None:
        key = str(name)
        self.metrics[key] = float(self.metrics.get(key, 0.0)) + float(value)


class _EventStoreStub:
    def __init__(self) -> None:
        self.rows: list[tuple[str, object]] = []

    def append(self, stream: str, event: object) -> None:
        self.rows.append((str(stream), event))


def _shadow_stub(tmp_path, *, enabled: bool = True, fail_open: bool = True) -> RobotOrchestrator:
    orch = object.__new__(RobotOrchestrator)
    orch.ops = _OpsStub()
    orch._record_module_event = lambda **_: None
    orch.settings = SimpleNamespace(storage=SimpleNamespace(run_dir=str(tmp_path)))
    orch._universe_shadow_enabled = bool(enabled)
    orch._universe_shadow_fail_open = bool(fail_open)
    orch._universe_shadow_every_n_steps = 1
    orch._universe_shadow_run_dir = str(tmp_path / "universe_shadow")
    orch._universe_shadow_mind = None
    orch._universe_shadow_last_packet_id = ""
    orch._universe_shadow_last_error = ""
    return orch


def _shadow_context() -> dict[str, object]:
    return {
        "symbol": "XBTUSD",
        "market_class": "crypto_spot",
        "mid": 100.0,
        "spread_bps": 8.0,
        "depth_notional": 8000.0,
        "features": {"realized_vol": 0.004},
        "market_watch": {"trend_2m_bps": 15.0, "realized_vol_2m": 0.004, "confidence": 0.7},
        "quote_free": 1000.0,
        "position_notional_quote": 0.0,
        "signed_exposure_notional_quote": 0.0,
        "drawdown_pct": 0.01,
        "latency_ms": 45.0,
        "forecast_confidence": 0.62,
        "forecast_sigma": 8.0,
    }


def test_universe_shadow_adapter_disabled_is_noop(tmp_path) -> None:
    orch = _shadow_stub(tmp_path, enabled=False)
    diag = orch._emit_universe_shadow_cycle(
        step=1,
        venue="kraken_spot",
        intent=None,
        context_payload=_shadow_context(),
    )
    assert diag["enabled"] is False
    assert diag["emitted"] is False
    assert diag["packet_id"] == ""


def test_universe_shadow_adapter_emits_packet_for_flat_intent(tmp_path) -> None:
    orch = _shadow_stub(tmp_path, enabled=True)
    diag = orch._emit_universe_shadow_cycle(
        step=1,
        venue="kraken_spot",
        intent=None,
        context_payload=_shadow_context(),
    )
    assert diag["enabled"] is True
    assert diag["emitted"] is True
    assert str(diag["packet_id"])
    assert orch._universe_shadow_last_packet_id == diag["packet_id"]
    assert any(event == "universe_shadow_cycle" for event, _ in orch.ops.events)


def test_universe_shadow_adapter_emits_mission_bridge_diagnostics(tmp_path) -> None:
    class _MissionMind:
        def ingest_decision_context(self, *args, **kwargs) -> None:
            _ = (args, kwargs)

        def run_cycle_from_intent(self, *args, **kwargs):
            _ = (args, kwargs)
            return SimpleNamespace(
                decision_packet=SimpleNamespace(
                    cycle_id="cycle-42",
                    selected_strategy="guardian",
                    mission={
                        "mission": "observation_only",
                        "reason_codes": ["observe_only_guard", "risk_off_posture"],
                        "no_trade_preferred": True,
                        "allow_new_risk": False,
                        "execution_posture_hint": "passive",
                    },
                ),
                execution_plan=SimpleNamespace(
                    instrument="XBTUSD",
                    side="buy",
                    actionable=False,
                    target_notional_quote=0.0,
                    order_type="none",
                    maker_taker="none",
                    urgency_tier="low",
                    max_slippage_bps=0.0,
                    expected_net_edge_bps=-1.5,
                    meta={
                        "execution_advisory": {
                            "severity": "critical",
                            "reason_codes": ["no_net_edge_after_costs"],
                            "requires_manual_review": True,
                        },
                        "execution_intelligence": {
                            "abort": {
                                "should_abort": True,
                                "reason_codes": ["no_net_edge_after_costs"],
                            }
                        },
                    },
                ),
                shield=SimpleNamespace(
                    mode="observe_only",
                    reason_codes=["confidence_collapse", "execution_stress_rising"],
                    no_trade_forced=True,
                    hard_stop_forced=False,
                ),
            )

    orch = _shadow_stub(tmp_path, enabled=True)
    orch._universe_shadow_mind = _MissionMind()

    diag = orch._emit_universe_shadow_cycle(
        step=1,
        venue="kraken_spot",
        intent=None,
        context_payload=_shadow_context(),
    )

    assert diag["emitted"] is True
    assert diag["mission"] == "observation_only"
    assert diag["mission_reason_codes"] == ["observe_only_guard", "risk_off_posture"]
    assert diag["mission_no_trade_preferred"] is True
    assert diag["mission_allow_new_risk"] is False
    assert diag["mission_execution_posture_hint"] == "passive"
    assert diag["execution_plan_abort"] is True
    assert diag["execution_plan_advisory_severity"] == "critical"
    assert diag["execution_plan_contract"]["expected_net_edge_bps"] == -1.5
    assert diag["shield_mode"] == "observe_only"
    assert diag["shield_reason_codes"] == ["confidence_collapse", "execution_stress_rising"]
    assert diag["shield_no_trade_forced"] is True
    assert diag["shield_hard_stop_forced"] is False

    shadow_event_payloads = [payload for event, payload in orch.ops.events if event == "universe_shadow_cycle"]
    assert shadow_event_payloads
    assert shadow_event_payloads[-1]["mission_reason_codes"] == ["observe_only_guard", "risk_off_posture"]


def test_universe_shadow_adapter_fail_open_on_cycle_error(tmp_path) -> None:
    class _BrokenMind:
        def ingest_decision_context(self, *args, **kwargs) -> None:
            return None

        def run_cycle_from_intent(self, *args, **kwargs):
            raise RuntimeError("boom")

    orch = _shadow_stub(tmp_path, enabled=True, fail_open=True)
    orch._universe_shadow_mind = _BrokenMind()
    diag = orch._emit_universe_shadow_cycle(
        step=1,
        venue="kraken_spot",
        intent=None,
        context_payload=_shadow_context(),
    )
    assert diag["enabled"] is True
    assert diag["emitted"] is False
    assert "shadow_cycle_failed:boom" in str(diag["error"])


def test_world_state_read_view_fallback_when_adapter_unavailable(tmp_path) -> None:
    orch = _shadow_stub(tmp_path, enabled=False)
    orch._world_state_read_adapter = None
    view = orch._world_state_read_view(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        market_data_stale_s=1.5,
        ws_healthy=True,
        drawdown_pct=0.1,
        regime="TREND",
        market_class="crypto_spot",
    )
    assert view["world_state_available"] is False
    assert view["graph_available"] is False
    assert view["safe_to_trade"] is False
    assert "market_state" in view["stale_critical_domains"]
    assert "freshness_s" in view


def test_event_adapter_mirrors_legacy_event_without_breaking_event_store() -> None:
    orch = _orchestrator_stub()
    orch.event_store = _EventStoreStub()
    orch.ops = _OpsStub()
    module_events: list[dict[str, object]] = []
    orch._record_module_event = lambda **kwargs: module_events.append(dict(kwargs))
    orch._universe_event_adapter_enabled = True
    orch._universe_event_adapter_fail_open = True
    orch._universe_event_adapter_last_error = ""

    mirrored: list[tuple[object, str, dict[str, object]]] = []

    class _FabricStub:
        def ingest_legacy_event(self, event: object, *, source: str, metadata: dict[str, object] | None = None):
            mirrored.append((event, str(source), dict(metadata or {})))
            return {"ok": True}

    orch._ensure_universe_event_adapter_fabric = lambda: _FabricStub()

    legacy_event = SimpleNamespace(
        event_type="OrderIntentEvent",
        symbol="XBTUSD",
        checksum="chk-1",
        payload={"target_notional": 12.0},
    )
    orch._append_legacy_event_and_mirror(
        stream="orders",
        event=legacy_event,
        adapter_source="unit_test_phase12",
    )

    assert orch.event_store.rows == [("orders", legacy_event)]
    assert len(mirrored) == 1
    assert mirrored[0][1] == "unit_test_phase12"
    assert mirrored[0][2]["legacy_stream"] == "orders"
    assert mirrored[0][2]["authority_path"] == "legacy_orchestrator"
    assert orch.ops.metrics["universe_event_adapter_last_publish_ok"] == 1.0
    assert orch.ops.metrics["universe_event_adapter_published_total"] == 1.0
    assert module_events and module_events[0]["module"] == "universe_event_adapter"
    assert module_events[0]["reason"] == "ok"


def test_event_adapter_fail_open_records_error_and_preserves_legacy_append() -> None:
    orch = _orchestrator_stub()
    orch.event_store = _EventStoreStub()
    orch.ops = _OpsStub()
    orch._record_module_event = lambda **_: None
    orch._universe_event_adapter_enabled = True
    orch._universe_event_adapter_fail_open = True
    orch._universe_event_adapter_last_error = ""

    class _BrokenFabric:
        def ingest_legacy_event(self, event: object, *, source: str, metadata: dict[str, object] | None = None):
            _ = (event, source, metadata)
            raise RuntimeError("adapter_boom")

    orch._ensure_universe_event_adapter_fabric = lambda: _BrokenFabric()

    legacy_event = SimpleNamespace(event_type="RiskEvent", symbol="XBTUSD", checksum="chk-2", payload={"reason": "x"})
    orch._append_legacy_event_and_mirror(
        stream="risk",
        event=legacy_event,
        adapter_source="unit_test_phase12",
    )

    assert orch.event_store.rows == [("risk", legacy_event)]
    assert orch.ops.metrics["universe_event_adapter_last_publish_ok"] == 0.0
    assert "event_adapter_publish_failed:adapter_boom" in str(orch._universe_event_adapter_last_error)
    assert any(name == "universe_event_adapter_error" for name, _ in orch.ops.events)
