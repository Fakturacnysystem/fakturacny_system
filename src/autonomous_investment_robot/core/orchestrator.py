from __future__ import annotations

from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time
from types import SimpleNamespace

from autonomous_investment_robot.backtest.harness import run_walk_forward_oos
from autonomous_investment_robot.core.order_scheduler import OrderSubmissionScheduler
from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings, UNSPECIFIED
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector
from autonomous_investment_robot.connectors.cex.kraken_futures import KrakenFuturesConnector, KrakenFuturesSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector
from autonomous_investment_robot.reporting.metrics import sharpe, sortino
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.data_ingestion.multi_venue_engine import MultiVenueMarketDataEngine, VenueQuote
from autonomous_investment_robot.services.data_qa.service import DataQAService
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.execution.live_kraken_futures_service import LiveKrakenFuturesService
from autonomous_investment_robot.services.execution.live_kraken_router_service import LiveKrakenRouterService
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.execution.hybrid_mode import parse_hybrid_symbols, symbol_live_in_hybrid
from autonomous_investment_robot.services.execution.order_churn_controller import OrderChurnController
from autonomous_investment_robot.services.execution.rate_limit_governor import RateLimitGovernor
from autonomous_investment_robot.services.execution.slippage_calibrator import SlippageCalibrator
from autonomous_investment_robot.services.execution.smart_router import SmartOrderRouter, VenueCandidate
from autonomous_investment_robot.services.execution.cost_engine import CostEngineService
from autonomous_investment_robot.services.fees.fee_profile import FeeProfileService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService, FeatureVector
from autonomous_investment_robot.services.governance.service import GovernanceService
from autonomous_investment_robot.services.incident.service import IncidentPolicy, Notifier
from autonomous_investment_robot.services.marketdata.ws_integrity import WSDataIntegrityGuard
from autonomous_investment_robot.services.mlops.service import MLOpsService
from autonomous_investment_robot.services.market_microstructure import ToxicityScorer
from autonomous_investment_robot.services.market_discovery import KrakenMarketDiscoveryService
from autonomous_investment_robot.services.models.service import Forecast, ModelsService
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.portfolio.optimizer import PortfolioOptimizerService
from autonomous_investment_robot.services.policy.service import OrderIntent, PolicyService
from autonomous_investment_robot.services.policy.universe_builder import KrakenSpotUniverseBuilder
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.reliability.bus import ReliabilityBus
from autonomous_investment_robot.services.reliability.health_audit_110 import HealthAudit110
from autonomous_investment_robot.services.research.service import ResearchPlatformService
from autonomous_investment_robot.services.research.online_validator import OnlineSignalValidator
from autonomous_investment_robot.services.replay.events import ComplianceEvent, FillEvent, OrderEvent, OrderIntentEvent, PositionEvent, RiskEvent, make_event, make_idempotency_key
from autonomous_investment_robot.services.risk import CapitalUnlockManager, HedgeManager, StuckPositionGovernor
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService
from autonomous_investment_robot.services.policy.mastermind_policy import MastermindPolicy
from autonomous_investment_robot.services.storage import SQLiteStore
from autonomous_investment_robot.services.treasury.service import TreasuryService
from autonomous_investment_robot.services.multi_account import AccountRouter
from autonomous_investment_robot.services.multi_exchange import ExchangeManager


AGGRESSIVE_HF_PROFILE_DEFAULTS: dict[str, str] = {
    "AUTONOMOUS_SYMBOL_TOPK": "60",
    "AUTONOMOUS_SYMBOL_SCORE_REFRESH_S": "5",
    "AUTONOMOUS_SYMBOL_QUARANTINE_MIN": "5",
    "ORDER_SUBMISSION_INTERVAL_SECONDS": "60",
    "AUTONOMOUS_EXTRA_SUBMISSIONS_ENABLED": "true",
    "AUTONOMOUS_EXTRA_SUBMISSIONS_MAX_PER_MIN": "6",
    "AUTONOMOUS_PROBE_NOTIONAL_QUOTE": "1.50",
    "AUTONOMOUS_PROBE_DISTANCE_TICKS": "1",
    "AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN": "60",
    "AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN": "12",
    "AUTONOMOUS_STUCK_GOVERNOR_ENABLED": "true",
    "AUTONOMOUS_STUCK_AGE_S": "3600",
    "AUTONOMOUS_STUCK_DD_TRIGGER": "-0.012",
    "AUTONOMOUS_STUCK_BLOCKED_SELLS_TRIGGER": "5",
    "AUTONOMOUS_STUCK_ENTRIES_PAUSE_MIN_S": "900",
    "AUTONOMOUS_HEDGE_ENABLED": "true",
    "AUTONOMOUS_HEDGE_MAX_RATIO": "0.80",
    "AUTONOMOUS_HEDGE_STEP_RATIO": "0.20",
    "AUTONOMOUS_HEDGE_DD_STEP": "0.008",
    "AUTONOMOUS_HEDGE_MIN_NOTIONAL": "10.0",
    "AUTONOMOUS_HEDGE_MAX_NOTIONAL_PER_SYMBOL": "200.0",
    "AUTONOMOUS_HEDGE_FUNDING_WINDOW_S": "1200",
    "AUTONOMOUS_ONLINE_VALIDATION_ENABLED": "true",
    "AUTONOMOUS_VALIDATION_WINDOW_TRADES": "200",
    "AUTONOMOUS_VALIDATION_MIN_ALPHA_BPS": "-10",
    "AUTONOMOUS_VALIDATION_MAX_REJECT_RATE": "0.35",
    "AUTONOMOUS_VALIDATION_COOLDOWN_S": "3600",
    "AUTONOMOUS_MASTERMIND_ENABLED": "true",
    "AUTONOMOUS_MASTERMIND_MAX_ENTRY_ORDERS_PER_MIN": "6",
    "AUTONOMOUS_CAPITAL_UNLOCK_ENABLED": "true",
    "AUTONOMOUS_CAPITAL_LOCKED_RATIO_TRIGGER": "0.35",
    "AUTONOMOUS_CAPITAL_MEDIAN_HOLD_S_TRIGGER": "7200",
    "AUTONOMOUS_CAPITAL_STUCK_ENTRY_SCALE": "0.20",
    "AUTONOMOUS_CAPITAL_REDIRECT_TOPK": "30",
}


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        if str(os.getenv("AUTONOMOUS_PROFILE", "") or "").strip().lower() == "aggressive_hf":
            for key, value in AGGRESSIVE_HF_PROFILE_DEFAULTS.items():
                os.environ.setdefault(key, value)
        self.ingestion = DataIngestionService()
        self.qa = DataQAService()
        self.raw = RawStoreService(settings.storage.run_dir)
        self.event_store = EventStore(settings.storage.run_dir)
        self.features = FeatureStoreService()
        self.models = ModelsService(regime_settings=settings.regime)
        self.policy = PolicyService(settings.policy, settings.allocator, settings.tco)
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(settings.execution)
        self.recon = ReconciliationService()
        self.compliance = ComplianceService(settings.provider_whitelist)
        self.oms = OMSService()
        self.ops = OpsService(settings.storage.run_dir)
        self.incidents = IncidentPolicy()
        self.notifier = Notifier()
        self.mlops = MLOpsService(settings.mlops.rollback_dd_threshold_pct, settings.mlops.drift_psi_threshold)
        self.market_data = MultiVenueMarketDataEngine(
            settings.storage.run_dir,
            stale_after_s=max(0.2, float(os.getenv("AUTONOMOUS_FEED_STALE_AFTER_S", "4.0") or "4.0")),
            max_clock_drift_ms=max(1.0, float(os.getenv("AUTONOMOUS_MAX_CLOCK_DRIFT_MS", "500.0") or "500.0")),
        )
        self.research = ResearchPlatformService(settings.storage.run_dir)
        self.portfolio_optimizer = PortfolioOptimizerService()
        self.router = SmartOrderRouter()
        self.cost_engine = CostEngineService()
        self.toxicity = ToxicityScorer(window=max(8, int(os.getenv("AUTONOMOUS_TOXICITY_WINDOW", "32") or "32")))
        self.treasury = TreasuryService(
            reserve_cash_ratio=max(0.0, float(os.getenv("AUTONOMOUS_RESERVE_CASH_RATIO", "0.12") or "0.12")),
            min_margin_buffer=max(0.1, float(os.getenv("AUTONOMOUS_MIN_MARGIN_BUFFER_POLICY", "1.4") or "1.4")),
        )
        self.governance = GovernanceService(
            settings.storage.run_dir,
            jurisdiction=str(os.getenv("AUTONOMOUS_JURISDICTION", "SK") or "SK"),
        )
        self.sqlite = SQLiteStore(settings.storage.run_dir)
        self.discovery = KrakenMarketDiscoveryService(settings.storage.run_dir)
        self.bus = ReliabilityBus(
            settings.storage.run_dir,
            max_attempts=max(1, int(os.getenv("AUTONOMOUS_BUS_MAX_ATTEMPTS", "3") or "3")),
        )
        self._health_path = os.path.join(
            settings.storage.run_dir,
            str(getattr(getattr(settings, "watchdog", None), "heartbeat_file", "health.json") or "health.json"),
        )
        self._watchdog_state_path = os.path.join(
            settings.storage.run_dir,
            str(getattr(getattr(settings, "watchdog", None), "state_file", "watchdog_state.json") or "watchdog_state.json"),
        )
        audit_cfg = getattr(settings, "health_audit_110", None)
        self.health_audit_110 = HealthAudit110(
            run_dir=settings.storage.run_dir,
            interval_s=max(
                60.0,
                float(
                    os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT110_INTERVAL_S",
                        os.getenv(
                            "AUTONOMOUS_HEALTH_AUDIT_INTERVAL_S",
                            str(getattr(audit_cfg, "interval_s", 600.0)),
                        ),
                    )
                    or os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT_INTERVAL_S",
                        str(getattr(audit_cfg, "interval_s", 600.0)),
                    )
                ),
            ),
            health_threshold=max(
                1.0,
                min(
                    100.0,
                    float(
                        os.getenv(
                            "AUTONOMOUS_HEALTH_AUDIT_THRESHOLD",
                            str(getattr(audit_cfg, "health_threshold", 90.0)),
                        )
                        or str(getattr(audit_cfg, "health_threshold", 90.0))
                    ),
                ),
            ),
            stream_stale_after_s=max(
                1.0,
                float(
                    os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT_STREAM_STALE_AFTER_S",
                        str(getattr(audit_cfg, "stream_stale_after_s", 20.0)),
                    )
                    or str(getattr(audit_cfg, "stream_stale_after_s", 20.0))
                ),
            ),
            scheduler_lag_grace_s=max(
                0.0,
                float(
                    os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT_SCHEDULER_GRACE_S",
                        str(getattr(audit_cfg, "scheduler_lag_grace_s", 5.0)),
                    )
                    or str(getattr(audit_cfg, "scheduler_lag_grace_s", 5.0))
                ),
            ),
            watchdog_stall_timeout_s=max(
                1.0,
                float(getattr(getattr(settings, "watchdog", None), "stall_timeout_s", 45.0) or 45.0),
            ),
            max_rate_limit_events_60s=max(
                1.0,
                float(
                    os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT_MAX_RATE_LIMIT_EVENTS_60S",
                        str(getattr(audit_cfg, "max_rate_limit_events_60s", 14.0)),
                    )
                    or str(getattr(audit_cfg, "max_rate_limit_events_60s", 14.0))
                ),
            ),
            heartbeat_file=str(getattr(getattr(settings, "watchdog", None), "heartbeat_file", "health.json") or "health.json"),
            watchdog_state_file=str(getattr(getattr(settings, "watchdog", None), "state_file", "watchdog_state.json") or "watchdog_state.json"),
        )
        self.fee_profile = FeeProfileService(
            default_entry_fee_bps=max(30.0, float(settings.execution.fee_bps)),
            default_exit_fee_bps=max(30.0, float(settings.execution.fee_bps)),
            refresh_interval_s=max(
                60.0,
                float(
                    os.getenv(
                        "AUTONOMOUS_FEE_REFRESH_S",
                        os.getenv("AUTONOMOUS_FEE_REFRESH_INTERVAL_S", "21600"),
                    )
                    or os.getenv("AUTONOMOUS_FEE_REFRESH_INTERVAL_S", "21600")
                ),
            ),
            volume_jump_ratio=max(
                0.0,
                float(os.getenv("AUTONOMOUS_FEE_REFRESH_VOLUME_JUMP_RATIO", "0.25") or "0.25"),
            ),
        )
        self.slippage_calibrator = SlippageCalibrator(
            percentile=max(
                0.5,
                min(
                    0.999,
                    float(os.getenv("AUTONOMOUS_SLIPPAGE_CALIBRATION_PCTL", "0.95") or "0.95"),
                ),
            ),
            min_bps=max(
                0.1,
                float(os.getenv("AUTONOMOUS_SLIPPAGE_CALIBRATION_MIN_BPS", "10.0") or "10.0"),
            ),
            max_bps=max(
                0.1,
                float(os.getenv("AUTONOMOUS_SLIPPAGE_CALIBRATION_MAX_BPS", "60.0") or "60.0"),
            ),
            default_spot_bps=max(
                0.1,
                float(
                    os.getenv(
                        "AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS",
                        str(max(15.0, float(settings.execution.slippage_bps))),
                    )
                    or str(max(15.0, float(settings.execution.slippage_bps)))
                ),
            ),
            default_perps_bps=max(
                0.1,
                float(
                    os.getenv(
                        "AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS",
                        str(max(15.0, float(settings.execution.slippage_bps))),
                    )
                    or str(max(15.0, float(settings.execution.slippage_bps)))
                ),
            ),
            window_size=max(64, int(os.getenv("AUTONOMOUS_SLIPPAGE_CALIBRATION_WINDOW", "2000") or "2000")),
        )
        self.ws_integrity = WSDataIntegrityGuard(
            stale_after_s=max(1.0, float(os.getenv("AUTONOMOUS_FEED_STALE_AFTER_S", "4.0") or "4.0")),
            max_out_of_order=max(1, int(os.getenv("AUTONOMOUS_WS_MAX_OUT_OF_ORDER", "8") or "8")),
            trade_id_cache_size=max(256, int(os.getenv("AUTONOMOUS_WS_TRADE_ID_CACHE", "10000") or "10000")),
        )
        self.rate_limit_governor = RateLimitGovernor(
            window_s=max(10.0, float(os.getenv("AUTONOMOUS_RATE_LIMIT_GOVERNOR_WINDOW_S", "60") or "60")),
            max_rate_limit_events_60s=max(
                1,
                int(os.getenv("AUTONOMOUS_RATE_LIMIT_GOVERNOR_MAX_EVENTS_60S", "12") or "12"),
            ),
            storm_cooldown_s=max(
                10.0,
                float(os.getenv("AUTONOMOUS_RATE_LIMIT_GOVERNOR_STORM_COOLDOWN_S", "120") or "120"),
            ),
            retry_budget_per_endpoint=max(
                1,
                int(os.getenv("AUTONOMOUS_RATE_LIMIT_GOVERNOR_RETRY_BUDGET", "2") or "2"),
            ),
        )
        self.order_churn_controller = OrderChurnController()
        self.stuck_governor = StuckPositionGovernor()
        self.hedge_manager = HedgeManager()
        self.capital_unlock_manager = CapitalUnlockManager()
        self.online_validator = OnlineSignalValidator()
        self.mastermind = MastermindPolicy()
        self.hybrid_live_symbols = parse_hybrid_symbols()
        self.hybrid_mode_enabled = len(self.hybrid_live_symbols) > 0
        self.account_router = AccountRouter()
        self.exchange_manager = ExchangeManager()
        self.exchange_status = self.exchange_manager.initialize()
        self._last_fee_profile_updated_ts = 0.0
        for venue, status in self.exchange_status.items():
            try:
                self.sqlite.record_module_event(
                    module="exchange_manager",
                    action="init",
                    reason=str(getattr(status, "reason", "")),
                    symbol="",
                    payload={
                        "venue": venue,
                        "enabled": bool(getattr(status, "enabled", False)),
                    },
                )
            except Exception:
                pass
        self.latest_oos_gate_pass = True

    def _missing_limits(self) -> bool:
        req = [
            self.settings.risk.max_daily_loss_pct,
            self.settings.risk.max_drawdown_pct,
            self.settings.risk.max_position_notional,
            self.settings.risk.max_exposure_notional,
            self.settings.risk.max_orders_per_min,
            self.settings.risk.leverage,
            self.settings.risk.max_spread_bps,
            self.settings.risk.min_depth_notional,
            self.settings.risk.stale_data_seconds,
            self.settings.risk.min_margin_buffer,
            self.settings.risk.max_funding_cost_per_day,
            self.settings.risk.max_oi_spike_pct,
            self.settings.risk.max_liquidation_spike,
            self.settings.risk.divergence_threshold_bps,
            self.settings.risk.crowding_score_kill,
            self.settings.tco.max_total_cost_bps,
            self.settings.tco.max_impact_bps,
        ]
        return any(v == UNSPECIFIED for v in req)

    def _kill_file_path(self) -> str:
        return os.path.join(self.settings.storage.run_dir, "KILL")

    def _walk_forward_quality_gate(self, symbol: str) -> tuple[bool, dict[str, object]]:
        enforce = os.getenv("AUTONOMOUS_WALK_FORWARD_ENFORCE", "true").strip().lower() in {"1", "true", "yes", "on"}
        enforce_nested = self._bool_env("AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE", False)
        min_samples = max(20, int(os.getenv("AUTONOMOUS_WALK_FORWARD_MIN_SAMPLES", "40") or "40"))
        fixture = self.settings.fixtures.ohlcv_csv
        if not fixture or not os.path.exists(fixture):
            payload = {
                "allowed": not enforce,
                "reason": "walk_forward_fixture_missing",
                "fixture": fixture,
                "enforced": enforce,
            }
            return False, payload
        bars = self.ingestion.replay_csv(symbol, fixture)
        prices = [float(b.mark_price if b.mark_price > 0 else b.close) for b in bars]
        if len(prices) < min_samples:
            payload = {
                "allowed": not enforce,
                "reason": "walk_forward_insufficient_samples",
                "samples": len(prices),
                "required_samples": min_samples,
                "enforced": enforce,
            }
            return bool(payload["allowed"]), payload
        train = max(20, int(len(prices) * 0.6))
        test = max(10, int(len(prices) * 0.15))
        wf = run_walk_forward_oos(prices, train=train, test=test)
        gate = wf.get("gate", {})
        nested = self.research.nested_walk_forward(prices)
        robust = self.research.robust_oos_gate(nested)
        primary_ok = bool(gate.get("allowed", False)) or (not enforce)
        nested_ok = bool(robust.get("allowed", False)) or (not enforce_nested)
        allowed = primary_ok and nested_ok
        reason = str(gate.get("reason", "walk_forward_gate_failed"))
        if primary_ok and not nested_ok:
            reason = str(robust.get("reason", "nested_walk_forward_gate_failed"))
        payload = {
            "allowed": allowed,
            "reason": reason,
            "summary": wf.get("summary", {}),
            "penalty": wf.get("penalty", {}),
            "nested_walk_forward": nested,
            "robust_oos_gate": robust,
            "splits": len(wf.get("splits", [])),
            "train": train,
            "test": test,
            "enforced": enforce,
            "nested_enforced": enforce_nested,
        }
        return bool(allowed), payload

    def _bool_env(self, name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _profile_name(self) -> str:
        return str(os.getenv("AUTONOMOUS_PROFILE", "") or "").strip().lower()

    def _profile_default(self, name: str, default: str) -> str:
        raw = os.getenv(name)
        if raw is not None:
            return str(raw)
        if self._profile_name() == "aggressive_hf":
            return str(AGGRESSIVE_HF_PROFILE_DEFAULTS.get(name, default))
        return str(default)

    def _bool_env_profile(self, name: str, default: bool) -> bool:
        raw = self._profile_default(name, "true" if default else "false")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _float_env_profile(self, name: str, default: float) -> float:
        raw = self._profile_default(name, str(default))
        try:
            return float(raw)
        except Exception:
            return float(default)

    def _int_env_profile(self, name: str, default: int) -> int:
        raw = self._profile_default(name, str(default))
        try:
            return int(float(raw))
        except Exception:
            return int(default)

    def _guards_mode(self) -> str:
        mode = str(os.getenv("AUTONOMOUS_GUARDS_MODE", "strict") or "strict").strip().lower()
        if mode not in {"strict", "fatal_only"}:
            return "strict"
        return mode

    def _universe_allowlist(self) -> set[str] | None:
        raw = str(os.getenv("AUTONOMOUS_UNIVERSE_ALLOWLIST", "") or "").strip()
        if not raw:
            # If explicit allowlist is missing, use fallback symbols as a safe implicit
            # allowlist so dynamic discovery cannot fan out into account-ineligible pairs.
            raw = str(os.getenv("AUTONOMOUS_FALLBACK_SYMBOLS", "") or "").strip()
        if not raw:
            return None
        out: set[str] = set()
        for row in raw.split(","):
            sym = row.strip().upper()
            if sym:
                out.add(sym)
        return out if out else None

    def _operator_universe_override(self) -> list[str]:
        raw = str(os.getenv("AUTONOMOUS_OPERATOR_UNIVERSE_OVERRIDE", "") or "").strip()
        if not raw:
            return []
        out: list[str] = []
        for row in raw.split(","):
            sym = row.strip().upper()
            if sym and sym not in out:
                out.append(sym)
        return out

    def _write_runtime_health(self, *, status: str, reason: str = "", extra: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {
            "ts": time.time(),
            "last_progress_ts": time.time(),
            "status": status,
            "reason": reason,
            "mode": str(self.settings.execution.mode),
            "provider": self.settings.live_provider() if self.settings.execution.mode != "paper" else "paper_sim_provider",
            "run_dir": self.settings.storage.run_dir,
            "watchdog_state_path": self._watchdog_state_path,
        }
        if isinstance(extra, dict) and extra:
            payload.update(extra)
        try:
            with open(self._health_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True))
        except Exception:
            pass

    def _record_module_event(
        self,
        *,
        module: str,
        action: str,
        reason: str = "",
        symbol: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.sqlite.record_module_event(
                module=module,
                action=action,
                reason=reason,
                symbol=symbol,
                payload=dict(payload or {}),
            )
        except Exception:
            pass

    def _record_violation(
        self,
        *,
        module: str,
        rule: str,
        reason: str = "",
        symbol: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.sqlite.record_violation(
                module=module,
                rule=rule,
                reason=reason,
                symbol=symbol,
                payload=dict(payload or {}),
            )
        except Exception:
            pass

    def _challenger_forecast(self, fv: FeatureVector, champion: Forecast) -> Forecast:
        edge = 0.25 * float(fv.values.get("ret_1", 0.0)) + 0.55 * float(fv.values.get("ret_3", 0.0)) + 0.20 * float(fv.values.get("flow_imbalance", 0.0))
        sigma = max(float(fv.values.get("realized_vol", 0.0)), 1e-6)
        raw = abs(edge) / (sigma + 1e-6)
        confidence = max(0.0, min(1.0, 0.45 + (raw / (1.0 + raw)) * 0.5))
        return Forecast(
            symbol=champion.symbol,
            ts=champion.ts,
            mu=edge,
            sigma=sigma,
            confidence=confidence,
            model_version=f"{champion.model_version}-challenger",
            regime=champion.regime,
            liquidity_regime=champion.liquidity_regime,
        )

    def _intent_expected_net_edge_bps(self, intent: OrderIntent | None) -> float:
        if intent is None or not isinstance(intent.why, dict):
            return 0.0
        comps = intent.why.get("components", [])
        if not isinstance(comps, list) or not comps:
            return 0.0
        w_sum = 0.0
        v_sum = 0.0
        for c in comps:
            if not isinstance(c, dict):
                continue
            w = float(c.get("weight", c.get("allocator_weight_raw", 0.0)) or 0.0)
            if w <= 0:
                continue
            edge = float(c.get("final_edge_bps", c.get("edge_bps", 0.0)) or 0.0)
            cost = float(c.get("cost_total_bps", 0.0) or 0.0)
            v_sum += w * (edge - cost)
            w_sum += w
        return 0.0 if w_sum <= 0 else v_sum / w_sum

    def _portfolio_symbol_score(self, *, ret_1: float, ret_3: float, spread_bps: float, depth_notional: float, rv: float, existing_exposure: float) -> float:
        momentum = (ret_1 * 7000.0) + (ret_3 * 3000.0)
        liquidity = min(30.0, max(0.0, depth_notional) ** 0.5 / 15.0)
        spread_penalty = spread_bps * 0.9
        vol_penalty = min(25.0, max(0.0, rv) * 10000.0 * 0.1)
        inventory_bonus = min(8.0, abs(existing_exposure) / 10.0)
        return momentum + liquidity + inventory_bonus - spread_penalty - vol_penalty

    def _correlation_matrix(self, returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {s: {} for s in returns}
        symbols = list(returns.keys())
        for a in symbols:
            xa = returns.get(a, [])
            if len(xa) < 5:
                out[a][a] = 1.0
                continue
            ma = sum(xa) / len(xa)
            va = sum((x - ma) ** 2 for x in xa) / len(xa)
            sa = va ** 0.5
            for b in symbols:
                xb = returns.get(b, [])
                if len(xb) < 5:
                    out[a][b] = 0.0 if a != b else 1.0
                    continue
                mb = sum(xb) / len(xb)
                vb = sum((x - mb) ** 2 for x in xb) / len(xb)
                sb = vb ** 0.5
                if sa <= 1e-12 or sb <= 1e-12:
                    out[a][b] = 0.0 if a != b else 1.0
                    continue
                n = min(len(xa), len(xb))
                cov = sum((xa[-n + i] - ma) * (xb[-n + i] - mb) for i in range(n)) / n
                out[a][b] = max(-1.0, min(1.0, cov / (sa * sb)))
        return out

    def _limit_float(self, value: float | str, default: float) -> float:
        if value == UNSPECIFIED:
            return float(default)
        try:
            return float(value)
        except Exception:
            return float(default)

    def _live_loop(self, live: object, symbol: str, mode: ExecutionMode) -> dict:
        default_poll = "2" if self.settings.live_provider() == "kraken_spot" else "5"
        poll_s = max(0.5, float(os.getenv("AUTONOMOUS_LIVE_POLL_SECONDS", default_poll)))
        rebalance_deadzone_factor = max(0.0, min(1.0, float(os.getenv("AUTONOMOUS_REBALANCE_DEADZONE_FACTOR", "0.5"))))
        rebalance_deadzone_floor = max(0.01, float(os.getenv("AUTONOMOUS_REBALANCE_DEADZONE_FLOOR", "0.25")))
        min_order_notional_quote = max(0.0, float(os.getenv("AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", "0") or "0"))
        self_tuner_enabled = self._bool_env("AUTONOMOUS_SELF_TUNER_ENABLED", True)
        self_tuner_every_steps = max(1, int(os.getenv("AUTONOMOUS_SELF_TUNER_EVERY_STEPS", "20") or "20"))
        self_tuner_window_events = max(20, int(os.getenv("AUTONOMOUS_SELF_TUNER_WINDOW_EVENTS", "300") or "300"))
        self_tuner_min_samples = max(1, int(os.getenv("AUTONOMOUS_SELF_TUNER_MIN_SAMPLES", "40") or "40"))
        self_tuner_size_scale = max(0.1, float(os.getenv("AUTONOMOUS_SELF_TUNER_SIZE_SCALE_INIT", "1.0") or "1.0"))
        self_tuner_size_scale_min = max(0.1, float(os.getenv("AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MIN", "0.35") or "0.35"))
        self_tuner_size_scale_max = max(self_tuner_size_scale_min, float(os.getenv("AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MAX", "1.75") or "1.75"))
        self_tuner_floor_min_default = min_order_notional_quote if min_order_notional_quote > 0.0 else 0.25
        self_tuner_floor_min = max(
            0.0,
            float(
                os.getenv(
                    "AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MIN",
                    f"{self_tuner_floor_min_default}",
                )
                or f"{self_tuner_floor_min_default}"
            ),
        )
        self_tuner_floor_max_default = max(
            self_tuner_floor_min,
            min(25.0, self_tuner_floor_min * 8.0),
        )
        self_tuner_floor_max = max(
            self_tuner_floor_min,
            float(
                os.getenv(
                    "AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MAX",
                    f"{self_tuner_floor_max_default}",
                )
                or f"{self_tuner_floor_max_default}"
            ),
        )
        dynamic_portfolio = self._bool_env("AUTONOMOUS_PORTFOLIO_OPTIMIZER", self.settings.live_provider() == "kraken_spot")
        reselect_every_steps = max(1, int(os.getenv("AUTONOMOUS_PORTFOLIO_RESELECT_EVERY_STEPS", "12") or "12"))
        portfolio_scan_batch = max(1, int(os.getenv("AUTONOMOUS_PORTFOLIO_SCAN_BATCH", "80") or "80"))
        symbol_topk = max(1, self._int_env_profile("AUTONOMOUS_SYMBOL_TOPK", 20))
        symbol_score_refresh_s = max(1.0, self._float_env_profile("AUTONOMOUS_SYMBOL_SCORE_REFRESH_S", 15.0))
        symbol_score_refresh_steps = max(1, int(round(symbol_score_refresh_s / max(poll_s, 0.1))))
        reselect_every_steps = min(reselect_every_steps, symbol_score_refresh_steps)
        switch_only_when_flat_notional = max(0.0, float(os.getenv("AUTONOMOUS_PORTFOLIO_SWITCH_ONLY_WHEN_FLAT_NOTIONAL", "1.0") or "1.0"))
        min_symbol_score_gap = max(0.0, float(os.getenv("AUTONOMOUS_PORTFOLIO_MIN_SCORE_GAP", "2.0") or "2.0"))
        portfolio_turnover_penalty = max(0.0, min(0.95, float(os.getenv("AUTONOMOUS_PORTFOLIO_TURNOVER_PENALTY", "0.35") or "0.35")))
        portfolio_cluster_cap = max(0.05, min(1.0, float(os.getenv("AUTONOMOUS_PORTFOLIO_CLUSTER_CAP", "0.65") or "0.65")))
        challenger_enabled = self._bool_env("AUTONOMOUS_CHALLENGER_ENABLED", True)
        challenger_warmup_steps = max(5, int(os.getenv("AUTONOMOUS_CHALLENGER_WARMUP_STEPS", "25") or "25"))
        challenger_margin = float(os.getenv("AUTONOMOUS_CHALLENGER_PROMOTION_MARGIN", "2.0") or "2.0")
        adaptive_sizing_enabled = self._bool_env("AUTONOMOUS_ADAPTIVE_SIZING_ENABLED", True)
        adaptive_min_scale = max(0.1, float(os.getenv("AUTONOMOUS_ADAPTIVE_MIN_SCALE", "0.35") or "0.35"))
        adaptive_max_scale = max(adaptive_min_scale, float(os.getenv("AUTONOMOUS_ADAPTIVE_MAX_SCALE", "1.4") or "1.4"))
        exit_time_stop_s = max(60.0, float(os.getenv("AUTONOMOUS_EXIT_TIME_STOP_S", "3600") or "3600"))
        exit_trailing_drawdown_quote = max(0.01, float(os.getenv("AUTONOMOUS_EXIT_TRAILING_DD_QUOTE", "1.0") or "1.0"))
        exit_partial_fraction = max(0.1, min(1.0, float(os.getenv("AUTONOMOUS_EXIT_PARTIAL_FRACTION", "0.5") or "0.5")))
        exit_vol_stop_threshold = max(0.001, float(os.getenv("AUTONOMOUS_EXIT_VOL_STOP_THRESHOLD", "0.02") or "0.02"))
        exit_profit_only = self._bool_env("AUTONOMOUS_EXIT_PROFIT_ONLY", True)
        exit_min_profit_quote = max(0.0, float(os.getenv("AUTONOMOUS_EXIT_MIN_PROFIT_QUOTE", "0.0") or "0.0"))
        exit_take_profit_pct = max(0.0, float(os.getenv("AUTONOMOUS_EXIT_TAKE_PROFIT_PCT", "0.0") or "0.0"))
        exit_take_profit_full_close = self._bool_env("AUTONOMOUS_EXIT_TAKE_PROFIT_FULL_CLOSE", True)
        sell_profit_lock_enabled = self._bool_env("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", True)
        default_sell_profit_bps = max(
            0.0,
            (2.0 * float(self.settings.execution.fee_bps)) + (2.0 * float(self.settings.execution.slippage_bps)),
        )
        sell_profit_lock_min_bps = max(
            0.0,
            float(
                os.getenv(
                    "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS",
                    f"{default_sell_profit_bps}",
                )
                or f"{default_sell_profit_bps}"
            ),
        )
        sell_profit_lock_min_bps = max(sell_profit_lock_min_bps, default_sell_profit_bps)
        sell_profit_lock_target_bps = max(
            sell_profit_lock_min_bps,
            float(
                os.getenv(
                    "AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS",
                    f"{sell_profit_lock_min_bps}",
                )
                or f"{sell_profit_lock_min_bps}"
            ),
        )
        sell_profit_lock_target_hold_s = max(
            0.0,
            float(os.getenv("AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S", "90") or "90"),
        )
        sell_profit_lock_fatal_bypass = self._bool_env("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", False)
        sell_profit_lock_require_cost_basis = self._bool_env("AUTONOMOUS_SPOT_SELL_REQUIRE_COST_BASIS", True)
        alert_reject_rate = max(0.0, min(1.0, float(os.getenv("AUTONOMOUS_ALERT_REJECT_RATE", "0.8") or "0.8")))
        alert_shortfall_bps = max(0.0, float(os.getenv("AUTONOMOUS_ALERT_SHORTFALL_BPS", "15.0") or "15.0"))
        alert_cooldown_steps = max(1, int(os.getenv("AUTONOMOUS_ALERT_COOLDOWN_STEPS", "30") or "30"))
        max_cost_to_alpha_ratio = max(0.1, float(os.getenv("AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO", "1.8") or "1.8"))
        modeled_ratio_ewma_alpha = max(0.01, min(1.0, float(os.getenv("AUTONOMOUS_MODELED_COST_ALPHA_EWMA", "0.25") or "0.25")))
        modeled_ratio_eps = 1e-9
        toxicity_threshold = max(0.0, min(1.0, float(os.getenv("AUTONOMOUS_TOXICITY_THRESHOLD", "0.75") or "0.75")))
        toxicity_throttle_scale = max(0.05, min(1.0, float(os.getenv("AUTONOMOUS_TOXICITY_THROTTLE_SCALE", "0.5") or "0.5")))
        toxicity_cooldown_s = max(1.0, float(os.getenv("AUTONOMOUS_TOXICITY_COOLDOWN_S", "60") or "60"))
        entry_safe_mode_enabled = self._bool_env("AUTONOMOUS_ENTRY_SAFE_MODE", True)
        volstop_throttle_scale = max(0.05, min(1.0, float(os.getenv("AUTONOMOUS_VOLSTOP_THROTTLE_SCALE", "0.30") or "0.30")))
        volstop_cooldown_s = max(1.0, float(os.getenv("AUTONOMOUS_VOLSTOP_COOLDOWN_S", "30") or "30"))
        min_seconds_between_orders = max(0.0, float(os.getenv("AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS", "0") or "0"))
        order_submission_interval_s = min(
            60.0,
            max(1.0, self._float_env_profile("ORDER_SUBMISSION_INTERVAL_SECONDS", 60.0)),
        )
        extra_submissions_enabled = self._bool_env_profile("AUTONOMOUS_EXTRA_SUBMISSIONS_ENABLED", False)
        extra_submissions_max_per_min = max(0, self._int_env_profile("AUTONOMOUS_EXTRA_SUBMISSIONS_MAX_PER_MIN", 0))
        probe_notional_quote = max(0.25, self._float_env_profile("AUTONOMOUS_PROBE_NOTIONAL_QUOTE", 1.5))
        probe_distance_ticks = max(1, self._int_env_profile("AUTONOMOUS_PROBE_DISTANCE_TICKS", 1))
        audit_cfg = getattr(self.settings, "health_audit_110", None)
        audit_enabled = self._bool_env(
            "AUTONOMOUS_HEALTH_AUDIT110_ENABLED",
            self._bool_env(
                "AUTONOMOUS_HEALTH_AUDIT_ENABLED",
                bool(getattr(audit_cfg, "enabled", True)),
            ),
        )
        audit_interval_s = max(
            60.0,
            float(
                os.getenv(
                    "AUTONOMOUS_HEALTH_AUDIT110_INTERVAL_S",
                    os.getenv(
                        "AUTONOMOUS_HEALTH_AUDIT_INTERVAL_S",
                        str(getattr(audit_cfg, "interval_s", 600.0)),
                    ),
                )
                or os.getenv(
                    "AUTONOMOUS_HEALTH_AUDIT_INTERVAL_S",
                    str(getattr(audit_cfg, "interval_s", 600.0)),
                )
            ),
        )
        audit_pause_openings_s = max(
            30.0,
            float(
                os.getenv(
                    "AUTONOMOUS_HEALTH_AUDIT_PAUSE_OPENINGS_S",
                    str(getattr(audit_cfg, "pause_openings_s", 180.0)),
                )
                or str(getattr(audit_cfg, "pause_openings_s", 180.0))
            ),
        )
        mode_label = str(os.getenv("AUTONOMOUS_MODE_LABEL", "") or "").strip().lower()
        growth_mode = self._bool_env("AUTONOMOUS_GROWTH_MODE", mode_label in {"growth", "canary", "main", "promoted", "pro_growth"})
        operator_pause_entries = self._bool_env("AUTONOMOUS_OPERATOR_PAUSE_ENTRIES", False)
        enforce_mandate = self._bool_env("AUTONOMOUS_ENFORCE_MANDATE", True)
        mandate_max_leverage = max(1, int(os.getenv("AUTONOMOUS_MANDATE_MAX_LEVERAGE", "1") or "1"))
        guards_mode = self._guards_mode()
        fatal_only_mode = guards_mode == "fatal_only"
        failed_probe_block_n = max(
            1,
            int(os.getenv("AUTONOMOUS_NO_NEW_ENTRIES_AFTER_FAILED_PROBES_N", "5") or "5"),
        )
        max_steps = int(os.getenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "0") or "0")
        # Production LIVE mode must run nonstop; max_steps is test/sandbox-only.
        if mode == ExecutionMode.LIVE:
            max_steps = 0
        base_budget = max(float(self.settings.policy.base_risk_budget), 1.0)
        exposure_notional = 0.0
        signed_exposure_notional = 0.0
        equity = 1.0
        peak = 1.0
        funding_paid_pct = 0.0
        prices: list[float] = []
        last_mid = None
        last_net_pnl_quote = 0.0
        last_recon_ok = True
        steps = 0
        orders_submitted = 0.0
        orders_rejected = 0.0
        rate_limit_events_total = 0.0
        fills_confirmed = 0.0
        maker_fills = 0.0
        taker_fills = 0.0
        intents_total = 0.0
        executions_attempted_total = 0.0
        executions_submitted_total = 0.0
        cost_to_alpha_ratio_modeled_ewma: float | None = None
        min_order_notional_quote_live = min_order_notional_quote
        tune_window: deque[dict[str, str]] = deque(maxlen=self_tuner_window_events)
        tuning_state_path = os.path.join(self.settings.storage.run_dir, "tuning_state.json")
        try:
            if os.path.exists(tuning_state_path):
                with open(tuning_state_path, "r", encoding="utf-8") as fh:
                    state = json.load(fh)
                if isinstance(state, dict):
                    self_tuner_size_scale = max(
                        self_tuner_size_scale_min,
                        min(self_tuner_size_scale_max, float(state.get("size_scale", self_tuner_size_scale) or self_tuner_size_scale)),
                    )
                    min_order_notional_quote_live = max(
                        self_tuner_floor_min,
                        min(self_tuner_floor_max, float(state.get("min_order_notional_quote", min_order_notional_quote_live) or min_order_notional_quote_live)),
                    )
        except Exception:
            pass
        total_exec_notional = 0.0
        total_fee_paid = 0.0
        total_slippage_paid = 0.0
        total_model_slippage_paid = 0.0
        non_attempt_block_reasons = {
            "min_order_block",
            "qty_precision_block",
            "price_precision_block",
            "insufficient_balance_block",
            "insufficient_base_balance_block",
            "rate_limit_cooldown",
            "cooldown",
            "cadence_cooldown",
            "dust_accumulator_hold",
            "dust_accumulate",
            "inventory_below_min_order",
            "profit_lock_sell_below_entry",
            "profit_lock_missing_cost_basis",
            "pretrade_credit_insufficient_quote",
            "pretrade_credit_insufficient_base",
            "pretrade_max_position_notional",
            "pretrade_exposure_notional",
            "exchange_constraint_invalid",
        }
        non_fatal_probe_block_reasons = {
            "entries_blocked_until_health_ok",
            "exits_only_mode",
            "insufficient_balance_block",
            "insufficient_base_balance_block",
            "inventory_below_min_order",
            "inventory_throttle_max",
            "no_trade_zone",
            "expected_fill_probability_low",
            "fee_aware_no_edge",
            "stale_market_data_buy_block",
            "symbol_quarantine",
            "session_closed",
            "cooldown",
            "cadence_cooldown",
        }
        failed_probe_block_cooldown_s = max(
            60.0,
            float(os.getenv("AUTONOMOUS_FAILED_PROBE_BLOCK_COOLDOWN_S", "300") or "300"),
        )
        max_drawdown_seen = 0.0
        toxicity_freeze_until_ts = 0.0
        toxicity_freeze_events = 0.0
        volstop_cooldown_until_ts = 0.0
        last_order_attempt_ts = 0.0
        audit_pause_new_risk_until_ts = 0.0
        failed_probe_streak = 0
        block_new_entries_until_health_ok = False
        block_new_entries_until_ts = 0.0
        extra_probe_submission_ts: deque[float] = deque(maxlen=512)
        extra_probe_backoff_until_ts = 0.0
        governor_base_extra_submissions = max(0, extra_submissions_max_per_min)
        governor_base_exit_reprice_interval = 0.0
        governor_base_cancel_replace_budget = 0
        managed_services = [
            live,
            getattr(live, "spot_service", None),
            getattr(live, "futures_service", None),
        ]
        for svc in managed_services:
            if svc is None or not hasattr(svc, "exit_order_manager"):
                continue
            cfg = getattr(getattr(svc, "exit_order_manager", None), "config", None)
            if cfg is not None:
                governor_base_exit_reprice_interval = max(
                    governor_base_exit_reprice_interval,
                    float(getattr(cfg, "reprice_interval_s", 0.0) or 0.0),
                )
                governor_base_cancel_replace_budget = max(
                    governor_base_cancel_replace_budget,
                    int(
                        max(
                            1,
                            int(
                                getattr(
                                    cfg,
                                    "cancel_replace_budget_per_symbol_per_min",
                                    1,
                                )
                                or 1
                            ),
                        )
                    ),
                )
        last_audit_failed_checks: list[str] = []
        restored_last_submission_ts = None
        try:
            restored_last_submission_ts = self.sqlite.latest_submission_epoch()
        except Exception:
            restored_last_submission_ts = None
        submission_scheduler = OrderSubmissionScheduler(
            interval_s=order_submission_interval_s,
            initial_last_submission_ts=restored_last_submission_ts,
        )
        if restored_last_submission_ts is not None:
            self.ops.audit_event(
                "scheduler_restore",
                {
                    "last_submission_ts": restored_last_submission_ts,
                    "interval_s": order_submission_interval_s,
                },
            )

        def _sync_runtime_adapters(now_ts_local: float) -> None:
            # Wire runtime adapters without changing existing execution contracts.
            nonlocal extra_probe_backoff_until_ts
            connector_spot = getattr(live, "connector", None)
            connector_perps = None
            if hasattr(live, "futures_service"):
                connector_perps = getattr(getattr(live, "futures_service", None), "connector", None)
            elif hasattr(live, "connector") and self.settings.live_provider() in {"kraken_futures"}:
                connector_perps = connector_spot
            self.fee_profile.connector_spot = connector_spot
            self.fee_profile.connector_perps = connector_perps
            fee_prof = self.fee_profile.maybe_refresh(
                pair=symbol,
                now_ts=now_ts_local,
                trade_volume_hint=total_exec_notional,
            )
            if float(getattr(fee_prof, "updated_ts", 0.0) or 0.0) > float(self._last_fee_profile_updated_ts):
                self._last_fee_profile_updated_ts = float(getattr(fee_prof, "updated_ts", now_ts_local) or now_ts_local)
                self._record_module_event(
                    module="fee_profile_service",
                    action="refresh",
                    reason=str(getattr(fee_prof, "source", "")),
                    symbol=symbol,
                    payload={
                        "spot_maker_fee_bps": float(getattr(fee_prof, "spot_maker_fee_bps", 0.0)),
                        "spot_taker_fee_bps": float(getattr(fee_prof, "spot_taker_fee_bps", 0.0)),
                        "perps_maker_fee_bps": float(getattr(fee_prof, "perps_maker_fee_bps", 0.0)),
                        "perps_taker_fee_bps": float(getattr(fee_prof, "perps_taker_fee_bps", 0.0)),
                    },
                )
            if hasattr(live, "set_fee_profile"):
                try:
                    live.set_fee_profile(fee_prof)
                except Exception:
                    pass
            if hasattr(live, "spot_service") and hasattr(live.spot_service, "set_fee_profile"):
                try:
                    live.spot_service.set_fee_profile(fee_prof)
                except Exception:
                    pass
            if hasattr(live, "futures_service") and hasattr(live.futures_service, "set_fee_profile"):
                try:
                    live.futures_service.set_fee_profile(fee_prof)
                except Exception:
                    pass

            market_kind = "perps" if self.settings.live_provider() in {"kraken_futures"} else "spot"
            cal_bps = self.slippage_calibrator.calibrated_bps(market=market_kind)
            if hasattr(live, "set_profit_gate_slippage_bps"):
                try:
                    live.set_profit_gate_slippage_bps(cal_bps)
                except Exception:
                    pass
            if hasattr(live, "spot_service") and hasattr(live.spot_service, "set_profit_gate_slippage_bps"):
                try:
                    live.spot_service.set_profit_gate_slippage_bps(self.slippage_calibrator.calibrated_bps(market="spot"))
                except Exception:
                    pass
            if hasattr(live, "futures_service") and hasattr(live.futures_service, "set_profit_gate_slippage_bps"):
                try:
                    live.futures_service.set_profit_gate_slippage_bps(self.slippage_calibrator.calibrated_bps(market="perps"))
                except Exception:
                    pass

            gov_state = self.rate_limit_governor.state(
                now_ts=now_ts_local,
                base_extra_submissions=governor_base_extra_submissions,
            )
            self.ops.set_metric("rate_limit_governor_storm", 1.0 if gov_state.storm_active else 0.0)
            self.ops.set_metric("rate_limit_governor_recent_events", float(gov_state.recent_events_60s))
            if gov_state.storm_active:
                self.order_churn_controller.note_rate_limit_storm(now_ts=now_ts_local)
                self._record_module_event(
                    module="rate_limit_governor",
                    action="storm_on",
                    reason="rate_limit_governor_storm",
                    payload={"recent_events_60s": float(gov_state.recent_events_60s)},
                )
                if hasattr(live, "set_exits_only_mode"):
                    try:
                        live.set_exits_only_mode(
                            reason="rate_limit_governor_storm",
                            duration_s=max(60.0, order_submission_interval_s * 2.0),
                        )
                    except Exception:
                        pass
                if governor_base_exit_reprice_interval > 0.0:
                    churn_rec = self.order_churn_controller.recommendations(now_ts=now_ts_local)
                    for svc in (
                        live,
                        getattr(live, "spot_service", None),
                        getattr(live, "futures_service", None),
                    ):
                        if svc is None or not hasattr(svc, "exit_order_manager"):
                            continue
                        cfg = getattr(getattr(svc, "exit_order_manager", None), "config", None)
                        if cfg is None:
                            continue
                        cfg.reprice_interval_s = self.rate_limit_governor.adjusted_reprice_interval(
                            max(governor_base_exit_reprice_interval, float(getattr(cfg, "reprice_interval_s", 0.0) or 0.0)),
                            now_ts=now_ts_local,
                        )
                        cfg.cancel_replace_budget_per_symbol_per_min = self.rate_limit_governor.adjusted_cancel_replace_budget(
                            max(1, governor_base_cancel_replace_budget or int(getattr(cfg, "cancel_replace_budget_per_symbol_per_min", 1) or 1)),
                            now_ts=now_ts_local,
                        )
                        cfg.max_cancel_replace_per_min = min(
                            int(getattr(cfg, "max_cancel_replace_per_min", churn_rec.max_cancel_replace_per_min) or churn_rec.max_cancel_replace_per_min),
                            int(churn_rec.max_cancel_replace_per_min),
                        )
                        cfg.cancel_replace_budget_per_symbol_per_min = min(
                            int(cfg.cancel_replace_budget_per_symbol_per_min),
                            int(churn_rec.budget_per_symbol_per_min),
                        )
                        cfg.reprice_interval_s = max(
                            float(cfg.reprice_interval_s),
                            float(governor_base_exit_reprice_interval or cfg.reprice_interval_s)
                            * float(churn_rec.reprice_interval_multiplier),
                        )
                extra_probe_backoff_until_ts = max(
                    extra_probe_backoff_until_ts,
                    now_ts_local + order_submission_interval_s,
                )
            else:
                self._record_module_event(
                    module="rate_limit_governor",
                    action="storm_off",
                    reason="rate_limit_governor_recovered",
                    payload={"recent_events_60s": float(gov_state.recent_events_60s)},
                )
                if hasattr(live, "clear_exits_only_mode"):
                    try:
                        live.clear_exits_only_mode()
                    except Exception:
                        pass
                if governor_base_exit_reprice_interval > 0.0:
                    churn_rec = self.order_churn_controller.recommendations(now_ts=now_ts_local)
                    for svc in (
                        live,
                        getattr(live, "spot_service", None),
                        getattr(live, "futures_service", None),
                    ):
                        if svc is None or not hasattr(svc, "exit_order_manager"):
                            continue
                        cfg = getattr(getattr(svc, "exit_order_manager", None), "config", None)
                        if cfg is None:
                            continue
                        cfg.reprice_interval_s = max(
                            float(governor_base_exit_reprice_interval),
                            float(governor_base_exit_reprice_interval) * float(churn_rec.reprice_interval_multiplier),
                        )
                        cfg.cancel_replace_budget_per_symbol_per_min = max(
                            1,
                            min(
                                int(governor_base_cancel_replace_budget or 1),
                                int(churn_rec.budget_per_symbol_per_min),
                            ),
                        )
                        cfg.max_cancel_replace_per_min = max(
                            1,
                            int(churn_rec.max_cancel_replace_per_min),
                        )
        signal_edge_gross_quote = 0.0
        execution_cost_quote = 0.0
        alpha_net_quote = 0.0
        live_state: dict[str, object] = {}
        position_open_ts: float | None = None
        position_peak_net_pnl_quote = 0.0
        model_scores = {"champion": 0.0, "challenger": 0.0}
        model_last_mu = {"champion": 0.0, "challenger": 0.0}
        model_last_mid = 0.0
        active_model_name = "champion"
        last_active_model_name = "champion"
        price_histories: dict[str, list[float]] = {s: [] for s in self.settings.universe}
        return_histories: dict[str, list[float]] = {s: [] for s in self.settings.universe}
        symbol_candidates = [s for s in self.settings.universe if s]
        if symbol not in symbol_candidates:
            symbol_candidates.insert(0, symbol)
        symbol_scores: dict[str, float] = {s: 0.0 for s in symbol_candidates}
        portfolio_weights: dict[str, float] = {s: 0.0 for s in symbol_candidates}
        portfolio_weights[symbol] = 1.0
        latest_feed_quotes: list[VenueQuote] = []
        latest_feed_quality: dict[str, object] = {}
        stuck_decision_reason = ""
        symbol_exposure_quote: dict[str, float] = {}
        symbol_position_age_s: dict[str, float] = {}
        capital_unlock_reason = "ok"
        capital_unlock_entry_scale = 1.0
        next_health_audit_ts = time.time() + min(30.0, audit_interval_s)
        last_alert_step: dict[str, int] = {}
        feature_schema_registered = False
        oos_gate_live_pass = bool(getattr(self, "latest_oos_gate_pass", True))
        dust_path = os.path.join(self.settings.storage.run_dir, "dust_accumulator.json")
        dust_accumulator: dict[str, dict[str, float]] = {}
        try:
            if os.path.exists(dust_path):
                with open(dust_path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                    if isinstance(raw, dict):
                        for k, v in raw.items():
                            if isinstance(v, dict):
                                dust_accumulator[k] = {
                                    "buy": float(v.get("buy", 0.0) or 0.0),
                                    "sell": float(v.get("sell", 0.0) or 0.0),
                                }
        except Exception:
            dust_accumulator = {}

        def _save_dust() -> None:
            try:
                os.makedirs(self.settings.storage.run_dir, exist_ok=True)
                with open(dust_path, "w", encoding="utf-8") as fh:
                    json.dump(dust_accumulator, fh, sort_keys=True, indent=2)
            except Exception:
                pass

        def _dust_for(sym: str, side: str) -> float:
            row = dust_accumulator.setdefault(sym, {"buy": 0.0, "sell": 0.0})
            return float(row.get(side, 0.0) or 0.0)

        def _set_dust(sym: str, side: str, value: float) -> None:
            row = dust_accumulator.setdefault(sym, {"buy": 0.0, "sell": 0.0})
            row[side] = max(0.0, float(value))
            _save_dust()

        def _submit_safe_probe_from_audit(reason: str, *, from_extra: bool = False, audit110: bool = False) -> bool:
            nonlocal failed_probe_streak, block_new_entries_until_health_ok, block_new_entries_until_ts, extra_probe_backoff_until_ts
            now_probe = time.time()
            if block_new_entries_until_health_ok and now_probe >= block_new_entries_until_ts:
                block_new_entries_until_health_ok = False
                failed_probe_streak = 0
                if hasattr(live, "set_health_ok"):
                    try:
                        live.set_health_ok(True)
                    except Exception:
                        pass
            probe_notional = max(
                0.25,
                min_order_notional_quote_live,
                rebalance_deadzone_floor,
                probe_notional_quote,
                float((live_state or {}).get("min_trade_notional_quote", 0.0) or 0.0),
            )
            try:
                if hasattr(live, "_available_quote_balance"):
                    _qccy, free_quote = live._available_quote_balance(symbol)  # type: ignore[attr-defined]
                    free_quote_f = max(0.0, float(free_quote))
                    if free_quote_f > 0.0:
                        probe_notional = min(probe_notional, free_quote_f * 0.90)
                        probe_notional = max(0.25, probe_notional)
            except Exception:
                pass
            strategy_name = "audit110_scheduler_probe" if audit110 else ("extra_scheduler_probe" if from_extra else "scheduler_probe")
            probe_why = {
                "scheduler_probe": True,
                "reason": reason,
                "probe_distance_ticks": probe_distance_ticks,
                "execution_route": {"order_type": "maker"},
                "components": [
                    {
                        "strategy": strategy_name,
                        "weight": 1.0,
                        "final_edge_bps": 320.0,
                        "cost_total_bps": 80.0,
                    }
                ],
            }
            probe = OrderIntent(symbol=symbol, side="buy", target_notional=probe_notional, why=probe_why)
            probe_result = self.execution.execute_live(probe)
            self.ops.audit_event(
                "scheduler_probe",
                {
                    "symbol": symbol,
                    "status": probe_result.status,
                    "reason": probe_result.reason,
                    "notional": probe_notional,
                    "interval_s": order_submission_interval_s,
                },
            )
            self.sqlite.record_submission(
                symbol=symbol,
                status=str(probe_result.status),
                reason=str(probe_result.reason),
                notional_quote=float(probe_notional),
                payload={"scheduler_probe": True, "audit110": audit110, "extra_submission": from_extra},
            )
            probe_order = probe_result.order if isinstance(probe_result.order, dict) else {}
            request_sent = bool(probe_order.get("request_sent", False))
            submitted = request_sent or probe_result.status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}
            reason_text = str(probe_result.reason)
            reason_lower = reason_text.strip().lower()
            non_fatal_block = probe_result.status in {"blocked", "skipped"} and reason_lower in non_fatal_probe_block_reasons
            if "rate_limit" in reason_text.lower():
                self.rate_limit_governor.record_error(
                    endpoint="scheduler_probe",
                    error_text=reason_text,
                    now_ts=time.time(),
                )
            else:
                self.rate_limit_governor.record_success(
                    endpoint="scheduler_probe",
                    now_ts=time.time(),
                )
            if submitted:
                submission_scheduler.record_submission(
                    now_ts=time.time(),
                    filled=probe_result.status in {"filled_maker", "filled_taker_fallback"},
                )
                if from_extra:
                    extra_probe_submission_ts.append(time.time())
                failed_probe_streak = 0
                block_new_entries_until_health_ok = False
                block_new_entries_until_ts = 0.0
                if hasattr(live, "set_health_ok"):
                    try:
                        live.set_health_ok(True)
                    except Exception:
                        pass
            elif non_fatal_block:
                # Keep cadence logic alive without escalating to global entry block on benign probe failures.
                failed_probe_streak = 0
            else:
                failed_probe_streak += 1
                if "rate_limit" in str(probe_result.reason).lower():
                    extra_probe_backoff_until_ts = max(extra_probe_backoff_until_ts, time.time() + order_submission_interval_s)
                if failed_probe_streak >= failed_probe_block_n:
                    block_new_entries_until_health_ok = True
                    block_new_entries_until_ts = time.time() + failed_probe_block_cooldown_s
                    if hasattr(live, "set_exits_only_mode"):
                        try:
                            live.set_exits_only_mode(reason="failed_probe_streak", duration_s=max(120.0, audit_pause_openings_s))
                        except Exception:
                            pass
            return submitted

        def _extra_probe_allowed(now_ts: float) -> bool:
            if not extra_submissions_enabled or extra_submissions_max_per_min <= 0:
                return False
            churn_rec = self.order_churn_controller.recommendations(now_ts=now_ts)
            if not churn_rec.extra_submissions_allowed:
                return False
            max_extra_dynamic = self.rate_limit_governor.adjusted_extra_submissions(
                extra_submissions_max_per_min,
                now_ts=now_ts,
            )
            if max_extra_dynamic <= 0:
                return False
            if now_ts < extra_probe_backoff_until_ts:
                return False
            rl_until = float(getattr(live, "rate_limit_cooldown_until_s", 0.0) or 0.0)
            if now_ts < rl_until:
                return False
            while extra_probe_submission_ts and (now_ts - extra_probe_submission_ts[0]) > 60.0:
                extra_probe_submission_ts.popleft()
            return len(extra_probe_submission_ts) < max_extra_dynamic

        def _is_fatal_reduce_why(why: dict[str, object]) -> bool:
            # Fatal pathways must never bypass SELL profit lock checks.
            _ = why
            _ = sell_profit_lock_fatal_bypass
            return False

        def _sync_live_fill_state(mid_price: float) -> dict[str, object]:
            nonlocal exposure_notional, signed_exposure_notional, equity, last_net_pnl_quote, total_fee_paid, total_exec_notional, fills_confirmed
            if not hasattr(live, "sync_fill_ledger"):
                return {}
            snap = live.sync_fill_ledger(symbol, mark_price=mid_price)
            if not isinstance(snap, dict):
                return {}
            signed_exposure_notional = float(snap.get("position_notional_signed", signed_exposure_notional))
            exposure_notional = abs(float(snap.get("exposure_notional", exposure_notional)))
            net_pnl_quote = float(snap.get("net_pnl_after_fees_quote", last_net_pnl_quote))
            pnl_delta_quote = net_pnl_quote - last_net_pnl_quote
            if abs(exposure_notional) > 1e-9:
                self.risk.record_return((pnl_delta_quote / max(exposure_notional, 1.0)) * 100.0)
            equity = 1.0 + (net_pnl_quote / base_budget)
            last_net_pnl_quote = net_pnl_quote
            total_fee_paid = float(snap.get("fees_quote", total_fee_paid))
            total_exec_notional = float(snap.get("filled_notional_quote", total_exec_notional))
            qa = snap.get("execution_qa", {})
            if isinstance(qa, dict):
                self.ops.set_metric("implementation_shortfall_bps", float(qa.get("implementation_shortfall_bps", 0.0)))
                self.ops.set_metric("execution_shortfall_bps", float(qa.get("implementation_shortfall_bps", 0.0)))
                self.ops.set_metric("latency_p50_ms", float(qa.get("latency_p50_ms", 0.0)))
                lat_p95 = float(qa.get("latency_p95_ms", 0.0))
                self.ops.set_metric("latency_p95_ms", lat_p95)
                self.ops.set_metric("latency_p99_ms", float(qa.get("latency_p99_ms", lat_p95 * 1.2)))
                self.ops.set_metric("latency_bucket_fast", float(qa.get("latency_bucket_fast", 0.0)))
                self.ops.set_metric("latency_bucket_medium", float(qa.get("latency_bucket_medium", 0.0)))
                self.ops.set_metric("latency_bucket_slow", float(qa.get("latency_bucket_slow", 0.0)))
                self.ops.set_metric("fill_probability", float(qa.get("fill_probability", 0.0)))
                fills_confirmed = float(qa.get("orders_filled", fills_confirmed))
            return snap

        def _update_live_kpis() -> None:
            attempts = orders_submitted + orders_rejected
            fill_rate = fills_confirmed / max(executions_submitted_total, 1.0)
            maker_fill_rate = maker_fills / max(maker_fills + taker_fills, 1.0)
            reject_rate = 0.0 if attempts <= 0 else orders_rejected / attempts
            slippage_vs_model_bps: float | None = None
            if total_exec_notional > 0:
                slippage_vs_model_bps = ((total_slippage_paid - total_model_slippage_paid) / total_exec_notional) * 10000.0
            net_after_fees_equity = equity - (total_fee_paid + total_slippage_paid) / base_budget
            net_after_fees_pct = (net_after_fees_equity - 1.0) * 100.0
            returns = [r / 100.0 for r in self.risk.state.rolling_returns[-252:]]
            self.ops.set_metric("intents_total", intents_total)
            self.ops.set_metric("executions_attempted_total", executions_attempted_total)
            self.ops.set_metric("executions_submitted_total", executions_submitted_total)
            self.ops.set_metric("fills_confirmed_total", fills_confirmed)
            self.ops.set_metric("fees_paid", total_fee_paid)
            self.ops.set_metric("slippage_paid", total_slippage_paid)
            self.ops.set_metric("net_pnl_after_fees", net_after_fees_pct)
            self.ops.set_metric("fill_rate", fill_rate)
            self.ops.set_metric("maker_fill_rate", maker_fill_rate)
            self.ops.set_metric("reject_rate", reject_rate)
            self.ops.set_metric("slippage_vs_model_bps", slippage_vs_model_bps)
            self.ops.set_metric("realized_slippage_bps", 0.0 if slippage_vs_model_bps is None else slippage_vs_model_bps)
            self.ops.set_metric("rate_limit_events", rate_limit_events_total)
            self.ops.set_metric("toxicity_freeze_events", toxicity_freeze_events)
            self.ops.set_metric("max_drawdown", max_drawdown_seen)
            self.ops.set_metric("sharpe", sharpe(returns))
            self.ops.set_metric("sortino", sortino(returns))
            self.ops.set_metric("signal_edge_gross_quote", signal_edge_gross_quote)
            self.ops.set_metric("execution_cost_quote", execution_cost_quote)
            self.ops.set_metric("alpha_net_quote", alpha_net_quote)
            sched_stats = submission_scheduler.stats(now_ts=time.time())
            self.ops.set_metric("last_submission_ts", sched_stats.last_submission_ts)
            self.ops.set_metric("submissions_per_minute", sched_stats.submissions_per_minute)
            self.ops.set_metric("fills_per_minute", sched_stats.fills_per_minute)
            self.ops.set_metric("order_submission_interval_s", order_submission_interval_s)
            if total_exec_notional > 0:
                signal_bps = signal_edge_gross_quote / total_exec_notional * 10000.0
                cost_bps = execution_cost_quote / total_exec_notional * 10000.0
                alpha_bps = alpha_net_quote / total_exec_notional * 10000.0
                self.ops.set_metric("signal_edge_gross_bps", signal_bps)
                self.ops.set_metric("execution_cost_bps", cost_bps)
                self.ops.set_metric("alpha_net_bps", alpha_bps)
                expected_backtest_alpha = float(os.getenv("AUTONOMOUS_BACKTEST_EXPECTED_ALPHA_BPS", "0.0") or "0.0")
                self.ops.set_metric("live_vs_backtest_divergence_bps", alpha_bps - expected_backtest_alpha)
            else:
                self.ops.set_metric("signal_edge_gross_bps", 0.0)
                self.ops.set_metric("execution_cost_bps", 0.0)
                self.ops.set_metric("alpha_net_bps", 0.0)
                self.ops.set_metric("live_vs_backtest_divergence_bps", 0.0)
            self.ops.set_metric("champion_score", model_scores["champion"])
            self.ops.set_metric("challenger_score", model_scores["challenger"])
            self.ops.set_metric("active_model_challenger", 1.0 if active_model_name == "challenger" else 0.0)

        def _emit_alert_limited(name: str, reason: str, *, cooldown_steps: int = alert_cooldown_steps) -> None:
            last = last_alert_step.get(name, -10**9)
            if steps - last < cooldown_steps:
                return
            last_alert_step[name] = steps
            self.ops.emit_alert(name, reason)

        def _tune_execution_params(*, force: bool = False) -> None:
            nonlocal self_tuner_size_scale, min_order_notional_quote_live
            if not self_tuner_enabled:
                return
            if not force and steps % self_tuner_every_steps != 0:
                return
            n = len(tune_window)
            if n < self_tuner_min_samples:
                return

            submitted = 0
            insufficient = 0
            min_order_blocks = 0
            rate_limits = 0
            for row in tune_window:
                status = str(row.get("status", "")).lower()
                reason = str(row.get("reason", "")).lower()
                if status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
                    submitted += 1
                if "insufficient_balance" in reason or "insufficient funds" in reason:
                    insufficient += 1
                if "min_order_block" in reason:
                    min_order_blocks += 1
                if "rate_limit" in reason:
                    rate_limits += 1

            n_f = float(max(n, 1))
            submitted_rate = submitted / n_f
            insufficient_rate = insufficient / n_f
            min_order_block_rate = min_order_blocks / n_f
            rate_limit_rate = rate_limits / n_f

            prev_scale = self_tuner_size_scale
            prev_floor = min_order_notional_quote_live

            if insufficient_rate >= 0.25:
                self_tuner_size_scale *= 0.85
            elif rate_limit_rate >= 0.12:
                self_tuner_size_scale *= 0.90
            elif submitted_rate >= 0.30 and insufficient_rate < 0.10 and rate_limit_rate < 0.08:
                self_tuner_size_scale *= 1.06

            if min_order_block_rate >= 0.18:
                min_order_notional_quote_live += 0.25
            elif min_order_block_rate <= 0.03 and submitted_rate < 0.10 and insufficient_rate < 0.12:
                min_order_notional_quote_live -= 0.10

            self_tuner_size_scale = max(self_tuner_size_scale_min, min(self_tuner_size_scale_max, self_tuner_size_scale))
            min_order_notional_quote_live = max(self_tuner_floor_min, min(self_tuner_floor_max, min_order_notional_quote_live))

            self.ops.set_metric("self_tuner_size_scale", self_tuner_size_scale)
            self.ops.set_metric("self_tuner_min_order_notional_quote", min_order_notional_quote_live)
            self.ops.set_metric("self_tuner_submitted_rate", submitted_rate)
            self.ops.set_metric("self_tuner_insufficient_rate", insufficient_rate)
            self.ops.set_metric("self_tuner_min_order_block_rate", min_order_block_rate)
            self.ops.set_metric("self_tuner_rate_limit_rate", rate_limit_rate)
            self.ops.set_metric("self_tuner_window_events", float(n))

            if abs(self_tuner_size_scale - prev_scale) > 1e-9 or abs(min_order_notional_quote_live - prev_floor) > 1e-9:
                self.ops.audit_event(
                    "self_tuner_update",
                    {
                        "window_events": n,
                        "submitted_rate": submitted_rate,
                        "insufficient_rate": insufficient_rate,
                        "min_order_block_rate": min_order_block_rate,
                        "rate_limit_rate": rate_limit_rate,
                        "size_scale_prev": prev_scale,
                        "size_scale_new": self_tuner_size_scale,
                        "min_order_notional_prev": prev_floor,
                        "min_order_notional_new": min_order_notional_quote_live,
                    },
                )
                try:
                    with open(tuning_state_path, "w", encoding="utf-8") as fh:
                        json.dump(
                            {
                                "ts": time.time(),
                                "size_scale": float(self_tuner_size_scale),
                                "min_order_notional_quote": float(min_order_notional_quote_live),
                                "submitted_rate": float(submitted_rate),
                                "insufficient_rate": float(insufficient_rate),
                                "min_order_block_rate": float(min_order_block_rate),
                                "rate_limit_rate": float(rate_limit_rate),
                            },
                            fh,
                            sort_keys=True,
                            indent=2,
                        )
                except Exception:
                    pass

        self.ops.set_metric("guards_fatal_only", 1.0 if fatal_only_mode else 0.0)
        self.ops.set_metric("self_tuner_size_scale", self_tuner_size_scale)
        self.ops.set_metric("self_tuner_min_order_notional_quote", min_order_notional_quote_live)
        self.ops.audit_event("live_loop_start", {"mode": mode.value, "symbol": symbol, "poll_s": poll_s, "max_steps": max_steps, "guards_mode": guards_mode})
        self._write_runtime_health(
            status="running",
            reason="live_loop_start",
            extra={
                "symbol": symbol,
                "mode": mode.value,
                "order_submission_interval_s": order_submission_interval_s,
            },
        )
        _sync_runtime_adapters(time.time())
        orders_counter_minute = int(time.time() // 60)
        while True:
            steps += 1
            now_ts = time.time()
            now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            now_minute = int(now_ts // 60)
            _sync_runtime_adapters(now_ts)
            self._write_runtime_health(
                status="running",
                extra={
                    "step": steps,
                    "symbol": symbol,
                    "mode": mode.value,
                },
            )
            if now_minute != orders_counter_minute:
                self.risk.reset_periodic_limits(reset_orders=True)
                orders_counter_minute = now_minute

            if audit_enabled and now_ts >= next_health_audit_ts:
                audit_report = self.health_audit_110.audit_and_repair(
                    symbol=symbol,
                    mode=mode.value,
                    live=live,
                    sqlite=self.sqlite,
                    ops=self.ops,
                    submission_scheduler=submission_scheduler,
                    order_submission_interval_s=order_submission_interval_s,
                    risk_engine=self.risk,
                    latest_feed_quotes=latest_feed_quotes,
                    latest_feed_quality=(latest_feed_quality if isinstance(latest_feed_quality, dict) else {}),
                    safe_probe_submitter=lambda reason: _submit_safe_probe_from_audit(reason, audit110=True),
                    now_ts=now_ts,
                )
                next_health_audit_ts = now_ts + audit_interval_s
                last_audit_failed_checks = list(audit_report.failed_checks)
                self.ops.set_metric("last_audit_ts", float(audit_report.ts))
                self.ops.set_metric("health_score", float(audit_report.health_score))
                self.ops.set_metric("health_audit_110_score", float(audit_report.health_score))
                self.ops.set_metric("health_audit_110_ok", 1.0 if audit_report.ok else 0.0)
                self.ops.set_metric("health_audit_110_failed_checks", float(len(audit_report.failed_checks)))
                self.ops.set_metric("health_audit_110_repairs", float(len(audit_report.repair_actions_taken)))
                self.ops.audit_event("health_audit_110", audit_report.to_dict())
                self._record_module_event(
                    module="health_audit_110",
                    action="run",
                    reason="ok" if audit_report.ok else "failed",
                    symbol=symbol,
                    payload={
                        "health_score": float(audit_report.health_score),
                        "failed_checks": list(audit_report.failed_checks),
                        "repairs": list(audit_report.repair_actions_taken),
                    },
                )
                self._write_runtime_health(
                    status="running" if audit_report.ok else "degraded",
                    reason="health_audit_110",
                    extra={
                        "health_score": float(audit_report.health_score),
                        "failed_checks": list(audit_report.failed_checks),
                        "repair_actions_taken": list(audit_report.repair_actions_taken),
                    },
                )
                if audit_report.ok:
                    audit_pause_new_risk_until_ts = 0.0
                    last_audit_failed_checks = []
                    block_new_entries_until_health_ok = False
                    failed_probe_streak = 0
                    if hasattr(live, "set_health_ok"):
                        try:
                            live.set_health_ok(True)
                        except Exception:
                            pass
                else:
                    audit_pause_new_risk_until_ts = max(
                        audit_pause_new_risk_until_ts,
                        now_ts + audit_pause_openings_s,
                    )
                    if hasattr(live, "set_exits_only_mode"):
                        try:
                            live.set_exits_only_mode(
                                reason="health_audit_110_failed",
                                duration_s=audit_pause_openings_s,
                            )
                        except Exception:
                            pass
                if audit_report.restart_required:
                    self._write_runtime_health(
                        status="restarting",
                        reason="health_audit_110_full_restart_required",
                        extra={
                            "failed_checks": list(audit_report.failed_checks),
                            "repair_actions_taken": list(audit_report.repair_actions_taken),
                        },
                    )
                    raise RuntimeError("health_audit_110_full_restart_required")

            if os.path.exists(self._kill_file_path()):
                if hasattr(live, "request_kill"):
                    live.request_kill("kill_file_detected")
                flattened = None
                if hasattr(live, "flatten_all_positions"):
                    try:
                        flattened = live.flatten_all_positions()
                    except Exception as exc:  # pragma: no cover
                        flattened = (False, f"flatten_error:{exc}")
                self.ops.audit_event("kill_file", {"flattened": flattened})
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                self._write_runtime_health(
                    status="stopped",
                    reason="kill_file_detected",
                    extra={"step": steps, "symbol": symbol},
                )
                return {"status": "stopped", "mode": mode.value, "reason": "kill_file_detected", "steps": steps, "flattened": flattened}

            stuck_snapshot = self.stuck_governor.state_snapshot(now_ts=now_ts)
            stuck_symbols = {sym for sym, row in stuck_snapshot.items() if bool(row.get("entries_paused", False))}
            capital_unlock = self.capital_unlock_manager.evaluate(
                now_ts=now_ts,
                base_topk=symbol_topk,
                exposure_by_symbol_quote=(symbol_exposure_quote if symbol_exposure_quote else {symbol: abs(exposure_notional)}),
                position_age_by_symbol_s=symbol_position_age_s,
                stuck_symbols=stuck_symbols,
                total_capital_quote=max(base_budget, base_budget + abs(exposure_notional)),
            )
            runtime_symbol_topk = int(capital_unlock.recommended_topk if capital_unlock.redirect_mode else symbol_topk)
            capital_unlock_reason = str(capital_unlock.reason)
            capital_unlock_entry_scale = float(capital_unlock.symbol_entry_scale.get(str(symbol).upper(), 1.0))
            self.ops.set_metric("capital_unlock_redirect_mode", 1.0 if capital_unlock.redirect_mode else 0.0)
            self.ops.set_metric("capital_unlock_locked_exposure_ratio", float(capital_unlock.locked_exposure_ratio))
            self.ops.set_metric("capital_unlock_median_stuck_hold_s", float(capital_unlock.median_stuck_hold_s))
            self.ops.set_metric("capital_unlock_topk", float(runtime_symbol_topk))
            self._record_module_event(
                module="capital_unlock_manager",
                action="evaluate",
                reason=capital_unlock_reason,
                symbol=symbol,
                payload={
                    "redirect_mode": bool(capital_unlock.redirect_mode),
                    "locked_exposure_ratio": float(capital_unlock.locked_exposure_ratio),
                    "median_stuck_hold_s": float(capital_unlock.median_stuck_hold_s),
                    "topk": int(runtime_symbol_topk),
                },
            )

            if dynamic_portfolio and len(symbol_candidates) > 1 and (steps == 1 or steps % reselect_every_steps == 0):
                best_symbol = symbol
                best_score = symbol_scores.get(symbol, -10**9)
                current_score = symbol_scores.get(symbol, -10**9)
                optimizer_candidates: dict[str, dict[str, float | str]] = {}
                ranked_universe = sorted(
                    symbol_candidates,
                    key=lambda s: float(symbol_scores.get(s, 0.0)),
                    reverse=True,
                )
                top_universe = ranked_universe[: max(1, min(runtime_symbol_topk, len(ranked_universe)))]
                if symbol not in top_universe:
                    top_universe = [symbol, *top_universe]
                dedup_top: list[str] = []
                seen_top: set[str] = set()
                for s in top_universe:
                    if s in seen_top:
                        continue
                    dedup_top.append(s)
                    seen_top.add(s)
                candidate_pool = dedup_top if dedup_top else list(symbol_candidates)
                scan_batch = min(len(candidate_pool), max(1, portfolio_scan_batch))
                if len(candidate_pool) <= scan_batch:
                    scan_symbols = list(candidate_pool)
                else:
                    scan_step = max(0, (steps - 1) // reselect_every_steps)
                    start = (scan_step * scan_batch) % len(candidate_pool)
                    scan_symbols = [candidate_pool[(start + i) % len(candidate_pool)] for i in range(scan_batch)]
                    if symbol not in scan_symbols:
                        scan_symbols[0] = symbol
                self.ops.set_metric("portfolio_scan_symbols", float(len(scan_symbols)))
                self.ops.set_metric("portfolio_universe_size", float(len(symbol_candidates)))
                self.ops.set_metric("portfolio_topk_size", float(len(candidate_pool)))
                for sym in scan_symbols:
                    try:
                        if self.settings.live_provider() == "kraken_spot" and hasattr(live, "market_snapshot"):
                            snap_sym = live.market_snapshot(sym, max_age_s=max(0.5, poll_s * 1.5))
                            sbid = float(snap_sym.get("bid", 0.0) or 0.0)
                            sask = float(snap_sym.get("ask", 0.0) or 0.0)
                            sbq = float(snap_sym.get("bid_qty", 0.0) or 0.0)
                            saq = float(snap_sym.get("ask_qty", 0.0) or 0.0)
                            if sbq <= 0.0:
                                sbq = 1.0
                            if saq <= 0.0:
                                saq = 1.0
                        elif self.settings.live_provider() == "kraken_spot":
                            ticker_sym = live.connector.ticker(sym)  # type: ignore[attr-defined]
                            row_sym = ticker_sym.get(sym) if isinstance(ticker_sym, dict) else None
                            if not row_sym and isinstance(ticker_sym, dict) and ticker_sym:
                                row_sym = next(iter(ticker_sym.values()))
                            if not isinstance(row_sym, dict):
                                continue
                            bid_raw = row_sym.get("b", 0)
                            ask_raw = row_sym.get("a", 0)
                            sbid = float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw or 0.0)
                            sask = float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw or 0.0)
                            sbq = 1.0
                            saq = 1.0
                        else:
                            book_sym = live.connector.book_ticker(sym)  # type: ignore[attr-defined]
                            sbid = float(book_sym.get("bidPrice", 0.0))
                            sask = float(book_sym.get("askPrice", 0.0))
                            sbq = float(book_sym.get("bidQty", 0.0))
                            saq = float(book_sym.get("askQty", 0.0))
                        if sbid <= 0.0 or sask <= 0.0:
                            continue
                        smid = (sbid + sask) / 2.0
                        sspread_bps = ((sask - sbid) / max(smid, 1e-9)) * 10000.0
                        sdepth = (sbid * max(sbq, 0.0)) + (sask * max(saq, 0.0))
                        ph = price_histories.setdefault(sym, [])
                        ph.append(smid)
                        ph[:] = ph[-32:]
                        ret_1_sym = 0.0 if len(ph) <= 2 else (ph[-1] / ph[-3] - 1.0)
                        ret_3_sym = 0.0 if len(ph) <= 10 else (ph[-1] / ph[-11] - 1.0)
                        rh = return_histories.setdefault(sym, [])
                        rh.append(ret_1_sym)
                        rh[:] = rh[-64:]
                        mean_sym = sum(ph) / len(ph)
                        rv_sym = 0.0 if mean_sym <= 0 else ((sum((p - mean_sym) ** 2 for p in ph) / len(ph)) ** 0.5) / mean_sym
                        score = self._portfolio_symbol_score(
                            ret_1=ret_1_sym,
                            ret_3=ret_3_sym,
                            spread_bps=sspread_bps,
                            depth_notional=sdepth,
                            rv=rv_sym,
                            existing_exposure=exposure_notional if sym == symbol else 0.0,
                        )
                        cluster = sym[-3:] if len(sym) >= 3 else "misc"
                        edge_proxy_bps = max(
                            0.0,
                            ret_1_sym * 6500.0 + ret_3_sym * 3500.0 - sspread_bps * 0.25 - rv_sym * 10000.0 * 0.08,
                        )
                        optimizer_candidates[sym] = {
                            "edge_bps": edge_proxy_bps,
                            "realized_vol": rv_sym,
                            "spread_bps": sspread_bps,
                            "depth_notional": sdepth,
                            "liquidity_score": max(0.2, min(2.0, (sdepth ** 0.5) / 250.0)),
                            "cluster": cluster,
                        }
                        symbol_scores[sym] = score
                        if score > best_score:
                            best_score = score
                            best_symbol = sym
                    except Exception as exc:
                        self.ops.audit_event("portfolio_score_error", {"symbol": sym, "error": str(exc)})

                if optimizer_candidates:
                    corr = self._correlation_matrix({k: return_histories.get(k, []) for k in optimizer_candidates})
                    cluster_caps = {str(v.get("cluster", "default")): portfolio_cluster_cap for v in optimizer_candidates.values()}
                    optimized = self.portfolio_optimizer.optimize(
                        optimizer_candidates,
                        corr=corr,
                        current_weights=portfolio_weights,
                        turnover_penalty=portfolio_turnover_penalty,
                        cluster_caps=cluster_caps,
                    )
                    portfolio_weights = dict(optimized.weights)
                    self.ops.set_metric("portfolio_turnover", optimized.turnover)
                    self.ops.set_metric("portfolio_cluster_count", float(len(optimized.cluster_exposure)))
                    if portfolio_weights:
                        self.ops.set_metric("portfolio_weight_current_symbol", float(portfolio_weights.get(symbol, 0.0)))
                        weighted_best = max(portfolio_weights.items(), key=lambda kv: kv[1])[0]
                        weighted_best_score = float(symbol_scores.get(weighted_best, -10**9))
                        if weighted_best_score > best_score - 1e-9:
                            best_symbol = weighted_best
                            best_score = weighted_best_score

                if (
                    best_symbol != symbol
                    and abs(exposure_notional) <= switch_only_when_flat_notional
                    and best_score >= current_score + min_symbol_score_gap
                ):
                    prev_symbol = symbol
                    symbol = best_symbol
                    last_mid = None
                    self.ops.audit_event(
                        "portfolio_switch",
                        {
                            "from_symbol": prev_symbol,
                            "to_symbol": symbol,
                            "from_score": current_score,
                            "to_score": best_score,
                            "steps": steps,
                        },
                    )

            selected_quote: VenueQuote | None = None
            try:
                if self.settings.live_provider() == "kraken_spot":
                    if hasattr(live, "market_snapshot"):
                        snap = live.market_snapshot(symbol, max_age_s=max(0.5, poll_s * 1.5))
                        bid = float(snap.get("bid", 0.0) or 0.0)
                        ask = float(snap.get("ask", 0.0) or 0.0)
                        bid_qty = float(snap.get("bid_qty", 0.0) or 0.0)
                        ask_qty = float(snap.get("ask_qty", 0.0) or 0.0)
                        if bid_qty <= 0.0:
                            bid_qty = 1.0
                        if ask_qty <= 0.0:
                            ask_qty = 1.0
                    else:
                        ticker_data = live.connector.ticker(symbol)  # type: ignore[attr-defined]
                        row = ticker_data.get(symbol) if isinstance(ticker_data, dict) else None
                        if not row and isinstance(ticker_data, dict) and ticker_data:
                            row = next(iter(ticker_data.values()))
                        if not isinstance(row, dict):
                            raise ValueError("ticker_row_missing")
                        bid_raw = row.get("b", 0)
                        ask_raw = row.get("a", 0)
                        bid = float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw or 0.0)
                        ask = float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw or 0.0)
                        bid_qty = float(bid_raw[1] if isinstance(bid_raw, list) and len(bid_raw) > 1 else 0.0)
                        ask_qty = float(ask_raw[1] if isinstance(ask_raw, list) and len(ask_raw) > 1 else 0.0)
                        if bid_qty <= 0.0:
                            bid_qty = 1.0
                        if ask_qty <= 0.0:
                            ask_qty = 1.0
                else:
                    book = live.connector.book_ticker(symbol)  # type: ignore[attr-defined]
                    bid = float(book.get("bidPrice", 0.0))
                    ask = float(book.get("askPrice", 0.0))
                    bid_qty = float(book.get("bidQty", 0.0))
                    ask_qty = float(book.get("askQty", 0.0))
            except Exception as exc:
                self.ops.audit_event("book_error", {"symbol": symbol, "error": str(exc)})
                self.ops.inc_metric("book_errors_total")
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                time.sleep(poll_s)
                continue

            # Multi-venue feed scoring with fallback selection.
            if hasattr(live, "venue_for_symbol"):
                try:
                    primary_venue = str(live.venue_for_symbol(symbol))
                except Exception:
                    primary_venue = "kraken_spot" if self.settings.live_provider() == "kraken_spot" else "binance_um_perps"
            else:
                primary_venue = "kraken_spot" if self.settings.live_provider() == "kraken_spot" else "binance_um_perps"
            connectors: dict[str, object] = {}
            if hasattr(live, "connectors_for_symbol"):
                try:
                    connectors = dict(live.connectors_for_symbol(symbol))
                except Exception:
                    connectors = {}
            if not connectors:
                if self.settings.live_provider() == "kraken_spot":
                    connectors = {primary_venue: live}
                else:
                    connectors = {primary_venue: getattr(live, "connector", live)}
            ws_healthy = True
            try:
                quotes = self.market_data.collect_quotes(symbol, connectors)
                selected_quote, quality_map, fallback_used = self.market_data.choose_with_fallback(
                    primary_venue,
                    quotes,
                    now_ts=now_ts,
                    min_primary_score=max(5.0, float(os.getenv("AUTONOMOUS_MIN_PRIMARY_FEED_SCORE", "25.0") or "25.0")),
                )
                latest_feed_quotes = list(quotes)
                latest_feed_quality = {k: {"score": v.score, "stale": v.stale, "clock_drift_ms": v.clock_drift_ms, "reasons": v.reasons} for k, v in quality_map.items()}
                ws_integrity_snapshot = self.ws_integrity.observe_cycle(
                    quotes=latest_feed_quotes,
                    quality=latest_feed_quality,
                    now_ts=now_ts,
                )
                self.ops.set_metric("ws_integrity_ok", 1.0 if ws_integrity_snapshot.get("healthy", False) else 0.0)
                self.ops.set_metric(
                    "ws_integrity_stream_count",
                    float(len(ws_integrity_snapshot.get("streams", {}))),
                )
                ws_healthy = bool(ws_integrity_snapshot.get("healthy", False))
                if not ws_healthy:
                    self._record_module_event(
                        module="ws_integrity_guard",
                        action="degraded",
                        reason="ws_integrity_degraded",
                        symbol=symbol,
                        payload={"snapshot": ws_integrity_snapshot},
                    )
                    audit_pause_new_risk_until_ts = max(audit_pause_new_risk_until_ts, now_ts + max(60.0, poll_s * 4.0))
                    last_audit_failed_checks = ["ws_integrity_guard"]
                    if hasattr(live, "set_exits_only_mode"):
                        try:
                            live.set_exits_only_mode(
                                reason="ws_integrity_degraded",
                                duration_s=max(60.0, poll_s * 4.0),
                            )
                        except Exception:
                            pass
                elif hasattr(live, "set_health_ok"):
                    self._record_module_event(
                        module="ws_integrity_guard",
                        action="healthy",
                        reason="ws_integrity_ok",
                        symbol=symbol,
                        payload={"snapshot": ws_integrity_snapshot},
                    )
                    try:
                        live.set_health_ok(True)
                    except Exception:
                        pass
                if selected_quote is not None:
                    bid = float(selected_quote.bid)
                    ask = float(selected_quote.ask)
                    if selected_quote.depth_notional > 0:
                        depth_notional = float(selected_quote.depth_notional)
                    self.market_data.update_clock_drift(selected_quote.venue, selected_quote.ts * 1000.0, now_ts=now_ts)
                    selected_quality = quality_map.get(selected_quote.venue)
                    if selected_quality is not None:
                        self.market_data.append_tick(selected_quote, selected_quality)
                        self.ops.set_metric("feed_quality_selected", selected_quality.score)
                        self.ops.set_metric("clock_drift_ms", abs(selected_quality.clock_drift_ms))
                    primary_quality = quality_map.get(primary_venue)
                    self.ops.set_metric("feed_quality_primary", 0.0 if primary_quality is None else primary_quality.score)
                    self.ops.set_metric("feed_fallback_active", 1.0 if fallback_used else 0.0)
            except Exception as exc:
                self.ops.audit_event("market_data_engine_error", {"symbol": symbol, "error": str(exc)})
                ws_healthy = False

            if bid <= 0 or ask <= 0:
                self.ops.audit_event("book_invalid", {"symbol": symbol, "bid": bid, "ask": ask})
                self.ops.inc_metric("book_invalid_total")
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                time.sleep(poll_s)
                continue

            mid = (bid + ask) / 2.0
            spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0
            depth_notional = (bid * max(bid_qty, 0.0)) + (ask * max(ask_qty, 0.0))
            if selected_quote is not None and selected_quote.depth_notional > 0:
                depth_notional = max(depth_notional, float(selected_quote.depth_notional))
            tox = self.toxicity.update(
                symbol=symbol,
                ts=now_ts,
                mid=mid,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
            )
            toxicity_score_value = float(tox.score)
            toxicity_throttle_active = toxicity_score_value >= toxicity_threshold
            if toxicity_throttle_active:
                toxicity_freeze_until_ts = max(toxicity_freeze_until_ts, now_ts + toxicity_cooldown_s)
            self.ops.set_metric("toxicity_score", toxicity_score_value)
            self.ops.set_metric("toxicity_throttle", 1.0 if toxicity_throttle_active or now_ts < toxicity_freeze_until_ts else 0.0)
            prices.append(mid)
            prices = prices[-64:]
            if primary_venue == "kraken_spot":
                fast_hops = 2
                medium_hops = 12
            else:
                fast_hops = 1
                medium_hops = 3
            ret_1 = 0.0 if len(prices) <= fast_hops else (prices[-1] / prices[-1 - fast_hops] - 1.0)
            ret_3 = 0.0 if len(prices) <= medium_hops else (prices[-1] / prices[-1 - medium_hops] - 1.0)
            mean = sum(prices) / len(prices)
            rv = 0.0 if mean <= 0 else ((sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5) / mean
            z_proxy = 0.0 if rv <= 1e-9 else (mid - mean) / (mean * rv + 1e-9)
            flow_imbalance = (bid_qty - ask_qty) / max(bid_qty + ask_qty, 1e-9)
            if self.settings.live_provider() == "kraken_spot" and self.settings.canary_mode:
                # Spot canary uses a slightly longer micro-trend horizon to produce testable intents under TCO.
                ret_1 *= 10.0
                ret_3 *= 18.0
                z_proxy *= 3.0
            features = {
                "ret_1": ret_1,
                "ret_3": ret_3,
                "pairs_zscore": z_proxy,
                "realized_vol": rv,
                "atr_proxy": spread_bps / 10000.0,
                "spread_proxy": spread_bps / 10000.0,
                "funding_rate": 0.0,
                "oi": 0.0,
                "liquidations": 0.0,
                "depth_notional": depth_notional,
                "orderbook_imbalance": flow_imbalance,
                "microprice_proxy": mid,
                "flow_imbalance": flow_imbalance,
                "mark_price": mid,
                "spot_price_proxy": 0.0,
            }
            if not feature_schema_registered:
                self.research.register_feature_schema(self.features.feature_version, list(features.keys()))
                feature_schema_registered = True
            parity_ok, parity_issues = self.research.assert_online_offline_parity(
                self.features.feature_version,
                online_features=features,
                offline_features=dict(features),
            )
            if not parity_ok:
                self.ops.audit_event("feature_parity_violation", {"issues": parity_issues[:10]})
                self.ops.inc_metric("feature_parity_fail_total")
            leak_ok, leak_reason = self.research.leakage_test(now_dt, now_dt)
            if not leak_ok:
                self.ops.audit_event("feature_leakage", {"reason": leak_reason})
                self.ops.inc_metric("feature_leakage_total")
            fv = FeatureVector(symbol=symbol, ts=now_dt, feature_version=self.features.feature_version, values=features)
            if model_last_mid > 0:
                realized_ret_bps = ((mid / max(model_last_mid, 1e-9)) - 1.0) * 10000.0
                for model_name in ("champion", "challenger"):
                    direction = 1.0 if model_last_mu.get(model_name, 0.0) >= 0 else -1.0
                    model_scores[model_name] = model_scores[model_name] * 0.995 + direction * realized_ret_bps
            model_last_mid = mid

            fc_champion = self.models.forecast(fv)
            fc_challenger = self._challenger_forecast(fv, fc_champion)
            model_last_mu["champion"] = fc_champion.mu
            model_last_mu["challenger"] = fc_challenger.mu
            self.ops.set_metric("model_uncertainty_penalty", float(fc_champion.diagnostics.get("uncertainty_penalty", 0.0)))
            self.ops.set_metric("model_ensemble_dispersion", float(fc_champion.diagnostics.get("ensemble_dispersion", 0.0)))
            if challenger_enabled and steps >= challenger_warmup_steps and model_scores["challenger"] > model_scores["champion"] + challenger_margin:
                fc = fc_challenger
                active_model_name = "challenger"
            else:
                fc = fc_champion
                active_model_name = "champion"
            gov_model_gate = self.governance.champion_challenger_gate(
                champion_score=model_scores["champion"],
                challenger_score=model_scores["challenger"],
                promotion_margin=challenger_margin,
                oos_gate_passed=oos_gate_live_pass,
            )
            if active_model_name == "challenger" and not gov_model_gate.allowed:
                active_model_name = "champion"
                fc = fc_champion
            if active_model_name != last_active_model_name:
                self.ops.audit_event(
                    "model_switch",
                    {
                        "from_model": last_active_model_name,
                        "to_model": active_model_name,
                        "champion_score": model_scores["champion"],
                        "challenger_score": model_scores["challenger"],
                        "steps": steps,
                    },
                )
                last_active_model_name = active_model_name

            live_state: dict[str, object] = {}
            try:
                live_state = _sync_live_fill_state(mid)
            except Exception as exc:
                self.ops.audit_event("fill_sync_error", {"symbol": symbol, "error": str(exc)})

            if not live_state and last_mid is not None and abs(exposure_notional) > 1e-9:
                pnl = signed_exposure_notional * ((mid / max(last_mid, 1e-9)) - 1.0)
                equity += pnl / base_budget
                self.risk.record_return((pnl / max(abs(exposure_notional), 1.0)) * 100.0)
            last_mid = mid
            peak = max(peak, equity)
            drawdown_pct = (equity / peak - 1.0) * 100.0
            daily_loss_pct = min(0.0, (equity - 1.0) * 100.0)

            if hasattr(live, "reconcile_live_state"):
                try:
                    last_recon_ok, recon_reason = live.reconcile_live_state(internal_exposure=abs(exposure_notional))
                    if not last_recon_ok:
                        self.ops.audit_event("reconcile", {"ok": False, "reason": recon_reason})
                        self.ops.inc_metric("reconciliation_mismatch_total")
                except Exception as exc:
                    last_recon_ok = False
                    self.ops.audit_event("reconcile_error", {"error": str(exc)})

            self.ops.set_metric("mid_price", mid)
            self.ops.set_metric("spread_bps", spread_bps)
            self.ops.set_metric("depth_notional", depth_notional)
            self.ops.set_metric("portfolio_symbol_score", symbol_scores.get(symbol, 0.0))
            self.ops.set_metric("equity", equity)
            drawdown_abs = max(0.0, (1.0 - (equity / max(peak, 1e-9))) * 100.0)
            self.ops.set_metric("drawdown", drawdown_abs)
            self.ops.set_metric("exposure_notional", abs(exposure_notional))
            self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
            max_drawdown_seen = max(max_drawdown_seen, drawdown_abs)
            quote_free = base_budget
            quote_total = base_budget
            margin_used = 0.0
            try:
                if hasattr(live, "_available_quote_balance"):
                    _ccy, quote_free = live._available_quote_balance(symbol)  # type: ignore[attr-defined]
                    quote_total = max(quote_total, quote_free + abs(signed_exposure_notional))
            except Exception:
                pass
            treasury_decision = self.treasury.evaluate(
                quote_free=float(quote_free),
                quote_total=float(quote_total),
                margin_used=float(margin_used),
                open_notional=abs(exposure_notional),
                drawdown_pct=drawdown_pct,
            )
            self.ops.set_metric("treasury_throttle", treasury_decision.throttle_scale)
            self.ops.set_metric("treasury_reserve_ratio", treasury_decision.reserve_ratio)
            self.ops.set_metric("treasury_margin_buffer", treasury_decision.margin_buffer)

            if exposure_notional > 1e-9:
                if position_open_ts is None:
                    position_open_ts = now_ts
                    position_peak_net_pnl_quote = last_net_pnl_quote
                else:
                    position_peak_net_pnl_quote = max(position_peak_net_pnl_quote, last_net_pnl_quote)
            else:
                position_open_ts = None
                position_peak_net_pnl_quote = 0.0
            position_age_s = max(0.0, now_ts - float(position_open_ts or now_ts)) if position_open_ts is not None else 0.0
            unrealized_pnl_ratio = 0.0 if exposure_notional <= 1e-9 else (last_net_pnl_quote / max(exposure_notional, 1e-9))
            symbol_exposure_quote[str(symbol).upper()] = float(abs(exposure_notional))
            symbol_position_age_s[str(symbol).upper()] = float(position_age_s)
            stuck_decision = self.stuck_governor.observe(
                symbol=symbol,
                now_ts=now_ts,
                has_position=bool(exposure_notional > 1e-9),
                position_age_s=position_age_s,
                unrealized_pnl_ratio=unrealized_pnl_ratio,
            )
            stuck_decision_reason = str(stuck_decision.reason)
            self.ops.set_metric("stuck_active", 1.0 if stuck_decision.stuck else 0.0)
            self.ops.set_metric("stuck_entries_paused", 1.0 if stuck_decision.entries_paused else 0.0)
            self.ops.set_metric("stuck_blocked_sell_count", float(stuck_decision.blocked_sell_count))
            self._record_module_event(
                module="stuck_position_governor",
                action="observe",
                reason=stuck_decision_reason,
                symbol=symbol,
                payload={
                    "stuck": bool(stuck_decision.stuck),
                    "entries_paused": bool(stuck_decision.entries_paused),
                    "blocked_sell_count": int(stuck_decision.blocked_sell_count),
                    "position_age_s": float(position_age_s),
                    "unrealized_pnl_ratio": float(unrealized_pnl_ratio),
                },
            )
            if stuck_decision.exits_only and hasattr(live, "set_exits_only_mode"):
                try:
                    live.set_exits_only_mode(
                        reason=f"stuck_governor:{stuck_decision_reason}",
                        duration_s=max(120.0, float(getattr(stuck_decision, "entries_paused_until_ts", now_ts) - now_ts)),
                    )
                except Exception:
                    pass

            # Hedge OPEN only (no forced close). Close path remains ProfitGate-gated in execution services.
            if stuck_decision.stuck and bool(getattr(self.hedge_manager.config, "enabled", False)):
                sym_n = str(symbol or "").upper().replace("/", "")
                hedge_symbol = ""
                if sym_n.startswith("PI_"):
                    hedge_symbol = sym_n
                else:
                    base = ""
                    for quote in ("USD", "USDT", "EUR"):
                        if sym_n.endswith(quote) and len(sym_n) > len(quote):
                            base = sym_n[: -len(quote)]
                            break
                    if base:
                        hedge_symbol = f"PI_{base}USD"
                perps_available = False
                if hedge_symbol and hasattr(live, "market_type_for_symbol"):
                    try:
                        perps_available = str(live.market_type_for_symbol(hedge_symbol)).lower() == "perp"
                    except Exception:
                        perps_available = False
                hedge_decision = self.hedge_manager.maybe_open_hedge(
                    symbol=symbol,
                    perps_symbol=hedge_symbol,
                    spot_signed_exposure_quote=signed_exposure_notional,
                    unrealized_pnl_ratio=unrealized_pnl_ratio,
                    pressure=float(stuck_decision.hedge_pressure),
                    funding_rate=0.0,
                    funding_eta_s=None,
                    now_ts=now_ts,
                    perps_available=perps_available,
                )
                self._record_module_event(
                    module="hedge_manager",
                    action="evaluate",
                    reason=str(hedge_decision.reason),
                    symbol=symbol,
                    payload={"perps_symbol": hedge_symbol, "perps_available": bool(perps_available)},
                )
                if hedge_decision.should_open and hedge_decision.action is not None:
                    hedge_action = hedge_decision.action
                    hedge_intent = OrderIntent(
                        symbol=hedge_action.symbol,
                        side=hedge_action.side,
                        target_notional=float(hedge_action.target_notional_quote),
                        why={
                            "hedge_manager": {
                                "reason": hedge_action.reason,
                                **dict(hedge_action.metadata),
                            },
                            "execution_route": {"order_type": "maker"},
                        },
                    )
                    hedge_result = self.execution.execute_live(hedge_intent)
                    self.ops.audit_event(
                        "hedge_action",
                        {
                            "symbol": symbol,
                            "hedge_symbol": hedge_action.symbol,
                            "hedge_side": hedge_action.side,
                            "hedge_notional_quote": hedge_action.target_notional_quote,
                            "status": hedge_result.status,
                            "reason": hedge_result.reason,
                        },
                    )
                    self._record_module_event(
                        module="hedge_manager",
                        action="open_tranche",
                        reason=str(hedge_action.reason),
                        symbol=symbol,
                        payload={
                            "hedge_symbol": hedge_action.symbol,
                            "hedge_side": hedge_action.side,
                            "target_notional_quote": float(hedge_action.target_notional_quote),
                            "status": str(hedge_result.status),
                            "result_reason": str(hedge_result.reason),
                        },
                    )
                    if str(hedge_result.reason).lower().find("rate_limit") >= 0:
                        self.rate_limit_governor.record_error(
                            endpoint="hedge_execution",
                            error_text=str(hedge_result.reason),
                            now_ts=now_ts,
                        )

            intent = self.policy.make_intent(fc, features, self.settings.execution.fee_bps, self.settings.execution.slippage_bps)
            forced_exit_reason = ""
            forced_exit_notional = 0.0
            if exposure_notional > 1e-9 and position_open_ts is not None:
                hold_seconds = now_ts - position_open_ts
                avg_entry_price = float((live_state or {}).get("avg_entry_price", 0.0) or 0.0)
                take_profit_trigger_price = 0.0
                if exit_take_profit_pct > 0.0 and avg_entry_price > 0.0:
                    take_profit_trigger_price = avg_entry_price * (1.0 + (exit_take_profit_pct / 100.0))
                    if bid >= take_profit_trigger_price:
                        forced_exit_reason = "take_profit_target"
                if not forced_exit_reason and hold_seconds >= exit_time_stop_s:
                    if exit_profit_only:
                        if last_net_pnl_quote >= exit_min_profit_quote:
                            forced_exit_reason = "time_stop"
                    elif last_net_pnl_quote <= 0.0:
                        forced_exit_reason = "time_stop"
                elif (
                    not forced_exit_reason
                    and position_peak_net_pnl_quote > 0.0
                    and (position_peak_net_pnl_quote - last_net_pnl_quote) >= exit_trailing_drawdown_quote
                ):
                    forced_exit_reason = "trailing_take_profit"
                elif not forced_exit_reason and rv >= exit_vol_stop_threshold and last_net_pnl_quote < 0.0 and not exit_profit_only:
                    forced_exit_reason = "vol_stop"
                if forced_exit_reason:
                    forced_fraction = exit_partial_fraction
                    if forced_exit_reason == "take_profit_target" and exit_take_profit_full_close:
                        forced_fraction = 1.0
                    forced_exit_notional = max(
                        float((live_state or {}).get("min_trade_notional_quote", 0.0)),
                        exposure_notional * forced_fraction,
                    )
                    self.ops.audit_event(
                        "exit_manager",
                        {
                            "reason": forced_exit_reason,
                            "symbol": symbol,
                            "hold_seconds": hold_seconds,
                            "position_notional": exposure_notional,
                            "peak_net_pnl_quote": position_peak_net_pnl_quote,
                            "net_pnl_quote": last_net_pnl_quote,
                            "forced_notional": forced_exit_notional,
                            "avg_entry_price": avg_entry_price,
                            "take_profit_trigger_price": take_profit_trigger_price,
                            "bid": bid,
                        },
                    )
            if forced_exit_notional > 0.0:
                exit_why = {"exit_manager": {"reason": forced_exit_reason, "forced_notional": forced_exit_notional, "regime": fc.regime}}
                intent = OrderIntent(symbol=symbol, side="sell", target_notional=forced_exit_notional, why=exit_why)
            if intent is not None and str(intent.side).lower() == "buy":
                why_obj = intent.why if isinstance(intent.why, dict) else {}
                components = why_obj.get("components", []) if isinstance(why_obj, dict) else []
                strategy_names: list[str] = []
                if isinstance(components, list):
                    for comp in components:
                        if isinstance(comp, dict):
                            name = str(comp.get("strategy", "") or "").strip().lower()
                            if name and name not in strategy_names:
                                strategy_names.append(name)
                if self.online_validator.symbol_blocked(symbol=symbol, strategies=strategy_names, now_ts=now_ts):
                    self.ops.audit_event(
                        "online_validation_block",
                        {
                            "symbol": symbol,
                            "side": "buy",
                            "strategies": strategy_names,
                            "reason": "validator_cooldown",
                        },
                    )
                    self._record_module_event(
                        module="online_signal_validator",
                        action="block_symbol",
                        reason="validator_cooldown",
                        symbol=symbol,
                        payload={"strategies": strategy_names},
                    )
                    self.stuck_governor.note_validation_underperformance(symbol)
                    intent = None

            if intent is None:
                self.ops.inc_metric("orders_rejected_total")
                orders_rejected += 1.0
                no_intent_debug = dict(getattr(self.policy, "last_no_intent_debug", {}) or {})
                should_force_submit = submission_scheduler.should_submit(now_ts=now_ts)
                should_extra_submit = (not should_force_submit) and _extra_probe_allowed(now_ts)
                if should_force_submit or should_extra_submit:
                    _submit_safe_probe_from_audit(
                        "no_intent_keepalive_submission" if should_force_submit else "extra_activity_submission",
                        from_extra=should_extra_submit,
                    )
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "reason": "no_intent",
                        "regime": fc.regime,
                        "liq_regime": fc.liquidity_regime,
                        "fc_confidence": fc.confidence,
                        "policy_debug": no_intent_debug,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue

            current_signed = signed_exposure_notional
            desired_signed = intent.target_notional if intent.side == "buy" else -intent.target_notional
            adaptive_scale = 1.0
            if adaptive_sizing_enabled:
                if fc.regime == "TREND":
                    adaptive_scale *= 1.15
                elif fc.regime == "PANIC":
                    adaptive_scale *= 0.55
                if fc.liquidity_regime == "THIN":
                    adaptive_scale *= 0.65
                if rv > 0.0:
                    target_rv = max(0.001, float(os.getenv("AUTONOMOUS_ADAPTIVE_TARGET_RV", "0.012") or "0.012"))
                    adaptive_scale *= max(0.5, min(1.2, target_rv / max(rv, 1e-9)))
                cvar_now = 0.0
                if hasattr(self.risk, "_approx_cvar"):
                    try:
                        cvar_now = float(self.risk._approx_cvar())  # type: ignore[attr-defined]
                    except Exception:
                        cvar_now = 0.0
                if cvar_now > 0.0:
                    cvar_target = max(0.25, float(os.getenv("AUTONOMOUS_ADAPTIVE_TARGET_CVAR_PCT", "3.0") or "3.0"))
                    adaptive_scale *= max(0.45, min(1.15, cvar_target / cvar_now))
                if drawdown_abs > 2.0:
                    adaptive_scale *= 0.75
            adaptive_scale *= treasury_decision.throttle_scale
            adaptive_scale = max(adaptive_min_scale, min(adaptive_max_scale, adaptive_scale))
            delta_signed = (desired_signed - current_signed) * adaptive_scale
            desired_signed = current_signed + delta_signed
            self.ops.set_metric("adaptive_size_scale", adaptive_scale)
            if self.settings.live_provider() == "kraken_spot":
                # Kraken spot mode runs unlevered inventory and should not open synthetic shorts.
                desired_signed = max(0.0, desired_signed)
            delta_signed = desired_signed - current_signed
            min_rebalance_notional = max(
                rebalance_deadzone_floor,
                float((live_state or {}).get("min_trade_notional_quote", 0.0)) * rebalance_deadzone_factor,
            )
            if abs(delta_signed) < min_rebalance_notional:
                self.ops.inc_metric("orders_rejected_total")
                orders_rejected += 1.0
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "reason": "rebalance_deadzone",
                        "desired_signed": desired_signed,
                        "current_signed": current_signed,
                        "delta_signed": delta_signed,
                        "min_rebalance_notional": min_rebalance_notional,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue

            rebalance_side = "buy" if delta_signed > 0 else "sell"
            if block_new_entries_until_health_ok and now_ts >= block_new_entries_until_ts:
                block_new_entries_until_health_ok = False
                failed_probe_streak = 0
                if hasattr(live, "set_health_ok"):
                    try:
                        live.set_health_ok(True)
                    except Exception:
                        pass
            if rebalance_side == "buy" and block_new_entries_until_health_ok:
                if submission_scheduler.should_submit(now_ts=now_ts):
                    _submit_safe_probe_from_audit("failed_probe_block_probe")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "reason": "failed_probe_block_new_entries",
                        "failed_probe_streak": failed_probe_streak,
                        "threshold": failed_probe_block_n,
                        "equity": equity,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if rebalance_side == "buy" and now_ts < audit_pause_new_risk_until_ts:
                if submission_scheduler.should_submit(now_ts=now_ts):
                    _submit_safe_probe_from_audit("audit110_pause_new_risk_probe")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "reason": "health_audit_pause_new_risk",
                        "delta_signed": delta_signed,
                        "equity": equity,
                        "failed_checks": list(last_audit_failed_checks),
                        "pause_remaining_s": max(0.0, audit_pause_new_risk_until_ts - now_ts),
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if operator_pause_entries and rebalance_side == "buy":
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "reason": "operator_pause_entries",
                        "delta_signed": delta_signed,
                        "equity": equity,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if rebalance_side == "buy" and bool(stuck_decision.entries_paused):
                if submission_scheduler.should_submit(now_ts=now_ts):
                    _submit_safe_probe_from_audit("stuck_entries_pause_probe")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "reason": "stuck_entries_paused",
                        "stuck_reason": stuck_decision_reason,
                        "entries_paused_until_ts": float(stuck_decision.entries_paused_until_ts),
                        "blocked_sell_count": int(stuck_decision.blocked_sell_count),
                        "equity": equity,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            rebalance_notional = abs(delta_signed) * (self_tuner_size_scale if self_tuner_enabled else 1.0)
            if rebalance_side == "buy" and capital_unlock_entry_scale < 1.0:
                rebalance_notional *= max(0.0, min(1.0, capital_unlock_entry_scale))
                self.ops.audit_event(
                    "capital_unlock_scale",
                    {
                        "symbol": symbol,
                        "reason": capital_unlock_reason,
                        "entry_scale": capital_unlock_entry_scale,
                    },
                )
            if rebalance_side == "buy" and (toxicity_throttle_active or now_ts < toxicity_freeze_until_ts):
                rebalance_notional *= toxicity_throttle_scale
                self.ops.set_metric("toxicity_throttle", 1.0)
                if rebalance_notional <= max(rebalance_deadzone_floor, 0.01):
                    toxicity_freeze_events += 1.0
                    self.ops.audit_event(
                        "heartbeat",
                        {
                            "symbol": symbol,
                            "mid": mid,
                            "spread_bps": spread_bps,
                            "equity": equity,
                            "reason": "toxicity_freeze",
                            "toxicity_score": toxicity_score_value,
                            "cooldown_remaining_s": max(0.0, toxicity_freeze_until_ts - now_ts),
                        },
                    )
                    _update_live_kpis()
                    self.ops.export_prometheus()
                    self.ops.export_dashboard_snapshot()
                    if max_steps and steps >= max_steps:
                        return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                    time.sleep(poll_s)
                    continue
            hard_order_cap_quote = max(0.0, float(os.getenv("AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE", "0") or "0"))
            if hard_order_cap_quote > 0.0 and rebalance_notional > hard_order_cap_quote:
                rebalance_notional = hard_order_cap_quote
            if growth_mode and rebalance_side == "buy" and now_ts < volstop_cooldown_until_ts:
                rebalance_notional *= volstop_throttle_scale
            min_trade_notional_quote = float((live_state or {}).get("min_trade_notional_quote", 0.0) or 0.0)
            if rebalance_side == "sell" and abs(current_signed) < max(min_trade_notional_quote, rebalance_deadzone_floor):
                self.ops.inc_metric("inventory_below_min_order_total")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "reason": "inventory_below_min_order",
                        "current_signed": current_signed,
                        "min_trade_notional_quote": min_trade_notional_quote,
                    },
                )
                self.ops.audit_event(
                    "live_exec",
                    {
                        "status": "skipped",
                        "reason": "inventory_below_min_order",
                        "symbol": symbol,
                        "side": rebalance_side,
                        "notional": rebalance_notional,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            min_required_quote = max(min_order_notional_quote_live, min_trade_notional_quote, rebalance_deadzone_floor)
            pending_dust_to_clear = 0.0
            dust_now = _dust_for(symbol, rebalance_side)
            if rebalance_notional + dust_now < min_required_quote:
                _set_dust(symbol, rebalance_side, dust_now + rebalance_notional)
                self.ops.inc_metric("dust_accumulate_total")
                self.ops.audit_event(
                    "dust_accumulate",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "side": rebalance_side,
                        "rebalance_notional": rebalance_notional,
                        "amount_quote": rebalance_notional,
                        "total_quote": dust_now + rebalance_notional,
                        "min_required_quote": min_required_quote,
                    },
                )
                self.ops.audit_event(
                    "live_exec",
                    {
                        "status": "skipped",
                        "reason": "dust_accumulate",
                        "symbol": symbol,
                        "side": rebalance_side,
                        "notional": rebalance_notional,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if dust_now > 0.0:
                rebalance_notional += dust_now
                pending_dust_to_clear = dust_now
            if hard_order_cap_quote > 0.0 and rebalance_notional > hard_order_cap_quote:
                overflow_quote = rebalance_notional - hard_order_cap_quote
                rebalance_notional = hard_order_cap_quote
                if pending_dust_to_clear > 0.0:
                    pending_dust_to_clear = max(0.0, pending_dust_to_clear - overflow_quote)
            rebalance_why = dict(intent.why)
            rebalance_why["delta_rebalance"] = {
                "current_signed_exposure": current_signed,
                "desired_signed_exposure": desired_signed,
                "delta_signed_exposure": delta_signed,
            }
            rebalance_why["self_tuner"] = {
                "enabled": self_tuner_enabled,
                "size_scale": self_tuner_size_scale,
                "min_order_notional_quote": min_order_notional_quote_live,
            }
            if pending_dust_to_clear > 0.0:
                rebalance_why["dust_accumulator"] = {
                    "merged_quote": pending_dust_to_clear,
                    "min_required_quote": min_required_quote,
                }
            if hard_order_cap_quote > 0.0:
                rebalance_why["max_order_notional_quote_cap"] = hard_order_cap_quote
            rebalance_why["market_snapshot"] = {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_bps": spread_bps,
                "depth_notional": depth_notional,
                "ts": now_ts,
            }
            rebalance_why["model_ops"] = {
                "active_model": active_model_name,
                "champion_score": model_scores["champion"],
                "challenger_score": model_scores["challenger"],
            }
            rebalance_intent = OrderIntent(intent.symbol, rebalance_side, rebalance_notional, rebalance_why)
            mastermind_mode = self.mastermind.mode(
                exits_only=bool(stuck_decision.exits_only) or (now_ts < audit_pause_new_risk_until_ts),
                rate_limit_storm=self.rate_limit_governor.storm_active(now_ts=now_ts),
                ws_healthy=bool(ws_healthy),
            )
            mm_decision = self.mastermind.choose(
                base_intent=rebalance_intent,
                now_ts=now_ts,
                mode=mastermind_mode,
                risk_penalty=max(0.0, drawdown_abs * 0.05),
                churn_penalty=3.0 if self.order_churn_controller.storm_active(now_ts=now_ts) else 0.0,
                stuck_penalty=5.0 if stuck_decision.stuck else 0.0,
            )
            if not mm_decision.allowed:
                self.ops.audit_event(
                    "mastermind_block",
                    {
                        "symbol": symbol,
                        "reason": mm_decision.reason,
                        "mode": mm_decision.mode,
                        "score": mm_decision.score,
                    },
                )
                self._record_module_event(
                    module="mastermind_policy",
                    action="block",
                    reason=str(mm_decision.reason),
                    symbol=symbol,
                    payload={"mode": mm_decision.mode, "score": float(mm_decision.score)},
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if mm_decision.intent is not None:
                rebalance_intent = mm_decision.intent
                rebalance_side = str(rebalance_intent.side).lower()
                rebalance_notional = max(0.0, float(rebalance_intent.target_notional))
                self.ops.set_metric("mastermind_score", float(mm_decision.score))
                self.ops.audit_event(
                    "mastermind_select",
                    {
                        "symbol": symbol,
                        "mode": mm_decision.mode,
                        "strategy": mm_decision.selected_strategy,
                        "score": mm_decision.score,
                        "side": rebalance_side,
                        "notional": rebalance_notional,
                    },
                )
                self._record_module_event(
                    module="mastermind_policy",
                    action="select",
                    reason="mastermind_selected",
                    symbol=symbol,
                    payload={
                        "mode": mm_decision.mode,
                        "strategy": mm_decision.selected_strategy,
                        "score": float(mm_decision.score),
                        "side": rebalance_side,
                        "notional": float(rebalance_notional),
                    },
                )
            projected_signed = current_signed + (rebalance_notional if rebalance_side == "buy" else -rebalance_notional)
            is_reduce_only = abs(projected_signed) + 1e-9 < abs(current_signed)
            if not treasury_decision.allowed and not is_reduce_only:
                self.ops.inc_metric("orders_rejected_total")
                orders_rejected += 1.0
                self.ops.audit_event(
                    "treasury_reject",
                    {
                        "reason": treasury_decision.reason,
                        "actions": treasury_decision.actions,
                        "reserve_ratio": treasury_decision.reserve_ratio,
                        "margin_buffer": treasury_decision.margin_buffer,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue

            decision = self.risk.evaluate(
                intent=rebalance_intent,
                current_exposure=abs(current_signed),
                drawdown_pct=drawdown_pct,
                daily_loss_pct=daily_loss_pct,
                data_lag_seconds=0.0,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
                reconciliation_ok=last_recon_ok,
                funding_paid_pct=funding_paid_pct,
                oi_spike_pct=0.0,
                liquidation_spike=0.0,
                divergence_bps=0.0,
                margin_buffer=999.0,
                funding_rate_abs=0.0,
                weekly_loss_pct=daily_loss_pct,
                symbol_exposure=abs(current_signed),
                cluster_exposure=abs(current_signed),
                market_regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
                is_reduce_only=is_reduce_only,
                side=rebalance_side,
            )
            risk_overridden = False
            risk_override_kind = ""
            if not decision.allowed:
                self.ops.inc_metric("risk_reject_total")
                risk_payload = {
                    "reason": decision.reason,
                    "details": decision.details,
                    "guards_mode": guards_mode,
                    "original_allowed": False,
                }
                if not is_reduce_only and (not entry_safe_mode_enabled) and str(decision.reason) == "safe_mode_default":
                    risk_overridden = True
                    risk_override_kind = "entry_safe_mode"
                    self.ops.inc_metric("safe_mode_entry_overridden_total")
                    risk_payload["overridden_by"] = "entry_safe_mode"
                    self.ops.audit_event("risk_reject", risk_payload)
                    self.ops.audit_event(
                        "policy_violation_warn",
                        {
                            "kind": "risk",
                            "reason": decision.reason,
                            "details": decision.details,
                            "overridden_by": "entry_safe_mode",
                        },
                    )
                elif not is_reduce_only and growth_mode and str(decision.reason) in {"cooldown_active", "vol_stop"}:
                    risk_overridden = True
                    risk_override_kind = "growth_volstop_throttle"
                    volstop_cooldown_until_ts = max(volstop_cooldown_until_ts, now_ts + volstop_cooldown_s)
                    risk_payload["overridden_by"] = "growth_volstop_throttle"
                    risk_payload["throttle_scale"] = volstop_throttle_scale
                    risk_payload["cooldown_s"] = volstop_cooldown_s
                    self.ops.audit_event("risk_reject", risk_payload)
                    self.ops.audit_event(
                        "policy_violation_warn",
                        {
                            "kind": "risk",
                            "reason": decision.reason,
                            "details": decision.details,
                            "overridden_by": "growth_volstop_throttle",
                            "throttle_scale": volstop_throttle_scale,
                            "cooldown_s": volstop_cooldown_s,
                        },
                    )
                elif fatal_only_mode:
                    risk_overridden = True
                    risk_override_kind = "fatal_only"
                    risk_payload["overridden_by_fatal_only"] = True
                    self.ops.audit_event("risk_reject", risk_payload)
                    self.ops.audit_event(
                        "policy_violation_warn",
                        {
                            "kind": "risk",
                            "reason": decision.reason,
                            "details": decision.details,
                            "overridden_by": "fatal_only",
                        },
                    )
                else:
                    self.ops.inc_metric("orders_rejected_total")
                    orders_rejected += 1.0
                    self.ops.audit_event("risk_reject", risk_payload)
                    if decision.flatten and hasattr(live, "flatten_all_positions"):
                        try:
                            closed, flat_reason = live.flatten_all_positions()
                            if closed:
                                exposure_notional = 0.0
                            self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": decision.reason})
                        except Exception as exc:
                            self.ops.audit_event("flatten_error", {"error": str(exc)})
                    _update_live_kpis()
                    self.ops.export_prometheus()
                    self.ops.export_dashboard_snapshot()
                    if max_steps and steps >= max_steps:
                        return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                    time.sleep(poll_s)
                    continue

            adjusted_notional_for_trade = decision.adjusted_notional
            if risk_overridden:
                if risk_override_kind == "growth_volstop_throttle":
                    adjusted_notional_for_trade = rebalance_intent.target_notional * volstop_throttle_scale
                else:
                    adjusted_notional_for_trade = max(rebalance_intent.target_notional, decision.adjusted_notional)
            if adjusted_notional_for_trade <= 0.0:
                adjusted_notional_for_trade = rebalance_intent.target_notional
            if hard_order_cap_quote > 0.0:
                adjusted_notional_for_trade = min(adjusted_notional_for_trade, hard_order_cap_quote)

            gov_decision = self.governance.enforce_policy_constraints(
                symbol=rebalance_intent.symbol,
                target_notional=adjusted_notional_for_trade,
                max_notional=self._limit_float(self.settings.risk.max_position_notional, adjusted_notional_for_trade),
                leverage=int(self._limit_float(self.settings.risk.leverage, 1.0)),
                max_leverage=mandate_max_leverage,
                drawdown_pct=drawdown_pct,
                max_drawdown_pct=self._limit_float(self.settings.risk.max_drawdown_pct, 100.0),
                allowed_symbols=set(symbol_candidates) if enforce_mandate else None,
            )
            governance_overridden = False
            fatal_governance_reasons = {
                "missing_auth_permissions",
                "symbol_mapping_invalid",
                "exchange_constraint_invalid",
                "invalid_book",
                "idempotency_duplicate",
                "hard_rate_limit_failure",
            }
            governance_fatal = bool(getattr(gov_decision, "fatal", False)) or str(gov_decision.reason) in fatal_governance_reasons
            if enforce_mandate and not gov_decision.allowed:
                self.ops.inc_metric("governance_block_total")
                self.ops.audit_event(
                    "governance_reject",
                    {
                        "reason": gov_decision.reason,
                        "details": gov_decision.details,
                        "fatal": governance_fatal,
                        "guards_mode": guards_mode,
                    },
                )
                if fatal_only_mode and not governance_fatal:
                    governance_overridden = True
                    self.ops.audit_event(
                        "policy_violation_warn",
                        {
                            "kind": "governance",
                            "reason": gov_decision.reason,
                            "details": gov_decision.details,
                            "overridden_by": "fatal_only",
                        },
                    )
                else:
                    self.ops.inc_metric("orders_rejected_total")
                    orders_rejected += 1.0
                    _update_live_kpis()
                    self.ops.export_prometheus()
                    self.ops.export_dashboard_snapshot()
                    if max_steps and steps >= max_steps:
                        return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                    time.sleep(poll_s)
                    continue
            self.ops.set_metric("governance_allowed", 1.0 if (gov_decision.allowed or governance_overridden) else 0.0)

            adjusted_why = dict(rebalance_intent.why)
            adjusted_why["risk_reason"] = decision.reason
            adjusted_why["risk"] = {
                "decision_reason": decision.reason,
                "decision_allowed": decision.allowed,
                "decision_overridden_by_fatal_only": risk_override_kind == "fatal_only",
                "decision_override_kind": risk_override_kind,
                "guards_mode": guards_mode,
                **decision.details,
            }
            adjusted_why["governance"] = {
                "decision_reason": gov_decision.reason,
                "decision_allowed": gov_decision.allowed,
                "decision_overridden_by_fatal_only": governance_overridden,
                "decision_fatal": governance_fatal,
                "guards_mode": guards_mode,
                **(gov_decision.details if isinstance(gov_decision.details, dict) else {}),
            }
            adjusted = OrderIntent(rebalance_intent.symbol, rebalance_intent.side, adjusted_notional_for_trade, adjusted_why)
            cadence_bypass = bool(is_reduce_only and (decision.flatten or governance_fatal))
            cadence_remaining_s = max(0.0, min_seconds_between_orders - (now_ts - last_order_attempt_ts))
            if min_seconds_between_orders > 0.0 and cadence_remaining_s > 1e-9 and not cadence_bypass:
                self.ops.audit_event(
                    "live_exec",
                    {
                        "status": "skipped",
                        "reason": "cadence_cooldown",
                        "symbol": adjusted.symbol,
                        "side": adjusted.side,
                        "notional": adjusted.target_notional,
                        "cooldown_remaining_s": cadence_remaining_s,
                        "min_seconds_between_orders": min_seconds_between_orders,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            last_order_attempt_ts = now_ts
            if adjusted.side == "sell" and sell_profit_lock_enabled and not _is_fatal_reduce_why(adjusted_why):
                live_pos_qty = float((live_state or {}).get("position_qty", 0.0) or 0.0)
                live_avg_entry_price = float((live_state or {}).get("avg_entry_price", 0.0) or 0.0)
                live_position_age_s = max(0.0, float((live_state or {}).get("position_age_s", 0.0) or 0.0))
                if live_pos_qty > 0.0 and bid > 0.0:
                    if live_avg_entry_price <= 0.0 and sell_profit_lock_require_cost_basis:
                        self.ops.audit_event(
                            "live_exec",
                            {
                                "status": "skipped",
                                "reason": "profit_lock_missing_cost_basis",
                                "symbol": adjusted.symbol,
                                "side": adjusted.side,
                                "notional": adjusted.target_notional,
                            },
                        )
                        _update_live_kpis()
                        self.ops.export_prometheus()
                        self.ops.export_dashboard_snapshot()
                        if max_steps and steps >= max_steps:
                            return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                        time.sleep(poll_s)
                        continue
                    if live_avg_entry_price > 0.0:
                        required_profit_bps = (
                            sell_profit_lock_target_bps
                            if live_position_age_s < sell_profit_lock_target_hold_s
                            else sell_profit_lock_min_bps
                        )
                        min_sell_price = live_avg_entry_price * (1.0 + (required_profit_bps / 10000.0))
                        if bid + 1e-12 < min_sell_price:
                            self.ops.audit_event(
                                "policy_violation_warn",
                                {
                                    "reason": "profit_lock_sell_below_entry",
                                    "symbol": adjusted.symbol,
                                    "side": adjusted.side,
                                    "bid": bid,
                                    "avg_entry_price": live_avg_entry_price,
                                    "min_sell_price": min_sell_price,
                                    "required_profit_bps": required_profit_bps,
                                    "position_age_s": live_position_age_s,
                                    "target_profit_bps": sell_profit_lock_target_bps,
                                    "target_hold_s": sell_profit_lock_target_hold_s,
                                    "min_profit_bps": sell_profit_lock_min_bps,
                                },
                            )
                            self.ops.audit_event(
                                "live_exec",
                                {
                                    "status": "skipped",
                                    "reason": "profit_lock_sell_below_entry",
                                    "symbol": adjusted.symbol,
                                    "side": adjusted.side,
                                    "notional": adjusted.target_notional,
                                },
                            )
                            self.stuck_governor.note_sell_profit_lock_block(adjusted.symbol)
                            _update_live_kpis()
                            self.ops.export_prometheus()
                            self.ops.export_dashboard_snapshot()
                            if max_steps and steps >= max_steps:
                                return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                            time.sleep(poll_s)
                            continue
            expected_net_edge_bps = self._intent_expected_net_edge_bps(adjusted)
            route_candidates: list[VenueCandidate] = []
            if latest_feed_quotes:
                for q in latest_feed_quotes:
                    route_candidates.append(
                        VenueCandidate(
                            venue=q.venue,
                            bid=float(q.bid),
                            ask=float(q.ask),
                            depth_notional=max(depth_notional, float(q.depth_notional)),
                            fee_bps=float(self.settings.execution.fee_bps),
                            latency_ms=float(q.latency_ms),
                            stale_s=max(0.0, now_ts - float(q.ts)),
                            queue_ahead_notional=max(0.0, float(q.depth_notional) * 0.2),
                        )
                    )
            if self.exchange_manager.enabled and route_candidates:
                mx_decision = self.exchange_manager.route_venue(
                    symbol=adjusted.symbol,
                    candidates=[
                        {
                            "venue": c.venue,
                            "liquidity": float(c.depth_notional),
                            "fee_bps": float(c.fee_bps),
                            "spread_bps": float(spread_bps),
                        }
                        for c in route_candidates
                    ],
                )
                self.ops.set_metric("multi_exchange_venue_score", float(mx_decision.score))
                self._record_module_event(
                    module="exchange_manager",
                    action="route_venue",
                    reason=str(mx_decision.reason),
                    symbol=adjusted.symbol,
                    payload={"venue": mx_decision.venue, "score": float(mx_decision.score)},
                )
            if not route_candidates:
                route_candidates.append(
                    VenueCandidate(
                        venue=primary_venue,
                        bid=bid,
                        ask=ask,
                        depth_notional=depth_notional,
                        fee_bps=float(self.settings.execution.fee_bps),
                        latency_ms=0.0,
                        stale_s=0.0,
                        queue_ahead_notional=max(0.0, depth_notional * 0.2),
                    )
                )
            route = self.router.pick_route(
                side=adjusted.side,
                notional=adjusted.target_notional,
                expected_edge_bps=expected_net_edge_bps,
                candidates=route_candidates,
                maker_preference=bool(self.settings.execution.maker_preference),
            )
            if route is None and not is_reduce_only:
                self.ops.inc_metric("orders_rejected_total")
                orders_rejected += 1.0
                self.ops.audit_event("route_reject", {"reason": "no_positive_net_route", "symbol": adjusted.symbol})
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue
            if route is not None:
                adjusted_why["execution_route"] = {
                    "venue": route.venue,
                    "order_type": route.order_type,
                    "expected_total_cost_bps": route.expected_total_cost_bps,
                    "expected_fill_prob": route.expected_fill_prob,
                    "expected_net_edge_bps": route.expected_net_edge_bps,
                    "reason": route.reason,
                    "diagnostics": route.diagnostics,
                }
                self.ops.set_metric("route_expected_fill_prob", route.expected_fill_prob)
                self.ops.set_metric("route_expected_net_edge_bps", route.expected_net_edge_bps)
                self.ops.set_metric("route_expected_cost_bps", route.expected_total_cost_bps)
                self.ops.set_metric("route_venue_mismatch", 1.0 if route.venue != primary_venue else 0.0)
                self.ops.set_metric("expected_total_cost_bps", route.expected_total_cost_bps)
                self.ops.set_metric("expected_net_edge_bps", route.expected_net_edge_bps)
                self.ops.set_metric("expected_fill_prob", route.expected_fill_prob)
                self.ops.set_metric("route_order_type", route.order_type)
                self.ops.set_metric("venue_selected", route.venue)
                modeled_ratio = route.expected_total_cost_bps / max(route.expected_net_edge_bps, modeled_ratio_eps)
                if cost_to_alpha_ratio_modeled_ewma is None:
                    cost_to_alpha_ratio_modeled_ewma = modeled_ratio
                else:
                    cost_to_alpha_ratio_modeled_ewma = (modeled_ratio_ewma_alpha * modeled_ratio) + ((1.0 - modeled_ratio_ewma_alpha) * cost_to_alpha_ratio_modeled_ewma)
                self.ops.set_metric("cost_to_alpha_ratio_modeled", cost_to_alpha_ratio_modeled_ewma)
            maker_mode = route is not None and route.order_type == "maker"
            tco = self.cost_engine.estimate(
                notional=adjusted.target_notional,
                depth_notional=depth_notional,
                spread_bps=spread_bps,
                fee_bps=float(self.settings.execution.fee_bps),
                slippage_bps=float(self.settings.execution.slippage_bps),
                funding_bps=0.0,
                borrow_bps=0.0,
                maker=maker_mode,
            )
            cost_to_alpha_ratio = self.cost_engine.cost_to_alpha_ratio(alpha_bps=expected_net_edge_bps, cost_bps=tco.total_bps)
            self.ops.set_metric("tco_total_bps_rt", tco.total_bps)
            self.ops.set_metric("cost_to_alpha_ratio", cost_to_alpha_ratio)
            if cost_to_alpha_ratio > max_cost_to_alpha_ratio and not is_reduce_only:
                self.ops.inc_metric("orders_rejected_total")
                orders_rejected += 1.0
                self.ops.audit_event(
                    "cost_guard_reject",
                    {
                        "reason": "cost_to_alpha_too_high",
                        "ratio": cost_to_alpha_ratio,
                        "max_ratio": max_cost_to_alpha_ratio,
                        "expected_net_edge_bps": expected_net_edge_bps,
                        "expected_cost_bps": tco.total_bps,
                    },
                )
                _update_live_kpis()
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
                time.sleep(poll_s)
                continue

            account_decision = self.account_router.choose_account(
                symbol=adjusted.symbol,
                available_margin_by_account={},
                rate_limit_pressure_by_account={},
            )
            adjusted_why["account_routing"] = {
                "account_id": account_decision.account_id,
                "reason": account_decision.reason,
            }
            self.ops.set_metric("account_routing_active", 1.0 if len(self.account_router.accounts) > 1 else 0.0)
            self._record_module_event(
                module="account_router",
                action="route",
                reason=account_decision.reason,
                symbol=adjusted.symbol,
                payload={"account_id": account_decision.account_id},
            )
            adjusted = OrderIntent(adjusted.symbol, adjusted.side, adjusted.target_notional, adjusted_why)
            intents_total += 1.0
            _ = self.bus.publish(
                "intent",
                {
                    "symbol": adjusted.symbol,
                    "side": adjusted.side,
                    "notional": adjusted.target_notional,
                    "step": steps,
                    "model_version": fc.model_version,
                    "regime": fc.regime,
                },
                event_id=f"intent-{steps}",
                idempotency_key=f"{adjusted.symbol}:{adjusted.side}:{round(adjusted.target_notional, 6)}:{steps // 2}",
            )
            hybrid_live_allowed = symbol_live_in_hybrid(adjusted.symbol, self.hybrid_live_symbols)
            if self.hybrid_mode_enabled and not hybrid_live_allowed:
                result = SimpleNamespace(
                    status="paper_hybrid",
                    reason="hybrid_paper_symbol",
                    order={
                        "symbol": adjusted.symbol,
                        "side": adjusted.side,
                        "notional": adjusted.target_notional,
                        "request_sent": False,
                    },
                )
                self._record_module_event(
                    module="hybrid_mode",
                    action="paper_symbol_skip_live",
                    reason="symbol_not_in_live_subset",
                    symbol=adjusted.symbol,
                    payload={"live_symbols": sorted(self.hybrid_live_symbols)},
                )
            else:
                result = self.execution.execute_live(adjusted)
            status_norm = str(result.status).strip().lower()
            reason_norm = str(result.reason).strip().lower()
            if "rate_limit" in reason_norm:
                self.rate_limit_governor.record_error(
                    endpoint="execution",
                    error_text=reason_norm,
                    now_ts=now_ts,
                )
                self.order_churn_controller.note_rate_limit_storm(now_ts=now_ts)
                extra_probe_backoff_until_ts = max(extra_probe_backoff_until_ts, now_ts + order_submission_interval_s)
            else:
                self.rate_limit_governor.record_success(
                    endpoint="execution",
                    now_ts=now_ts,
                )
            count_as_attempt = not (status_norm in {"blocked", "skipped"} and reason_norm in non_attempt_block_reasons)
            if count_as_attempt:
                executions_attempted_total += 1.0
            if reason_norm == "inventory_below_min_order":
                self.ops.inc_metric("inventory_below_min_order_total")
            self.ops.audit_event("live_exec", {"status": result.status, "reason": result.reason, "symbol": adjusted.symbol, "side": adjusted.side, "notional": adjusted.target_notional})
            if status_norm in {"submitted_limit_floor", "submitted"} and str(adjusted.side).lower() == "sell":
                self._record_module_event(
                    module="exit_order_manager",
                    action="submit_exit",
                    reason=str(result.reason),
                    symbol=adjusted.symbol,
                    payload={
                        "status": str(result.status),
                        "required_exit_price": float((result.order or {}).get("required_exit_price", 0.0) or 0.0),
                        "eligible_qty": float((result.order or {}).get("eligible_qty", 0.0) or 0.0),
                    },
                )
            self.sqlite.record_order(
                symbol=adjusted.symbol,
                side=adjusted.side,
                status=str(result.status),
                reason=str(result.reason),
                notional_quote=float(adjusted.target_notional),
                venue=primary_venue,
                order_type=str((route.order_type if route is not None else "")),
                payload=dict(result.order or {}),
            )
            self.sqlite.record_submission(
                symbol=adjusted.symbol,
                status=str(result.status),
                reason=str(result.reason),
                notional_quote=float(adjusted.target_notional),
                payload={"scheduler_probe": False},
            )
            if result.status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
                if str(adjusted.side).lower() == "buy":
                    self.mastermind.note_entry_submission(now_ts=now_ts)
                self.ops.audit_event(
                    "execution_submitted",
                    {
                        "symbol": adjusted.symbol,
                        "side": adjusted.side,
                        "notional_quote": adjusted.target_notional,
                        "arrival_mid": mid,
                        "expected_cost_bps": tco.total_bps,
                        "expected_edge_bps": expected_net_edge_bps,
                        "why": adjusted.why,
                    },
                )
            blocked_sell_now = str(adjusted.side).lower() == "sell" and (
                "profit_lock" in reason_norm or "profit_gate_block" in reason_norm
            )
            if blocked_sell_now or ("sell_invariant" in reason_norm):
                self._record_violation(
                    module="profit_gate",
                    rule="core_rule_1_min_net_profit_2pct",
                    reason=str(result.reason),
                    symbol=adjusted.symbol,
                    payload={
                        "status": str(result.status),
                        "side": str(adjusted.side),
                        "notional": float(adjusted.target_notional),
                        "order": dict(result.order or {}),
                    },
                )
            if blocked_sell_now:
                self.stuck_governor.note_sell_profit_lock_block(adjusted.symbol)
            elif str(adjusted.side).lower() == "sell" and result.status in {
                "submitted",
                "filled_maker",
                "filled_taker_fallback",
                "submitted_limit_floor",
            }:
                self.stuck_governor.note_sell_success(adjusted.symbol)

            why_components = adjusted.why.get("components", []) if isinstance(adjusted.why, dict) else []
            strategy_names: list[str] = []
            if isinstance(why_components, list):
                for comp in why_components:
                    if isinstance(comp, dict):
                        nm = str(comp.get("strategy", "") or "").strip().lower()
                        if nm and nm not in strategy_names:
                            strategy_names.append(nm)
            if strategy_names:
                observed_alpha = float(expected_net_edge_bps)
                if status_norm in {"blocked", "rejected", "skipped", "timeout"}:
                    observed_alpha = -abs(float(tco.total_bps))
                for sname in strategy_names:
                    self.online_validator.observe(
                        symbol=adjusted.symbol,
                        strategy=sname,
                        alpha_bps=observed_alpha,
                        expected_alpha_bps=float(expected_net_edge_bps),
                        rejected=status_norm in {"blocked", "rejected"},
                        blocked_sell=blocked_sell_now,
                        now_ts=now_ts,
                    )
            if self_tuner_enabled:
                tune_window.append(
                    {
                        "status": str(result.status),
                        "reason": str(result.reason),
                    }
                )
                _tune_execution_params()
            self.governance.audit_trade(
                {
                    "symbol": adjusted.symbol,
                    "side": adjusted.side,
                    "notional": adjusted.target_notional,
                    "status": result.status,
                    "reason": result.reason,
                    "model_version": fc.model_version,
                    "regime": fc.regime,
                    "liquidity_regime": fc.liquidity_regime,
                    "expected_net_edge_bps": expected_net_edge_bps,
                    "expected_cost_bps": tco.total_bps,
                    "risk": decision.details,
                    "why": adjusted.why,
                }
            )
            _ = self.bus.publish(
                "execution",
                {
                    "symbol": adjusted.symbol,
                    "side": adjusted.side,
                    "notional": adjusted.target_notional,
                    "status": result.status,
                    "reason": result.reason,
                    "step": steps,
                },
                event_id=f"execution-{steps}",
                idempotency_key=f"{adjusted.symbol}:{adjusted.side}:{result.status}:{steps // 2}",
            )
            delivered_exec, failed_exec = self.bus.drain("execution", lambda _payload: None)
            self.ops.set_metric("bus_delivery_ok", float(delivered_exec))
            self.ops.set_metric("bus_delivery_failed", float(failed_exec))

            result_order = result.order if isinstance(result.order, dict) else {}
            request_sent = bool(result_order.get("request_sent", False))
            if request_sent or result.status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
                submission_scheduler.record_submission(
                    now_ts=now_ts,
                    filled=result.status in {"filled_maker", "filled_taker_fallback"},
                )
                self.ops.inc_metric("orders_submitted_total")
                orders_submitted += 1.0
                executions_submitted_total += 1.0
                if result.status == "filled_maker":
                    maker_fills += 1.0
                elif result.status == "filled_taker_fallback":
                    taker_fills += 1.0
                if pending_dust_to_clear > 0.0:
                    residual = max(0.0, _dust_for(symbol, adjusted.side) - pending_dust_to_clear)
                    _set_dust(symbol, adjusted.side, residual)
                    self.ops.audit_event(
                        "dust_release",
                        {
                            "symbol": symbol,
                            "side": adjusted.side,
                            "released_quote": pending_dust_to_clear,
                            "residual_quote": residual,
                            "execution_status": result.status,
                        },
                    )
                exec_notional = float((result.order or {}).get("notional", adjusted.target_notional))
                fee_bps_eff = self.settings.execution.fee_bps * (0.6 if result.status == "filled_maker" else 1.0)
                if result.status == "filled_maker":
                    slippage_bps_eff = self.settings.execution.slippage_bps * 0.5
                elif result.status == "filled_taker_fallback":
                    slippage_bps_eff = self.settings.execution.slippage_bps * 1.5
                else:
                    slippage_bps_eff = self.settings.execution.slippage_bps
                total_exec_notional += exec_notional
                total_fee_paid += exec_notional * fee_bps_eff / 10000.0
                total_slippage_paid += exec_notional * slippage_bps_eff / 10000.0
                total_model_slippage_paid += exec_notional * self.settings.execution.slippage_bps / 10000.0
                signal_edge_gross_quote += exec_notional * expected_net_edge_bps / 10000.0
                execution_cost_quote += exec_notional * (fee_bps_eff + slippage_bps_eff) / 10000.0
                alpha_net_quote = signal_edge_gross_quote - execution_cost_quote
                if result.status in {"filled_maker", "filled_taker_fallback"}:
                    fill_price = float((result.order or {}).get("price", mid) or mid)
                    market_kind = "perps" if self.settings.live_provider() == "kraken_futures" else "spot"
                    self.slippage_calibrator.observe_fill(
                        side=str(adjusted.side),
                        fill_price=fill_price,
                        mid_at_submit=mid,
                        market=market_kind,
                        ts=now_ts,
                    )
                    calibration = self.slippage_calibrator.recalibrate(market=market_kind)
                    self.ops.set_metric(
                        "calibrated_slippage_bps",
                        float(calibration.value_bps),
                    )
                    self._record_module_event(
                        module="slippage_calibrator",
                        action="recalibrate",
                        reason=f"market:{market_kind}",
                        symbol=adjusted.symbol,
                        payload={
                            "value_bps": float(calibration.value_bps),
                            "sample_size": int(calibration.sample_size),
                            "percentile": float(calibration.percentile),
                        },
                    )
                    if hasattr(live, "set_profit_gate_slippage_bps"):
                        try:
                            live.set_profit_gate_slippage_bps(float(calibration.value_bps))
                        except Exception:
                            pass
            elif result.status in {"rejected", "blocked", "killed"}:
                if count_as_attempt:
                    self.ops.inc_metric("orders_rejected_total")
                    orders_rejected += 1.0
            if "rate_limit" in str(result.reason).lower():
                rate_limit_events_total += 1.0

            try:
                live_state = _sync_live_fill_state(mid)
            except Exception as exc:
                self.ops.audit_event("fill_sync_error", {"symbol": symbol, "error": str(exc)})
                live_state = {}
            if result.status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
                qa = {}
                if isinstance(live_state, dict):
                    qa = live_state.get("execution_qa", {})
                self.ops.audit_event(
                    "execution_report",
                    {
                        "symbol": adjusted.symbol,
                        "side": adjusted.side,
                        "status": result.status,
                        "reason": result.reason,
                        "notional_quote": float((result.order or {}).get("notional", adjusted.target_notional)),
                        "fees_quote": float((live_state or {}).get("fees_quote", total_fee_paid) if isinstance(live_state, dict) else total_fee_paid),
                        "implementation_shortfall_bps": float(qa.get("implementation_shortfall_bps", 0.0) if isinstance(qa, dict) else 0.0),
                    },
                )

            _update_live_kpis()
            attempts_now = orders_submitted + orders_rejected
            reject_rate_now = float(self.ops.metrics.get("reject_rate", 0.0))
            if attempts_now >= 3 and reject_rate_now >= alert_reject_rate:
                _emit_alert_limited("reject_rate_high", f"reject_rate={reject_rate_now:.3f} attempts={attempts_now:.0f}")
            shortfall_now = float(self.ops.metrics.get("implementation_shortfall_bps", 0.0))
            if shortfall_now >= alert_shortfall_bps:
                _emit_alert_limited("execution_shortfall_high", f"shortfall_bps={shortfall_now:.2f}")
            if active_model_name == "challenger" and model_scores["challenger"] < model_scores["champion"]:
                _emit_alert_limited("challenger_underperforming", "challenger_active_but_score_below_champion", cooldown_steps=max(60, alert_cooldown_steps))

            if getattr(live, "killed", False):
                self.ops.audit_event("live_killed", {"reason": getattr(live, "kill_reason", "")})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                self._write_runtime_health(
                    status="stopped",
                    reason=str(getattr(live, "kill_reason", "kill_switch_active") or "kill_switch_active"),
                    extra={"step": steps, "symbol": symbol},
                )
                return {"status": "stopped", "mode": mode.value, "reason": getattr(live, "kill_reason", "kill_switch_active"), "steps": steps}

            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            if max_steps and steps >= max_steps:
                self._write_runtime_health(
                    status="ok",
                    reason="max_steps_reached",
                    extra={"step": steps, "symbol": symbol},
                )
                return {"status": "ok", "mode": mode.value, "reason": "max_steps_reached", "steps": steps}
            time.sleep(poll_s)

    def boot(self) -> dict:
        self._write_runtime_health(status="starting", reason="boot")
        self.ops.track_config(asdict(self.settings))
        allowlist = self._universe_allowlist()
        if allowlist:
            filtered = [s for s in self.settings.universe if str(s).upper() in allowlist]
            if not filtered:
                self.ops.audit_event(
                    "universe_allowlist_reject",
                    {"reason": "allowlist_empty_after_filter", "allowlist_size": len(allowlist)},
                )
                self._write_runtime_health(status="blocked", reason="allowlist_empty_after_filter")
                return {"status": "blocked", "reason": "allowlist_empty_after_filter"}
            if len(filtered) != len(self.settings.universe):
                self.ops.audit_event(
                    "universe_allowlist_applied",
                    {
                        "before": len(self.settings.universe),
                        "after": len(filtered),
                        "allowlist_size": len(allowlist),
                    },
                )
            self.settings.universe = filtered
        op_override = self._operator_universe_override()
        if op_override:
            if allowlist:
                op_override = [s for s in op_override if s in allowlist]
            if op_override:
                self.settings.universe = op_override
                self.ops.audit_event(
                    "operator_universe_override",
                    {"symbols": list(op_override), "count": len(op_override)},
                )
        if not self.settings.universe:
            self.settings.universe = ["XBTUSD"]
        symbol = self.settings.universe[0]
        mode = self.settings.execution_mode_enum()
        provider = "paper_sim_provider" if mode == ExecutionMode.PAPER else self.settings.live_provider()
        c = self.compliance.check_provider_authorization(provider)
        self.event_store.append("compliance", make_event(ComplianceEvent, "COMPLIANCE_CHECK", symbol, provider, self.event_store.next_seq("compliance"), {"allowed": c.allowed, "reason": c.reason}))
        self.compliance.write_report(
            run_dir=self.settings.storage.run_dir,
            jurisdiction=str(os.getenv("AUTONOMOUS_JURISDICTION", "SK") or "SK"),
            provider=provider,
            decision=c,
            extra={"mode": mode.value},
        )
        if not c.allowed:
            self._write_runtime_health(status="blocked", reason=str(c.reason))
            return {"status": "blocked", "reason": c.reason}
        if self._missing_limits():
            self._write_runtime_health(status="blocked", reason="missing_required_limits")
            return {"status": "blocked", "reason": "missing_required_limits"}
        if mode in {ExecutionMode.LIVE, ExecutionMode.LIVE_TESTNET}:
            ok_wf, wf_payload = self._walk_forward_quality_gate(symbol)
            self.latest_oos_gate_pass = bool(ok_wf)
            self.ops.audit_event("walk_forward_gate", wf_payload)
            self.research.record_experiment(
                name="live_preflight_walk_forward",
                params={"symbol": symbol, "mode": mode.value},
                metrics={
                    "allowed": 1.0 if ok_wf else 0.0,
                    "splits": float(wf_payload.get("splits", 0)),
                    "nested_outer_splits": float((wf_payload.get("nested_walk_forward", {}) or {}).get("outer_splits", 0)),
                },
                artifacts={"walk_forward": wf_payload},
                status="passed" if ok_wf else "failed",
            )
            if not ok_wf:
                self._write_runtime_health(
                    status="blocked",
                    reason=str(wf_payload.get("reason", "walk_forward_gate_failed")),
                    extra={"walk_forward": wf_payload},
                )
                return {"status": "blocked", "reason": wf_payload.get("reason", "walk_forward_gate_failed"), "walk_forward": wf_payload}

        if mode != ExecutionMode.PAPER:
            if self.settings.live_provider() == "kraken_spot":
                connector = KrakenSpotConnector(self.settings.execution.kraken_spot)
                futures_connector: KrakenFuturesConnector | None = None
                discovery_instruments: list[dict[str, object]] = []
                coverage = getattr(self.settings, "market_coverage", None)
                enable_spot = bool(getattr(coverage, "enable_spot", True))
                enable_margin = bool(getattr(coverage, "enable_margin", True))
                enable_perps = bool(getattr(coverage, "enable_perps", True))
                enable_optional_venues = bool(getattr(coverage, "enable_optional_venues", True))
                discover_all_symbols = bool(getattr(coverage, "discover_all_symbols", True))
                coverage_max_symbols = max(0, int(getattr(coverage, "max_symbols", 0) or 0))
                dynamic_universe = self._bool_env("AUTONOMOUS_DYNAMIC_UNIVERSE", discover_all_symbols)
                dynamic_universe_all = self._bool_env("AUTONOMOUS_DYNAMIC_UNIVERSE_ALL", True)
                dynamic_universe_max = max(0, int(os.getenv("AUTONOMOUS_DYNAMIC_UNIVERSE_MAX", str(coverage_max_symbols)) or str(coverage_max_symbols)))
                try:
                    futures_connector = KrakenFuturesConnector(KrakenFuturesSettings()) if enable_perps else None
                    discovery = self.discovery.discover(
                        spot_connector=connector,
                        futures_connector=futures_connector,
                        enable_spot=enable_spot,
                        enable_margin=enable_margin,
                        enable_perps=enable_perps,
                        enable_optional_venues=enable_optional_venues,
                    )
                    self.ops.audit_event(
                        "market_discovery",
                        {
                            "spot_symbols": len(discovery.spot_symbols),
                            "margin_symbols": len(discovery.margin_symbols),
                            "perp_symbols": len(discovery.perp_symbols),
                            "optional_symbols": len(discovery.optional_symbols),
                            "errors": list(discovery.errors),
                        },
                    )
                    self.ops.set_metric("discovery_spot_symbols", float(len(discovery.spot_symbols)))
                    self.ops.set_metric("discovery_margin_symbols", float(len(discovery.margin_symbols)))
                    self.ops.set_metric("discovery_perp_symbols", float(len(discovery.perp_symbols)))
                    self.ops.set_metric("discovery_optional_symbols", float(len(discovery.optional_symbols)))
                    discovery_instruments = [x.__dict__ for x in discovery.instruments]

                    # Auto-build a broader spot universe and prefer the top trade candidate in canary/live.
                    pairs = connector.asset_pairs()
                    ticker_all = connector.ticker()
                    tiers = KrakenSpotUniverseBuilder(self.settings.universe_builder).build(pairs, ticker_all if isinstance(ticker_all, dict) else {})
                    KrakenSpotUniverseBuilder(self.settings.universe_builder).write_helpers(self.settings.storage.run_dir, tiers)
                    if dynamic_universe:
                        discovered_tradeable: list[str] = []
                        if enable_spot:
                            discovered_tradeable.extend(list(discovery.spot_symbols))
                        if enable_margin:
                            discovered_tradeable.extend(list(discovery.margin_symbols))
                        if enable_perps:
                            discovered_tradeable.extend(list(discovery.perp_symbols))
                        if enable_optional_venues:
                            discovered_tradeable.extend(list(discovery.optional_symbols))
                        discovered_tradeable = [s for s in dict.fromkeys(discovered_tradeable) if s]
                        if dynamic_universe_all and discovered_tradeable:
                            built_symbols = list(discovered_tradeable)
                        elif dynamic_universe_all and tiers.watch:
                            built_symbols = list(tiers.watch)
                        elif discovered_tradeable:
                            built_symbols = list(discovered_tradeable)
                        elif tiers.trade:
                            built_symbols = list(tiers.trade)
                        elif tiers.candidate:
                            built_symbols = list(tiers.candidate)
                        else:
                            built_symbols = list(self.settings.universe)
                        if dynamic_universe_max > 0:
                            built_symbols = built_symbols[:dynamic_universe_max]
                        built_symbols = [s for s in dict.fromkeys(built_symbols) if s]
                        allowlist = self._universe_allowlist()
                        if allowlist:
                            built_symbols = [s for s in built_symbols if str(s).upper() in allowlist]
                        if built_symbols:
                            self.settings.universe = built_symbols
                            symbol = built_symbols[0]
                            self.ops.audit_event(
                                "dynamic_universe_loaded",
                                {
                                    "dynamic_universe_all": dynamic_universe_all,
                                    "symbols_loaded": len(built_symbols),
                                    "watch_count": len(tiers.watch),
                                    "candidate_count": len(tiers.candidate),
                                    "trade_count": len(tiers.trade),
                                    "perp_symbols": len(discovery.perp_symbols),
                                    "optional_symbols": len(discovery.optional_symbols),
                                    "first_symbol": symbol,
                                },
                            )
                except Exception as exc:
                    self.ops.audit_event("universe_builder_error", {"error": str(exc)})
                spot_live = LiveKrakenSpotService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=connector,
                )
                futures_live = None
                if enable_perps and futures_connector is not None:
                    futures_live = LiveKrakenFuturesService(
                        settings=self.settings,
                        run_id=self.settings.storage.run_dir.replace("/", "_"),
                        connector=futures_connector,
                    )
                live = LiveKrakenRouterService(
                    spot_service=spot_live if enable_spot else None,
                    futures_service=futures_live,
                    discovered_instruments=discovery_instruments,
                )
            else:
                live = LiveBinanceService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=BinanceUMPerpsConnector(self.settings.execution.binance),
                )
            self.execution.attach_live_service(live)
            ok_preflight, reason_preflight = live.preflight()
            self.recon.persist_report(
                self.settings.storage.run_dir,
                {"mode": mode.value, "preflight_ok": ok_preflight, "reason": reason_preflight},
            )
            if not ok_preflight:
                self.ops.inc_metric("auth_errors_total")
                inc = self.incidents.evaluate(self.ops.metrics)
                if inc is not None:
                    self.notifier.notify(inc.action, inc.reason)
                self._write_runtime_health(status="blocked", reason=str(reason_preflight))
                return {"status": "blocked", "reason": reason_preflight}
            self.governance.write_compliance_report(
                provider=self.settings.live_provider(),
                provider_permissions={"preflight_ok": ok_preflight, "preflight_reason": reason_preflight},
                rules={
                    "max_drawdown_pct": self.settings.risk.max_drawdown_pct,
                    "max_position_notional": self.settings.risk.max_position_notional,
                    "max_exposure_notional": self.settings.risk.max_exposure_notional,
                },
            )
            if mode == ExecutionMode.LIVE_READONLY:
                self._write_runtime_health(status="ok", reason="live_preflight_passed", extra={"symbol": symbol})
                return {"status": "ok", "mode": mode.value, "reason": "live_preflight_passed"}
            self._write_runtime_health(status="running", reason="live_loop_bootstrap", extra={"symbol": symbol})
            return self._live_loop(live, symbol=symbol, mode=mode)

        if len(self.settings.universe) > 1:
            if not self.settings.fixtures.symbol_files:
                self._write_runtime_health(status="blocked", reason="missing_symbol_fixtures")
                return {"status": "blocked", "reason": "missing_symbol_fixtures"}
            for sym in self.settings.universe:
                if sym not in self.settings.fixtures.symbol_files:
                    self._write_runtime_health(status="blocked", reason=f"missing_fixture_for_{sym}")
                    return {"status": "blocked", "reason": f"missing_fixture_for_{sym}"}

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        ok, issues = self.qa.validate_replay(bars)
        if not ok:
            self._write_runtime_health(status="blocked", reason=",".join(issues))
            return {"status": "blocked", "reason": ",".join(issues)}

        fvs = self.features.build_from_bars(bars)

        equity, peak, exposure = 1.0, 1.0, 0.0
        funding_paid_pct = 0.0
        strategy_perf = {s.name: 0.0 for s in self.policy.strategies}
        fills_all, plans, trade_log = [], [], []

        for i in range(1, len(fvs)):
            fv = fvs[i - 1]
            bar = bars[i]
            self.features.assert_no_leakage(fv.ts, bar.ts)

            if self.qa.divergence_breaker(bar, float(self.settings.risk.divergence_threshold_bps)):
                self.risk.state.kill_switch = True
                self.risk.state.safe_mode = True
                self.event_store.append("risk", make_event(RiskEvent, "DIVERGENCE_KILL", symbol, "paper", self.event_store.next_seq("risk"), {"divergence": True}))
                if abs(exposure) > 0:
                    fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
                    exposure = 0.0
                break

            fc = self.models.forecast(fv)
            intent = self.policy.make_intent(fc, fv.values, self.settings.execution.fee_bps, self.settings.execution.slippage_bps)
            if intent is None:
                self.ops.inc_metric("orders_rejected_total")
                if self.policy.last_veto_reasons:
                    self.ops.inc_metric("veto_tco_total", float(len(self.policy.last_veto_reasons)))
                    for reason, count in self.policy.last_veto_counts.items():
                        self.ops.inc_metric(f"veto_{reason}_total", float(count))
                continue

            oi_prev = max(1.0, bars[i - 1].oi)
            oi_spike = (bar.oi - oi_prev) / oi_prev * 100
            divergence_bps = abs(bar.mark_price - bar.secondary_price) / max(bar.mark_price, 1e-9) * 10000
            margin_buffer = 2.5

            decision = self.risk.evaluate(
                intent,
                current_exposure=abs(exposure),
                drawdown_pct=(equity / peak - 1) * 100,
                daily_loss_pct=min(0.0, (equity - 1.0) * 100),
                data_lag_seconds=0.0,
                spread_bps=bar.spread_bps,
                depth_notional=bar.depth_notional,
                reconciliation_ok=True,
                funding_paid_pct=funding_paid_pct,
                oi_spike_pct=oi_spike,
                liquidation_spike=bar.liquidations,
                divergence_bps=divergence_bps,
                margin_buffer=margin_buffer,
                funding_rate_abs=abs(bar.funding_rate),
                market_regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
                is_reduce_only=intent.side == "sell",
                side=intent.side,
            )
            self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
            crowd_level = getattr(self.risk.state, "last_crowding_level", "none")
            crowd_map = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "extreme": 4.0}
            self.ops.set_metric("crowding_level", crowd_map.get(crowd_level, 0.0))
            self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
            self.ops.set_metric("liquidation_spike", bar.liquidations)
            self.ops.set_metric("oi_spike_pct", oi_spike)
            self.ops.set_metric("max_liquidation_spike", float(self.settings.risk.max_liquidation_spike))
            self.ops.set_metric("max_oi_spike_pct", float(self.settings.risk.max_oi_spike_pct))
            self.ops.set_metric("crowding_score_extreme", float(getattr(self.settings.risk, "crowding_score_extreme", self.settings.risk.crowding_score_kill) if getattr(self.settings.risk, "crowding_score_extreme", "UNSPECIFIED") != UNSPECIFIED else self.settings.risk.crowding_score_kill))
            if decision.reason in {"crowding_radar_kill", "crowding_high_block_open_reduce_only", "funding_cost_limit", "funding_budget_throttle_block_open"}:
                self.ops.audit_event(
                    "risk_guard",
                    {
                        "reason": decision.reason,
                        "details": decision.details,
                        "symbol": symbol,
                        "bar_ts": str(bar.ts),
                    },
                )
            if not decision.allowed:
                self.event_store.append("risk", make_event(RiskEvent, "RISK_REJECT", symbol, "paper", self.event_store.next_seq("risk"), {"reason": decision.reason}))
                self.ops.inc_metric("orders_rejected_total")
                if decision.flatten:
                    fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
                    exposure = 0.0
                    break
                continue

            adjusted_why = dict(intent.why)
            adjusted_why["risk"] = {"decision_reason": decision.reason, **decision.details}
            adjusted = OrderIntent(intent.symbol, intent.side, decision.adjusted_notional, adjusted_why)
            idem = make_idempotency_key(asdict(adjusted), "perps-intraday", i)
            order_id = f"ord-{i}"
            self.event_store.append("orders", make_event(OrderIntentEvent, "ORDER_INTENT", symbol, "paper", self.event_store.next_seq("orders"), asdict(adjusted), idempotency_key=idem))
            ok_submit, _ = self.oms.submit_intent(ManagedOrder(order_id=order_id, symbol=symbol, side=adjusted.side, notional=adjusted.target_notional, idempotency_key=idem))
            if not ok_submit:
                self.ops.inc_metric("orders_rejected_total")
                continue
            self.oms.transition(order_id, "ACK")
            self.event_store.append("orders", make_event(OrderEvent, "ORDER_ACK", symbol, "paper", self.event_store.next_seq("orders"), {"order_id": order_id}, idempotency_key=idem))

            fills = self.execution.execute_paper(order_id, adjusted, bar.mark_price, bar.depth_notional, oi_spike, bar.liquidations, bar.funding_rate, bar.spread_bps, fc.regime, fc.liquidity_regime)
            if not fills:
                self.ops.inc_metric("orders_rejected_total")
                continue

            for fill in fills:
                self.oms.apply_fill(order_id, fill.notional)
                self.event_store.append("fills", make_event(FillEvent, "FILL", symbol, "paper", self.event_store.next_seq("fills"), asdict(fill), idempotency_key=fill.fill_id))
                fills_all.append(fill)

            fill_notional = sum(f.notional for f in fills)
            fees = sum(f.fee + f.slippage_cost for f in fills)
            funding_paid_pct += abs(bar.funding_rate) * 100
            side = 1 if adjusted.side == "buy" else -1
            ret = side * (bar.mark_price / bars[i - 1].mark_price - 1)
            pnl = fill_notional * ret - fees - abs(bar.funding_rate) * fill_notional
            equity += pnl / max(self.settings.policy.base_risk_budget, 1.0)
            peak = max(peak, equity)
            exposure += fill_notional if adjusted.side == "buy" else -fill_notional
            self.risk.record_return((pnl / max(fill_notional, 1.0)) * 100)
            plans.append({"order_id": order_id, **asdict(adjusted)})
            trade_log.append({"order_id": order_id, "side": adjusted.side, "notional": fill_notional, "pnl": pnl, "why": adjusted.why})
            self.ops.inc_metric("orders_submitted_total")
            trade_return_bps = (pnl / max(fill_notional, 1.0)) * 10000.0
            strategy_pnl_bps: dict[str, float] = {}
            comps = adjusted.why.get("components", []) if isinstance(adjusted.why, dict) else []
            if isinstance(comps, list) and comps:
                for comp in comps:
                    strat = str(comp.get("strategy", "") or "")
                    if not strat:
                        continue
                    w = float(comp.get("weight", comp.get("allocator_weight_raw", 0.0)) or 0.0)
                    strategy_pnl_bps[strat] = strategy_pnl_bps.get(strat, 0.0) + trade_return_bps * w
            if not strategy_pnl_bps:
                n = max(len(strategy_perf), 1)
                strategy_pnl_bps = {k: trade_return_bps / n for k in strategy_perf}
            for k, v in strategy_pnl_bps.items():
                strategy_perf[k] = strategy_perf.get(k, 0.0) + v
            self.policy.update_allocator(strategy_pnl_bps)

        rec_ok, rec_reason = self.recon.reconcile(fills_all, exposure, True, True)
        if not rec_ok:
            self.risk.state.kill_switch = True
            self.risk.state.safe_mode = True
            self.event_store.append("risk", make_event(RiskEvent, "RECONCILIATION_MISMATCH", symbol, "paper", self.event_store.next_seq("risk"), {"reason": rec_reason}))
            fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
            exposure = 0.0

        drawdown_signed = (equity / peak - 1) * 100
        drawdown = max(0.0, (1.0 - (equity / peak)) * 100)
        psi = self.mlops.detector.psi([x.values["ret_1"] for x in fvs[: max(1, len(fvs)//2)]], [x.values["ret_1"] for x in fvs[max(1, len(fvs)//2):]])
        if self.mlops.should_rollback(drawdown, psi):
            self.event_store.append("risk", make_event(RiskEvent, "AUTO_ROLLBACK", symbol, "paper", self.event_store.next_seq("risk"), {"drawdown_pct": drawdown, "drawdown_signed_pct": drawdown_signed, "psi": psi}))

        self.event_store.append("positions", make_event(PositionEvent, "POSITION_SNAPSHOT", symbol, "paper", self.event_store.next_seq("positions"), {"exposure_notional": exposure}))

        self.ops.set_metric("data_lag_seconds", 0.0)
        self.ops.set_metric("pnl", (equity - 1.0) * 100)
        self.ops.set_metric("drawdown", drawdown)
        self.ops.set_metric("exposure_notional", abs(exposure))
        self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
        self.ops.set_metric("compliance_veto_state", 0.0)
        self.ops.set_metric("reconciliation_mismatch_total", 0.0 if rec_ok else 1.0)
        self.ops.set_metric("slippage_bps", self.settings.execution.slippage_bps)
        self.ops.set_metric("fees_paid", sum(f.fee for f in fills_all))
        self.ops.set_metric("funding_paid", funding_paid_pct)
        maker_count = len([f for f in fills_all if "maker" in f.status])
        self.ops.set_metric("maker_fill_rate", 0.0 if not fills_all else maker_count / len(fills_all))
        avg_cost = 0.0
        if trade_log:
            vals = []
            for t in trade_log:
                comps = t.get("why", {}).get("components", [])
                vals.extend([c.get("cost_total_bps", 0.0) for c in comps])
            if vals:
                avg_cost = sum(vals) / len(vals)

        self.ops.set_metric("cost_total_bps", avg_cost)
        self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
        self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
        orders_submitted = float(self.ops.metrics.get("orders_submitted_total", 0.0))
        orders_rejected = float(self.ops.metrics.get("orders_rejected_total", 0.0))
        attempts = orders_submitted + orders_rejected
        unique_filled_orders = len({f.order_id for f in fills_all})
        fill_rate = 0.0 if orders_submitted <= 0 else min(1.0, unique_filled_orders / orders_submitted)
        reject_rate = 0.0 if attempts <= 0 else orders_rejected / attempts
        total_notional = sum(f.notional for f in fills_all)
        total_slippage_paid = sum(f.slippage_cost for f in fills_all)
        model_slippage_paid = total_notional * self.settings.execution.slippage_bps / 10000.0
        slippage_vs_model = 0.0 if total_notional <= 0 else ((total_slippage_paid - model_slippage_paid) / total_notional) * 10000.0
        net_pnl_after_fees = sum(float(t.get("pnl", 0.0)) for t in trade_log)
        returns = [r / 100.0 for r in self.risk.state.rolling_returns[-252:]]
        self.ops.set_metric("net_pnl_after_fees", net_pnl_after_fees)
        self.ops.set_metric("fill_rate", fill_rate)
        self.ops.set_metric("reject_rate", reject_rate)
        self.ops.set_metric("slippage_vs_model_bps", slippage_vs_model)
        self.ops.set_metric("max_drawdown", drawdown)
        self.ops.set_metric("sharpe", sharpe(returns))
        self.ops.set_metric("sortino", sortino(returns))
        for k, v in self.policy.allocator.state.weights.items():
            self.ops.set_metric(f"allocator_weight_{k}", v)

        inc = self.incidents.evaluate(self.ops.metrics)
        if inc is not None:
            self.notifier.notify(inc.action, inc.reason)

        self.ops.export_prometheus()
        self.ops.export_dashboard_snapshot()
        self.raw.write_table("order_plans", plans)
        self.raw.write_table("fills", [asdict(f) for f in fills_all])
        self.raw.write_table("report", [{"equity": equity, "drawdown_pct": drawdown, "drawdown_signed_pct": drawdown_signed, "funding_paid_pct": funding_paid_pct}])
        self.raw.write_table("trade_log", trade_log)
        self.governance.write_tax_report(
            [
                {
                    "symbol": symbol,
                    "notional": float(t.get("notional", 0.0) or 0.0),
                    "realized_pnl_quote": float(t.get("pnl", 0.0) or 0.0),
                    "fees_quote": max(0.0, -float(t.get("pnl", 0.0) or 0.0)) * 0.0,
                }
                for t in trade_log
            ]
        )

        checksums = {
            "orders_checksum": sha256(json.dumps(plans, sort_keys=True, default=str).encode()).hexdigest(),
            "fills_checksum": sha256(json.dumps([asdict(f) for f in fills_all], sort_keys=True, default=str).encode()).hexdigest(),
            # Keep backward-compatible checksum payload stable for golden tests.
            "equity_checksum": sha256(json.dumps({"equity": equity, "drawdown": drawdown_signed}, sort_keys=True).encode()).hexdigest(),
        }
        self.raw.write_table("checksums", [checksums])
        self._write_runtime_health(status="ok", reason="paper_backtest_complete", extra={"symbol": symbol, "orders": len(plans), "fills": len(fills_all)})
        return {"status": "ok", "orders": len(plans), "fills": len(fills_all), **checksums}
