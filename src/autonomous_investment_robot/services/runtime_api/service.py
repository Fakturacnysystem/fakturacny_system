from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from autonomous_investment_robot.config.settings import (
    BinanceExecutionSettings,
    KrakenExecutionSettings,
    KrakenSpotExecutionSettings,
)
from autonomous_investment_robot.connectors.cex.binance_um_perps import (
    BinanceConnectorError,
    BinanceUMPerpsConnector,
)
from autonomous_investment_robot.connectors.cex.kraken_derivatives import (
    KrakenConnectorError,
    KrakenDerivativesConnector,
)
from autonomous_investment_robot.connectors.cex.kraken_spot import (
    KrakenSpotConnector,
    KrakenSpotConnectorError,
)

RuntimeStateKind = str
RuntimeTone = str


class RuntimeApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    venue: str
    bid: float
    ask: float
    latency_ms: int
    ts: str
    source: str = "live_connector"


@dataclass
class RuntimeApiServiceConfig:
    repo_root: Path
    run_dir: Path | None = None
    run_id: str | None = None
    artifact_stale_after_seconds: int = 300
    quote_stale_after_seconds: int = 15
    quote_cache_ttl_seconds: float = 2.0
    command_outbox_name: str = "rcc_control_outbox.jsonl"
    incident_notes_name: str = "rcc_incident_notes.jsonl"
    command_bridge_path: Path | None = None

    def resolve_run_dir(self) -> Path:
        if self.run_dir is not None and self.run_id:
            raise RuntimeApiError("run_selection_conflict:specify_run_dir_or_run_id_not_both")
        if self.run_dir is not None:
            return self.run_dir
        if self.run_id:
            return self.repo_root / "runs" / self.run_id
        return self.repo_root / "runs" / "latest"

    def selection_mode(self) -> str:
        return "pinned" if self.run_dir is not None or bool(self.run_id) else "latest"

    def resolution_source(self) -> str:
        if self.run_dir is not None:
            return "explicit_run_dir"
        if self.run_id:
            return "explicit_run_id"
        return "default_latest"

    def selection_target(self) -> str:
        if self.run_dir is not None:
            return str(self.run_dir)
        if self.run_id:
            return f"runs/{self.run_id}"
        return "runs/latest"


@dataclass
class ArtifactSnapshot:
    run_dir: Path
    run_id: str
    manifest: dict[str, Any]
    harmony_report: dict[str, Any]
    harmony_boot_report: dict[str, Any]
    report_row: dict[str, Any]
    truth_ownership: list[dict[str, Any]]
    provider_capability: dict[str, Any]
    provider_capability_journal: dict[str, Any]
    operator_summary: dict[str, Any]
    operator_summary_journal: dict[str, Any]
    replay_summary: dict[str, Any]
    replay_summary_journal: dict[str, Any]
    decision_explainability: dict[str, Any]
    live_safety_summary: dict[str, Any]
    health_summary: dict[str, Any]
    readiness_summary: dict[str, Any]
    throughput_diagnostics: dict[str, Any]
    manual_review: dict[str, Any]
    fills: list[dict[str, Any]]
    order_plans: list[dict[str, Any]]
    portfolio_ledger: list[dict[str, Any]]
    truth_events: list[dict[str, Any]]
    account_events: list[dict[str, Any]]
    order_events: list[dict[str, Any]]
    fill_events: list[dict[str, Any]]
    position_events: list[dict[str, Any]]
    risk_events: list[dict[str, Any]]
    user_stream_events: list[dict[str, Any]]
    user_stream_audit: list[dict[str, Any]]
    control_journal: list[dict[str, Any]]
    lifecycle_journal: list[dict[str, Any]]
    lifecycle_evidence: list[dict[str, Any]]
    execution_journal: list[dict[str, Any]]
    market_context_summary: list[dict[str, Any]]
    signal_journal: list[dict[str, Any]]
    market_watch_journal: list[dict[str, Any]]
    market_integrity_journal: list[dict[str, Any]]
    venue_limit_journal: list[dict[str, Any]]
    health_journal: list[dict[str, Any]]
    doctrine_summary: list[dict[str, Any]]
    mastermind_journal: list[dict[str, Any]]
    mastermind_summary: list[dict[str, Any]]
    human_escalation: list[dict[str, Any]]
    capital_strategy: list[dict[str, Any]]
    event_intelligence: list[dict[str, Any]]
    position_morph: list[dict[str, Any]]
    source_trust: list[dict[str, Any]]
    reconciliation: list[dict[str, Any]]
    reconciliation_report: list[dict[str, Any]]
    execution_simulation: list[dict[str, Any]]
    trade_log: list[dict[str, Any]]
    performance_artifacts: dict[str, Any]
    latest_artifact_at: datetime
    started_at: datetime
    artifact_fallback_active: bool
    warnings: list[str] = field(default_factory=list)


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _ensure_datetime(value: datetime | None, fallback: datetime) -> datetime:
    return value if value is not None else fallback


def _dt_to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _safe_datetime_from_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def _file_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parse failures are surfaced as warnings.
        raise RuntimeApiError(f"json_parse_failed:{path.name}:{exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception as exc:  # pragma: no cover - parse failures are surfaced as warnings.
            raise RuntimeApiError(f"jsonl_parse_failed:{path.name}:{index}:{exc}") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _as_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload:
        head = payload[0]
        if isinstance(head, dict):
            return head
    return {}


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_ts_from_row(row: dict[str, Any]) -> datetime | None:
    for key in ("ts", "timestamp", "lastUpdatedAt", "startedAt"):
        value = row.get(key)
        if isinstance(value, str):
            parsed = _safe_datetime_from_iso(value)
            if parsed is not None:
                return parsed
    return None


def _latest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    ranked = sorted(
        rows,
        key=lambda row: (
            _safe_ts_from_row(row) or datetime.min.replace(tzinfo=UTC),
            rows.index(row),
        ),
    )
    return ranked[-1]


PERFORMANCE_ARTIFACT_NAMES = [
    "trade_admission_summary",
    "floor_compatibility_summary",
    "performance_target_translation",
    "performance_gap_report",
    "capital_envelope_summary",
    "capital_utilization_diagnostics",
    "portfolio_heat_summary",
    "capital_efficiency_report",
    "capital_utilization_report",
    "deployment_efficiency_report",
    "dead_capital_pressure_report",
    "pair_universe_snapshot",
    "pair_ranking_report",
    "pair_rotation_decisions",
    "pair_cluster_report",
    "pair_admission_expulsion_report",
    "venue_behavior_profile_report",
    "regime_snapshot",
    "regime_transition_log",
    "regime_pair_matrix",
    "regime_hysteresis_report",
    "regime_exit_family_report",
    "playbook_candidate_log",
    "playbook_expectancy_summary",
    "playbook_disable_reasons",
    "playbook_shadow_evaluation",
    "playbook_confidence_calibration",
    "playbook_opportunity_decay_report",
    "opportunity_queue_snapshot",
    "decision_ranking_explainability",
    "candidate_rejection_matrix",
    "opportunity_auction_report",
    "opportunity_backlog_report",
    "false_negative_report",
    "false_positive_report",
    "quality_of_edge_report",
    "signal_crowding_report",
    "no_trade_reason_histogram",
    "opportunity_miss_journal",
    "decision_waterfall_journal",
    "veto_attribution_journal",
    "false_negative_review",
    "exit_decision_log",
    "exit_state_machine_journal",
    "inventory_aging_report",
    "realized_exit_quality_report",
    "exit_reason_distribution",
    "exit_ladder_report",
    "hold_time_optimization_report",
    "winner_monetization_journal",
    "exit_path_decision_journal",
    "realized_vs_forecast_exit_journal",
    "winner_hold_vs_take_review",
    "exit_family_comparison",
    "inventory_pressure_report",
    "adverse_excursion_report",
    "trade_lifecycle_scoring",
    "post_trade_root_cause_report",
    "cost_model_diagnostics",
    "fill_quality_report",
    "maker_taker_mix_report",
    "cancel_replace_efficiency",
    "cost_sensitivity_analysis",
    "live_degradation_delta_report",
    "private_stream_health",
    "execution_lifecycle_report",
    "order_reject_taxonomy",
    "maker_first_effectiveness",
    "execution_quality_bucket_report",
    "entry_timing_optimizer_report",
    "adaptive_cadence_report",
    "live_degradation_detector_report",
    "self_throttling_state_report",
    "allocator_decisions",
    "capital_allocation_matrix",
    "confidence_bucket_exposure",
    "playbook_pair_budget_matrix",
    "recovery_mode_report",
    "aggressiveness_scaler_report",
    "expectancy_engine_report",
    "expectancy_segment_matrix",
    "playbook_promotion_readiness",
    "pair_regime_expectancy_grid",
    "promotion_score_report",
    "intraday_session_model_report",
    "meta_router_report",
    "confidence_calibration_report",
    "realized_vs_forecast_execution_journal",
    "cost_forecast_vs_realized",
    "fill_delay_review",
    "slippage_truth_review",
    "edge_capture_efficiency_summary",
    "symbol_execution_regime_review",
    "edge_forecast_vs_realized_journal",
    "forecast_error_decomposition",
    "execution_forecast_error_summary",
    "trade_realization_review",
    "symbol_edge_truth_summary",
    "execution_calibration_feedback",
    "planning_bias_adjustment_review",
    "calibration_confidence_snapshot",
    "phase2_operator_summary",
    "phase2_edge_capture_review",
    "phase2_exit_effectiveness_review",
    "phase2_execution_truth_review",
    "post_trade_realization_summary",
    "exit_effectiveness_truth",
    "realized_fee_burden_review",
    "realized_opportunity_cost_review",
    "experiment_registry",
    "experiment_results_summary",
    "promotion_gate_report",
    "rollback_trigger_report",
    "regime_segmented_experiment_report",
    "enhanced_harmony_report",
    "strategy_capability_matrix",
    "rollout_readiness_report",
    "operator_start_procedure",
    "module_value_summary",
    "module_latency_budget_report",
    "module_redundancy_report",
    "module_opportunity_cost_report",
    "profile_optimization_report",
    "config_truth_diff_summary",
    "live_profile_capability_delta",
]


def _state_tone(kind: RuntimeStateKind) -> RuntimeTone:
    if kind in {"error", "unavailable"}:
        return "danger"
    if kind in {"degraded", "stale"}:
        return "warn"
    if kind == "partial":
        return "info"
    return "good"


def _health_status(kind: RuntimeStateKind) -> str:
    if kind in {"error", "unavailable"}:
        return "danger"
    if kind in {"stale", "degraded", "partial"}:
        return "warn"
    return "good"


def _severity_to_tone(value: str) -> RuntimeTone:
    normalized = value.lower()
    if normalized in {"critical", "danger", "error"}:
        return "danger"
    if normalized in {"warn", "warning", "high"}:
        return "warn"
    if normalized in {"good", "ok"}:
        return "good"
    return "info"


def _hash_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _format_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}m"


def _payload_summary(payload: dict[str, Any]) -> str:
    if not payload:
        return "no payload"
    parts: list[str] = []
    for key in sorted(payload.keys())[:4]:
        value = payload[key]
        if isinstance(value, (dict, list)):
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts) or "structured payload"


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class RuntimeApiService:
    def __init__(
        self,
        config: RuntimeApiServiceConfig,
        *,
        now: Callable[[], datetime] = _now_utc,
        quote_fetcher: Callable[[str, str], QuoteSnapshot] | None = None,
    ) -> None:
        self.config = config
        self._now = now
        self._quote_fetcher = quote_fetcher
        self._write_lock = threading.Lock()
        self._selection_lock = threading.Lock()
        self._quote_cache: dict[tuple[str, str], tuple[float, QuoteSnapshot]] = {}
        self._connectors: dict[str, Any] = {}

    def _selection_target_path(self) -> Path:
        return self.config.resolve_run_dir()

    def _run_dir(self) -> Path:
        run_dir = self._selection_target_path()
        if not run_dir.exists():
            raise RuntimeApiError(f"run_not_found:{run_dir}")
        if not run_dir.is_dir():
            raise RuntimeApiError(f"run_not_directory:{run_dir}")
        return run_dir

    def _selection_identity_unresolved(
        self,
        reason_code: str,
        *,
        selection_mode: str | None = None,
        resolution_source: str | None = None,
        target_path: Path | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        target_path = target_path or self._selection_target_path()
        selection_mode = selection_mode or self.config.selection_mode()
        return {
            "runId": run_id or self.config.run_id or target_path.name or "unresolved",
            "runSelectionMode": selection_mode,
            "runResolutionSource": resolution_source or self.config.resolution_source(),
            "runPath": str(target_path),
            "providerId": "unresolved",
            "mode": "unresolved",
            "stateKind": "unresolved",
            "reasonCode": reason_code,
            "driftStatus": "tracking_latest" if selection_mode == "latest" else "unresolved",
            "artifactFreshness": {
                "status": "unavailable",
                "ageSeconds": 0,
                "thresholdSeconds": self.config.artifact_stale_after_seconds,
                "lastArtifactUpdateAt": "",
            },
            "startedAt": None,
            "lastArtifactUpdateAt": None,
            "pinIntegrityStatus": "not_pinned" if selection_mode == "latest" else "unresolved",
            "schemaVersion": None,
        }

    def unresolved_selection_payload(
        self,
        reason_code: str,
        selection_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        override_mode = None
        override_source = None
        override_target: Path | None = None
        override_run_id = None
        selection_target = self.config.selection_target()
        if selection_override:
            override_mode = str(selection_override.get("mode") or "").strip().lower() or None
            override_run_id = _string_or_none(selection_override.get("runId"))
            override_run_path = _string_or_none(selection_override.get("runPath"))
            if override_mode == "latest":
                override_source = "default_latest"
                override_target = self._runs_root() / "latest"
                selection_target = "runs/latest"
            elif override_run_path:
                override_source = "explicit_run_dir"
                override_target = Path(override_run_path).expanduser().resolve()
                selection_target = str(override_target)
                override_run_id = override_target.name
            elif override_run_id:
                override_source = "explicit_run_id"
                override_target = (self._runs_root() / override_run_id).resolve()
                selection_target = f"runs/{override_run_id}"

        return {
            "error": "run_not_found",
            "detail": reason_code,
            "runtimeIdentity": self._selection_identity_unresolved(
                reason_code,
                selection_mode=override_mode,
                resolution_source=override_source,
                target_path=override_target,
                run_id=override_run_id,
            ),
            "runSelection": {
                "mode": override_mode or self.config.selection_mode(),
                "target": selection_target,
                "resolvedRunDir": "",
            },
            "availableRuns": self.runs(),
        }

    def _control_outbox_path(self) -> Path:
        return self._run_dir() / self.config.command_outbox_name

    def _incident_notes_path(self) -> Path:
        return self._run_dir() / self.config.incident_notes_name

    def _read_snapshot(self) -> ArtifactSnapshot:
        run_dir = self._run_dir()
        warnings: list[str] = []

        def load_json(name: str) -> Any:
            path = run_dir / name
            try:
                return _read_json(path)
            except RuntimeApiError as exc:
                warnings.append(str(exc))
                return None

        def load_jsonl(name: str) -> list[dict[str, Any]]:
            path = run_dir / name
            try:
                return _read_jsonl(path)
            except RuntimeApiError as exc:
                warnings.append(str(exc))
                return []

        manifest = _as_object(load_json("config_manifest.json"))
        harmony_report = _as_object(load_json("harmony_report.json"))
        harmony_boot_report = _as_object(load_json("harmony_boot_report.json"))
        report_row = _as_object(load_json("report.json"))
        truth_ownership = _as_list(load_json("truth_ownership.json"))
        provider_capability = _as_object(load_json("provider_capabilities.json"))
        provider_capability_journal = _latest_row(load_jsonl("provider_capability_journal.jsonl"))
        operator_summary = _as_object(load_json("kraken_spot_operator_summary.json"))
        operator_summary_journal = _latest_row(load_jsonl("kraken_spot_operator_summary.jsonl"))
        replay_summary = _as_object(load_json("kraken_spot_replay_summary.json"))
        replay_summary_journal = _latest_row(load_jsonl("kraken_spot_replay_summary.jsonl"))
        decision_explainability = _as_object(load_json("decision_explainability.json"))
        live_safety_summary = _as_object(load_json("live_safety_summary.json"))
        health_summary = _as_object(load_json("health_summary.json"))
        readiness_summary = _as_object(load_json("readiness_summary.json"))
        throughput_diagnostics = _as_object(load_json("throughput_diagnostics.json"))
        manual_review = _as_object(load_json("MANUAL_REVIEW_REQUIRED.json"))
        fills = _as_list(load_json("fills.json"))
        order_plans = _as_list(load_json("order_plans.json"))
        portfolio_ledger = _as_list(load_json("portfolio_ledger.json"))
        trade_log = _as_list(load_json("trade_log.json"))

        truth_events = load_jsonl("events_truth.jsonl")
        account_events = load_jsonl("events_account.jsonl")
        order_events = load_jsonl("events_orders.jsonl")
        fill_events = load_jsonl("events_fills.jsonl")
        position_events = load_jsonl("events_positions.jsonl")
        risk_events = load_jsonl("events_risk.jsonl")
        user_stream_events = load_jsonl("events_user_stream.jsonl")
        user_stream_audit = load_jsonl("user_stream_audit.jsonl")
        control_journal = load_jsonl("control_journal.jsonl")
        lifecycle_journal = load_jsonl("lifecycle_journal.jsonl")
        lifecycle_evidence = load_jsonl("lifecycle_evidence_journal.jsonl")
        execution_journal = load_jsonl("execution_journal.jsonl")
        market_context_summary = load_jsonl("market_context_summary.jsonl")
        signal_journal = load_jsonl("signal_journal.jsonl")
        market_watch_journal = load_jsonl("market_watch_journal.jsonl")
        market_integrity_journal = load_jsonl("market_integrity_journal.jsonl")
        venue_limit_journal = load_jsonl("venue_limit_journal.jsonl")
        health_journal = load_jsonl("health_journal.jsonl")
        doctrine_summary = load_jsonl("decision_doctrine_summary.jsonl")
        mastermind_journal = load_jsonl("mastermind_journal.jsonl")
        mastermind_summary = load_jsonl("mastermind_summary.jsonl")
        human_escalation = load_jsonl("human_escalation_journal.jsonl")
        capital_strategy = load_jsonl("capital_strategy_summary.jsonl")
        event_intelligence = load_jsonl("event_intelligence_journal.jsonl")
        position_morph = load_jsonl("position_morphing_journal.jsonl")
        source_trust = load_jsonl("source_trust_journal.jsonl")
        reconciliation = load_jsonl("reconciliation_journal.jsonl")
        reconciliation_report = load_jsonl("reconciliation_report.jsonl")
        execution_simulation = load_jsonl("execution_simulation_journal.jsonl")
        performance_artifacts = {name: load_json(f"{name}.json") for name in PERFORMANCE_ARTIFACT_NAMES}

        relevant_paths = [
            run_dir / "config_manifest.json",
            run_dir / "harmony_report.json",
            run_dir / "harmony_boot_report.json",
            run_dir / "report.json",
            run_dir / "kraken_spot_operator_summary.json",
            run_dir / "kraken_spot_replay_summary.json",
            run_dir / "decision_explainability.json",
            run_dir / "live_safety_summary.json",
            run_dir / "health_summary.json",
            run_dir / "readiness_summary.json",
            run_dir / "events_truth.jsonl",
            run_dir / "events_account.jsonl",
            run_dir / "events_orders.jsonl",
            run_dir / "events_fills.jsonl",
            run_dir / "events_positions.jsonl",
            run_dir / "events_risk.jsonl",
            run_dir / "events_user_stream.jsonl",
            run_dir / "user_stream_audit.jsonl",
            run_dir / "control_journal.jsonl",
            run_dir / "lifecycle_journal.jsonl",
            run_dir / "lifecycle_evidence_journal.jsonl",
            run_dir / "execution_journal.jsonl",
            run_dir / "market_context_summary.jsonl",
            run_dir / "signal_journal.jsonl",
            run_dir / "market_watch_journal.jsonl",
            run_dir / "market_integrity_journal.jsonl",
            run_dir / "venue_limit_journal.jsonl",
            run_dir / "health_journal.jsonl",
            run_dir / "mastermind_journal.jsonl",
            run_dir / "decision_doctrine_summary.jsonl",
            run_dir / "human_escalation_journal.jsonl",
            run_dir / "capital_strategy_summary.jsonl",
            run_dir / "reconciliation_report.jsonl",
            *[run_dir / f"{name}.json" for name in PERFORMANCE_ARTIFACT_NAMES],
        ]
        mtimes = [_file_mtime(path) for path in relevant_paths]
        valid_mtimes = [mtime for mtime in mtimes if mtime is not None]
        now = self._now()
        latest_artifact_at = max(valid_mtimes) if valid_mtimes else now
        started_at = min(valid_mtimes) if valid_mtimes else now

        operator_bundle_present = bool(operator_summary or operator_summary_journal)
        replay_bundle_present = bool(replay_summary or replay_summary_journal)
        replay_reconstruction_supported = bool(
            operator_bundle_present
            and (truth_events or risk_events or position_events or reconciliation or reconciliation_report)
            and (market_context_summary or market_watch_journal or market_integrity_journal)
        )
        artifact_fallback_active = not (
            operator_bundle_present
            and (replay_bundle_present or replay_reconstruction_supported)
        )
        if artifact_fallback_active:
            warnings.append(
                "Canonical operator/replay bundles are missing; runtime API is reconstructing state from raw artifacts."
            )

        if not manifest:
            warnings.append("config_manifest.json missing; runtime metadata is degraded.")

        return ArtifactSnapshot(
            run_dir=run_dir,
            run_id=run_dir.resolve().name,
            manifest=manifest,
            harmony_report=harmony_report,
            harmony_boot_report=harmony_boot_report,
            report_row=report_row,
            truth_ownership=truth_ownership,
            provider_capability=provider_capability,
            provider_capability_journal=provider_capability_journal,
            operator_summary=operator_summary,
            operator_summary_journal=operator_summary_journal,
            replay_summary=replay_summary,
            replay_summary_journal=replay_summary_journal,
            decision_explainability=decision_explainability,
            live_safety_summary=live_safety_summary,
            health_summary=health_summary,
            readiness_summary=readiness_summary,
            throughput_diagnostics=throughput_diagnostics,
            manual_review=manual_review,
            fills=fills,
            order_plans=order_plans,
            portfolio_ledger=portfolio_ledger,
            trade_log=trade_log,
            truth_events=truth_events,
            account_events=account_events,
            order_events=order_events,
            fill_events=fill_events,
            position_events=position_events,
            risk_events=risk_events,
            user_stream_events=user_stream_events,
            user_stream_audit=user_stream_audit,
            control_journal=control_journal,
            lifecycle_journal=lifecycle_journal,
            lifecycle_evidence=lifecycle_evidence,
            execution_journal=execution_journal,
            market_context_summary=market_context_summary,
            signal_journal=signal_journal,
            market_watch_journal=market_watch_journal,
            market_integrity_journal=market_integrity_journal,
            venue_limit_journal=venue_limit_journal,
            health_journal=health_journal,
            doctrine_summary=doctrine_summary,
            mastermind_journal=mastermind_journal,
            mastermind_summary=mastermind_summary,
            human_escalation=human_escalation,
            capital_strategy=capital_strategy,
            event_intelligence=event_intelligence,
            position_morph=position_morph,
            source_trust=source_trust,
            reconciliation=reconciliation,
            reconciliation_report=reconciliation_report,
            execution_simulation=execution_simulation,
            performance_artifacts=performance_artifacts,
            latest_artifact_at=latest_artifact_at,
            started_at=started_at,
            artifact_fallback_active=artifact_fallback_active,
            warnings=warnings,
        )

    def _get_connector(self, provider_id: str) -> Any:
        if provider_id in self._connectors:
            return self._connectors[provider_id]
        try:
            if provider_id == "binance_um_perps":
                connector: Any = BinanceUMPerpsConnector(BinanceExecutionSettings())
            elif provider_id == "kraken_derivatives":
                connector = KrakenDerivativesConnector(KrakenExecutionSettings())
            elif provider_id == "kraken_spot":
                connector = KrakenSpotConnector(KrakenSpotExecutionSettings())
            else:
                raise RuntimeApiError(f"unsupported_quote_provider:{provider_id}")
        except (BinanceConnectorError, KrakenConnectorError, KrakenSpotConnectorError) as exc:
            raise RuntimeApiError(f"quote_fetch_failed:{provider_id}:connector_init:{exc}") from exc
        self._connectors[provider_id] = connector
        return connector

    def _fetch_live_quote_uncached(self, provider_id: str, symbol: str) -> QuoteSnapshot:
        if self._quote_fetcher is not None:
            return self._quote_fetcher(provider_id, symbol)

        connector = self._get_connector(provider_id)
        started = time.perf_counter()
        try:
            raw = connector.book_ticker(symbol)
        except (BinanceConnectorError, KrakenConnectorError, KrakenSpotConnectorError) as exc:
            raise RuntimeApiError(f"quote_fetch_failed:{provider_id}:{symbol}:{exc}") from exc

        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        bid = _coerce_float(raw.get("bidPrice"))
        ask = _coerce_float(raw.get("askPrice"))
        ts = raw.get("timestamp")
        dt = datetime.fromtimestamp(ts / 1000, tz=UTC) if isinstance(ts, (int, float)) and ts else self._now()
        return QuoteSnapshot(
            symbol=symbol,
            venue=provider_id,
            bid=bid,
            ask=ask,
            latency_ms=latency_ms,
            ts=_dt_to_iso(dt),
        )

    def _fetch_live_quote(self, provider_id: str, symbol: str) -> QuoteSnapshot:
        cache_key = (provider_id, symbol)
        now_ts = time.monotonic()
        cached = self._quote_cache.get(cache_key)
        if cached is not None and cached[0] > now_ts:
            return cached[1]
        quote = self._fetch_live_quote_uncached(provider_id, symbol)
        self._quote_cache[cache_key] = (now_ts + self.config.quote_cache_ttl_seconds, quote)
        return quote

    def _build_symbols(self, snapshot: ArtifactSnapshot) -> tuple[list[dict[str, Any]], str | None]:
        universe = snapshot.manifest.get("universe") or snapshot.harmony_report.get("universe") or []
        provider_id = str(
            snapshot.manifest.get("provider_id")
            or snapshot.harmony_report.get("provider_target")
            or "unknown_provider"
        )
        symbols: list[str] = [str(symbol) for symbol in universe if str(symbol)]
        results: list[dict[str, Any]] = []
        error_message: str | None = None
        for symbol in symbols:
            try:
                quote = self._fetch_live_quote(provider_id, symbol)
                midpoint = (quote.bid + quote.ask) / 2 if quote.bid > 0 and quote.ask > 0 else 0.0
                spread_bps = ((quote.ask - quote.bid) / midpoint * 10_000.0) if midpoint > 0 else 0.0
                quality = max(0.0, min(100.0, 100.0 - spread_bps * 0.9 - quote.latency_ms * 0.08))
                stale = (self._now() - _safe_datetime_from_iso(quote.ts)).total_seconds() > self.config.quote_stale_after_seconds  # type: ignore[arg-type]
                results.append(
                    {
                        "symbol": symbol,
                        "venue": quote.venue,
                        "bid": round(quote.bid, 6),
                        "ask": round(quote.ask, 6),
                        "spreadBps": round(spread_bps, 2),
                        "latencyMs": quote.latency_ms,
                        "qualityScore": round(quality, 2),
                        "stale": stale,
                        "ts": quote.ts,
                        "source": quote.source,
                    }
                )
            except RuntimeApiError as exc:
                artifact_quote = self._artifact_quote_snapshot(snapshot, symbol, provider_id)
                if artifact_quote is not None:
                    midpoint = (artifact_quote.bid + artifact_quote.ask) / 2 if artifact_quote.bid > 0 and artifact_quote.ask > 0 else 0.0
                    spread_bps = ((artifact_quote.ask - artifact_quote.bid) / midpoint * 10_000.0) if midpoint > 0 else 0.0
                    quality = max(0.0, min(100.0, 100.0 - spread_bps * 0.9 - artifact_quote.latency_ms * 0.08))
                    stale = (self._now() - _safe_datetime_from_iso(artifact_quote.ts)).total_seconds() > self.config.quote_stale_after_seconds  # type: ignore[arg-type]
                    results.append(
                        {
                            "symbol": symbol,
                            "venue": provider_id,
                            "bid": round(artifact_quote.bid, 6),
                            "ask": round(artifact_quote.ask, 6),
                            "spreadBps": round(spread_bps, 2),
                            "latencyMs": artifact_quote.latency_ms,
                            "qualityScore": round(quality, 2),
                            "stale": stale,
                            "ts": artifact_quote.ts,
                            "source": artifact_quote.source,
                        }
                    )
                    continue
                error_message = str(exc)
                results.append(
                    {
                        "symbol": symbol,
                        "venue": provider_id,
                        "bid": 0.0,
                        "ask": 0.0,
                        "spreadBps": 0.0,
                        "latencyMs": 0,
                        "qualityScore": 0.0,
                        "stale": True,
                        "ts": _dt_to_iso(self._now()),
                        "source": "unavailable",
                    }
                )
        return results, error_message

    def _truth_gap_domains(self, snapshot: ArtifactSnapshot) -> list[str]:
        domains: list[str] = []
        for row in snapshot.risk_events:
            if str(row.get("event_type")) != "TRUTH_OWNERSHIP_GAP":
                continue
            payload = row.get("payload")
            if isinstance(payload, dict):
                values = payload.get("domains")
                if isinstance(values, list):
                    domains.extend(str(value) for value in values if str(value))
        return sorted(set(domains))

    def _current_state(
        self,
        snapshot: ArtifactSnapshot,
        *,
        quote_error: str | None = None,
    ) -> tuple[RuntimeStateKind, str | None, str | None]:
        age_seconds = int((self._now() - snapshot.latest_artifact_at).total_seconds())
        truth_gap_domains = self._truth_gap_domains(snapshot)
        manual_review_required = bool(snapshot.manual_review.get("manual_review_required"))

        if not snapshot.manifest and not snapshot.harmony_report:
            return ("unavailable", "runtime_artifacts_missing", "Runtime artifacts missing; summary/integrity cannot be trusted.")
        if age_seconds > self.config.artifact_stale_after_seconds:
            return (
                "stale",
                "runtime_artifacts_stale",
                f"Latest runtime artifact is {_format_age(age_seconds)} old.",
            )
        if manual_review_required:
            return (
                "degraded",
                "manual_review_required",
                "Human escalation is active; runtime should be treated as degraded until acknowledged.",
            )
        if truth_gap_domains:
            return (
                "degraded",
                "truth_ownership_gap",
                f"Truth ownership gap remains for {', '.join(truth_gap_domains)}.",
            )
        if quote_error is not None:
            return (
                "partial",
                "market_quote_degraded",
                "Runtime artifacts loaded, but live public quote fetch is degraded.",
            )
        if snapshot.artifact_fallback_active:
            return (
                "partial",
                "artifact_reconstruction_active",
                "Canonical operator/replay bundles are missing; API is reconstructing state from lower-level artifacts.",
            )
        return ("healthy", None, None)

    def _provider_id(self, snapshot: ArtifactSnapshot) -> str:
        manifest = snapshot.manifest
        return str(
            manifest.get("provider_id")
            or snapshot.harmony_report.get("provider_target")
            or snapshot.provider_capability.get("provider_id")
            or "unknown_provider"
        )

    def _mode(self, snapshot: ArtifactSnapshot) -> str:
        manifest = snapshot.manifest
        return str(manifest.get("runtime_mode") or manifest.get("trading_mode") or "unknown")

    def _runtime_identity(
        self,
        snapshot: ArtifactSnapshot,
        *,
        state_kind: RuntimeStateKind,
        reason_code: str | None,
        provider_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        provider = provider_id or self._provider_id(snapshot)
        runtime_mode = mode or self._mode(snapshot)
        age_seconds = max(0, int((self._now() - snapshot.latest_artifact_at).total_seconds()))
        selection_mode = self.config.selection_mode()
        resolution_source = self.config.resolution_source()
        target_path = self.config.resolve_run_dir()

        if selection_mode == "latest":
            pin_integrity_status = "not_pinned"
            drift_status = "tracking_latest"
        elif snapshot.run_dir.resolve() != target_path.resolve():
            pin_integrity_status = "mismatch"
            drift_status = "mismatch"
        else:
            pin_integrity_status = "ok"
            drift_status = "locked"

        freshness_status = "stale" if age_seconds > self.config.artifact_stale_after_seconds else "fresh"
        if state_kind == "unavailable":
            freshness_status = "unavailable"

        return {
            "runId": snapshot.run_id,
            "runSelectionMode": selection_mode,
            "runResolutionSource": resolution_source,
            "runPath": str(snapshot.run_dir.resolve()),
            "providerId": provider,
            "mode": runtime_mode,
            "stateKind": state_kind,
            "reasonCode": reason_code or "ok",
            "driftStatus": drift_status,
            "artifactFreshness": {
                "status": freshness_status,
                "ageSeconds": age_seconds,
                "thresholdSeconds": self.config.artifact_stale_after_seconds,
                "lastArtifactUpdateAt": _dt_to_iso(snapshot.latest_artifact_at),
            },
            "startedAt": _dt_to_iso(snapshot.started_at),
            "lastArtifactUpdateAt": _dt_to_iso(snapshot.latest_artifact_at),
            "pinIntegrityStatus": pin_integrity_status,
            "schemaVersion": snapshot.manifest.get("schema_version"),
        }

    def _canonical_operator_summary(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        if snapshot.operator_summary_journal:
            return snapshot.operator_summary_journal
        return snapshot.operator_summary

    def _canonical_replay_summary(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        if snapshot.replay_summary_journal:
            return snapshot.replay_summary_journal
        return snapshot.replay_summary

    def _latest_truth_confidence(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        snapshots = [
            _as_object(row.get("payload"))
            for row in snapshot.truth_events
            if str(row.get("event_type") or "") == "TRUTH_CONFIDENCE_SNAPSHOT"
        ]
        if snapshots:
            return snapshots[-1]
        return {}

    def _artifact_quote_snapshot(self, snapshot: ArtifactSnapshot, symbol: str, provider_id: str) -> QuoteSnapshot | None:
        market_context = self._latest_market_context(snapshot)
        market_integrity = self._latest_market_integrity(snapshot)
        market_watch = self._latest_market_watch(snapshot)
        operator_summary = self._canonical_operator_summary(snapshot)
        truth_confidence = self._latest_truth_confidence(snapshot)
        market_data_truth = _as_object(truth_confidence.get("market_data_truth_confidence"))

        integrity_meta = _as_object(market_integrity.get("metadata"))
        watch_meta = _as_object(market_watch.get("metadata"))
        dead_market_reasoning = _as_object(watch_meta.get("dead_market_reasoning"))
        integrity_evidence = _as_object(integrity_meta.get("integrity_evidence"))
        capability_evidence = _as_object(integrity_meta.get("capability_evidence"))
        operator_market_context = _as_object(operator_summary.get("market_context"))
        operator_market_integrity = _as_object(operator_market_context.get("market_integrity"))
        operator_cost_model = _as_object(
            _as_object(
                _as_object(_as_object(operator_summary.get("performance_architecture")).get("execution_alpha")).get("cost_model")
            ).get("metadata")
        )

        mid_price = _optional_float(operator_cost_model.get("mid_price"))
        spread_bps = (
            _optional_float(integrity_meta.get("spread_bps"))
            or _optional_float(watch_meta.get("spread_bps"))
            or _optional_float(_as_object(operator_market_integrity.get("metadata")).get("spread_bps"))
        )
        freshness_seconds = (
            _optional_float(integrity_evidence.get("feed_age_seconds"))
            or _optional_float(capability_evidence.get("freshness_seconds"))
            or _optional_float(dead_market_reasoning.get("seconds_since_distinct_book_change"))
            or 0.0
        )
        public_market_connected = bool(dead_market_reasoning.get("public_market_data_connected"))
        truth_level = str(market_data_truth.get("level") or "").lower()
        truth_reason = str(market_data_truth.get("reason") or "").lower()
        known_symbols = {
            value
            for value in [
                _string_or_none(market_integrity.get("symbol")),
                _string_or_none(market_watch.get("symbol")),
                _string_or_none(market_context.get("symbol")),
                _string_or_none(operator_summary.get("symbol")),
            ]
            if value
        }

        if known_symbols and symbol not in known_symbols:
            return None
        if mid_price is None or mid_price <= 0 or spread_bps is None or spread_bps < 0:
            return None
        if not public_market_connected and truth_level != "authoritative":
            return None
        if truth_level not in {"authoritative", "strong"} and truth_reason != "market_data_integrity_ok":
            return None

        half_spread = mid_price * (spread_bps / 10_000.0) / 2.0
        bid = max(0.0, mid_price - half_spread)
        ask = max(bid, mid_price + half_spread)
        ts = (
            _string_or_none(market_integrity.get("ts"))
            or _string_or_none(market_watch.get("ts"))
            or _string_or_none(market_context.get("ts"))
            or _dt_to_iso(snapshot.latest_artifact_at)
        )
        return QuoteSnapshot(
            symbol=symbol,
            venue=provider_id,
            bid=bid,
            ask=ask,
            latency_ms=max(1, int(max(0.0, freshness_seconds) * 1000)),
            ts=ts,
            source="runtime_artifacts",
        )

    def _latest_account_snapshot(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        latest = _latest_row(snapshot.account_events)
        return _as_object(latest.get("payload"))

    def _latest_position_snapshot(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        latest = _latest_row(snapshot.position_events)
        return _as_object(latest.get("payload"))

    def _latest_reconciliation_report(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        report = _latest_row(snapshot.reconciliation_report)
        if report:
            return report
        return _latest_row(snapshot.reconciliation)

    def _latest_market_integrity(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        replay_summary = self._canonical_replay_summary(snapshot)
        market_context = _as_object(self._canonical_operator_summary(snapshot).get("market_context"))
        return (
            _latest_row(snapshot.market_integrity_journal)
            or _as_object(replay_summary.get("market_integrity"))
            or _as_object(market_context.get("market_integrity"))
        )

    def _latest_market_watch(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        replay_summary = self._canonical_replay_summary(snapshot)
        market_context = _as_object(self._canonical_operator_summary(snapshot).get("market_context"))
        return (
            _latest_row(snapshot.market_watch_journal)
            or _as_object(replay_summary.get("market_watch"))
            or _as_object(market_context.get("market_watch"))
        )

    def _latest_venue_limit(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        return _latest_row(snapshot.venue_limit_journal)

    def _latest_health_signal(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        return _latest_row(snapshot.health_journal)

    def _latest_control_state(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        return _latest_row(snapshot.control_journal)

    def _latest_queued_command(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        return _latest_row(_read_jsonl(self._control_outbox_path()))

    def _latest_market_context(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        return _latest_row(snapshot.market_context_summary)

    def _latest_lifecycle_summary(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        summaries = [
            row for row in snapshot.lifecycle_evidence
            if str(row.get("type") or "").lower() == "summary"
        ]
        if summaries:
            return summaries[-1]
        return _latest_row(snapshot.lifecycle_journal)

    def _user_stream_state(self, snapshot: ArtifactSnapshot) -> dict[str, Any]:
        rows = snapshot.user_stream_audit or snapshot.user_stream_events
        if not rows:
            return {
                "status": "unavailable",
                "detail": "No authenticated user stream telemetry was emitted for the active run.",
                "subscribedChannels": [],
                "lastEventType": None,
                "lastEventAt": None,
                "evidence": [],
            }

        subscribed_channels = sorted(
            {
                str(_as_object(row.get("payload")).get("subscription", {}).get("name"))
                for row in rows
                if isinstance(_as_object(row.get("payload")).get("subscription"), dict)
                and str(_as_object(row.get("payload")).get("subscription", {}).get("name"))
            }
        )
        last_row = rows[-1]
        last_event_type = _string_or_none(last_row.get("type")) or _string_or_none(last_row.get("event_type"))
        has_socket_open = any(str(row.get("type") or "").lower() == "socket_open" for row in rows)
        has_subscriptions = len(subscribed_channels) > 0
        has_token = any(str(row.get("type") or "").lower() == "token_acquired" for row in rows)
        status = "connected" if has_socket_open and has_subscriptions else ("partial" if has_token or has_socket_open else "disconnected")
        detail_bits = []
        if has_token:
            detail_bits.append("token acquired")
        if has_socket_open:
            detail_bits.append("socket open")
        if subscribed_channels:
            detail_bits.append(f"channels={','.join(subscribed_channels)}")
        if not detail_bits:
            detail_bits.append("stream handshake missing")
        return {
            "status": status,
            "detail": ", ".join(detail_bits),
            "subscribedChannels": subscribed_channels,
            "lastEventType": last_event_type,
            "lastEventAt": _string_or_none(last_row.get("ts")),
            "evidence": self._linked_artifacts(snapshot, "events_user_stream.jsonl", "user_stream_audit.jsonl"),
        }

    def _linked_artifacts(self, snapshot: ArtifactSnapshot, *names: str) -> list[str]:
        return [name for name in names if (snapshot.run_dir / name).exists()]

    def _runs_root(self) -> Path:
        return self.config.repo_root / "runs"

    def _iter_run_dirs(self) -> list[Path]:
        runs_root = self._runs_root()
        if not runs_root.exists() or not runs_root.is_dir():
            return []
        run_dirs: list[Path] = []
        for child in runs_root.iterdir():
            if child.name == "latest":
                continue
            if child.is_dir():
                run_dirs.append(child.resolve())
        return sorted(run_dirs)

    def _describe_run_dir(self, run_dir: Path) -> dict[str, Any]:
        manifest = _as_object(_read_json(run_dir / "config_manifest.json"))
        health_summary = _as_object(_read_json(run_dir / "health_summary.json"))
        report_row = _as_object(_read_json(run_dir / "report.json"))
        manual_review = _as_object(_read_json(run_dir / "MANUAL_REVIEW_REQUIRED.json"))
        relevant_paths = [
            run_dir / "config_manifest.json",
            run_dir / "health_summary.json",
            run_dir / "report.json",
            run_dir / "events_account.jsonl",
            run_dir / "events_orders.jsonl",
            run_dir / "events_positions.jsonl",
            run_dir / "events_risk.jsonl",
            run_dir / "events_truth.jsonl",
            run_dir / "market_context_summary.jsonl",
            run_dir / "market_integrity_journal.jsonl",
            run_dir / "control_journal.jsonl",
            run_dir / "lifecycle_evidence_journal.jsonl",
        ]
        mtimes = [_file_mtime(path) for path in relevant_paths]
        valid_mtimes = [mtime for mtime in mtimes if mtime is not None]
        latest_artifact_at = max(valid_mtimes) if valid_mtimes else self._now()
        started_at = min(valid_mtimes) if valid_mtimes else latest_artifact_at
        age_seconds = max(0, int((self._now() - latest_artifact_at).total_seconds()))
        state_kind: RuntimeStateKind = "healthy"
        reason_code = "ok"
        if age_seconds > self.config.artifact_stale_after_seconds:
            state_kind = "stale"
            reason_code = "runtime_artifacts_stale"
        elif bool(manual_review.get("manual_review_required")):
            state_kind = "degraded"
            reason_code = "manual_review_required"
        elif str(health_summary.get("status") or "").lower() in {"degraded", "warn", "warning"}:
            state_kind = "degraded"
            reason_code = "health_summary_degraded"
        return {
            "runId": run_dir.name,
            "runPath": str(run_dir),
            "providerId": str(manifest.get("provider_id") or "unknown_provider"),
            "mode": str(manifest.get("runtime_mode") or manifest.get("trading_mode") or "unknown"),
            "stateKind": state_kind,
            "reasonCode": reason_code,
            "startedAt": _dt_to_iso(started_at),
            "lastArtifactUpdateAt": _dt_to_iso(latest_artifact_at),
            "artifactFreshnessStatus": "stale" if age_seconds > self.config.artifact_stale_after_seconds else "fresh",
            "equity": _optional_float(report_row.get("equity")),
        }

    def runs(self) -> dict[str, Any]:
        items = [self._describe_run_dir(run_dir) for run_dir in self._iter_run_dirs()]
        items = sorted(items, key=lambda item: item.get("lastArtifactUpdateAt") or "", reverse=True)
        selection_mode = self.config.selection_mode()
        selection_target = self.config.selection_target()
        selected_run_id: str | None = None
        selected_run_path: str | None = None
        unresolved_selection = False
        runtime_identity: dict[str, Any] | None = None
        try:
            current_run_dir = self._run_dir().resolve()
            selected_run_id = current_run_dir.name
            selected_run_path = str(current_run_dir)
            snapshot = self._read_snapshot()
            state_kind, reason_code, _ = self._current_state(snapshot)
            runtime_identity = self._runtime_identity(snapshot, state_kind=state_kind, reason_code=reason_code)
        except RuntimeApiError as exc:
            if str(exc).startswith("run_not_found:"):
                unresolved_selection = True
                runtime_identity = self._selection_identity_unresolved("run_not_found")
            else:
                raise

        latest_path = self._runs_root() / "latest"
        latest_resolved: Path | None = None
        if latest_path.exists():
            try:
                latest_resolved = latest_path.resolve()
            except Exception:
                latest_resolved = None

        for item in items:
            item["current"] = bool(selected_run_id and item["runId"] == selected_run_id)
            item["latest"] = bool(latest_resolved and item["runPath"] == str(latest_resolved))

        return {
            "items": items,
            "selectionMode": selection_mode,
            "selectionTarget": selection_target,
            "resolvedRunId": selected_run_id,
            "resolvedRunPath": selected_run_path,
            "latestRunId": latest_resolved.name if latest_resolved is not None else None,
            "latestRunPath": str(latest_resolved) if latest_resolved is not None else None,
            "unresolvedSelection": unresolved_selection,
            "runtimeIdentity": runtime_identity,
            "lastUpdatedAt": _dt_to_iso(self._now()),
        }

    def select_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "").strip().lower()
        run_id = _string_or_none(payload.get("runId"))
        run_path_raw = _string_or_none(payload.get("runPath"))
        if mode not in {"latest", "pinned"}:
            raise RuntimeApiError("invalid_run_selection_mode")
        if mode == "latest":
            with self._selection_lock:
                self.config.run_dir = None
                self.config.run_id = None
            try:
                snapshot = self._read_snapshot()
                state_kind, reason_code, _ = self._current_state(snapshot)
                runtime_identity = self._runtime_identity(snapshot, state_kind=state_kind, reason_code=reason_code)
                run_id_value = snapshot.run_id
                run_path_value = str(snapshot.run_dir.resolve())
            except RuntimeApiError as exc:
                if str(exc).startswith("run_not_found:"):
                    runtime_identity = self._selection_identity_unresolved("run_not_found")
                    run_id_value = None
                    run_path_value = None
                else:
                    raise
            return {
                "accepted": True,
                "selectionMode": "latest",
                "selectionTarget": self.config.selection_target(),
                "runId": run_id_value,
                "runPath": run_path_value,
                "runtimeIdentity": runtime_identity,
                "operatorMessage": "Runtime API is now tracking the latest run.",
                "ts": _dt_to_iso(self._now()),
            }

        if bool(run_id) == bool(run_path_raw):
            raise RuntimeApiError("pinned_run_requires_exactly_one_of_runId_or_runPath")
        run_path = Path(run_path_raw).expanduser().resolve() if run_path_raw else (self._runs_root() / str(run_id)).resolve()
        if not run_path.exists() or not run_path.is_dir():
            raise RuntimeApiError(f"run_not_found:{run_path}")
        with self._selection_lock:
            self.config.run_dir = run_path if run_path_raw else None
            self.config.run_id = str(run_id or run_path.name) if not run_path_raw else None
        snapshot = self._read_snapshot()
        state_kind, reason_code, _ = self._current_state(snapshot)
        runtime_identity = self._runtime_identity(snapshot, state_kind=state_kind, reason_code=reason_code)
        return {
            "accepted": True,
            "selectionMode": "pinned",
            "selectionTarget": self.config.selection_target(),
            "runId": snapshot.run_id,
            "runPath": str(snapshot.run_dir.resolve()),
            "runtimeIdentity": runtime_identity,
            "operatorMessage": f"Runtime API pinned to {snapshot.run_id}.",
            "ts": _dt_to_iso(self._now()),
        }

    def summary(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        symbols, quote_error = self._build_symbols(snapshot)
        state_kind, reason_code, reason_text = self._current_state(snapshot, quote_error=quote_error)

        manifest = snapshot.manifest
        live_gate = _as_object(manifest.get("live_gate_status"))
        provider_id = self._provider_id(snapshot)
        mode = self._mode(snapshot)
        equity = _coerce_float(snapshot.report_row.get("equity"), 0.0)
        latest_position = _latest_row(snapshot.position_events)
        exposure_notional = _coerce_float(_as_object(latest_position.get("payload")).get("exposure_notional"))
        open_positions = 1 if exposure_notional > 0 else 0
        open_orders = len(snapshot.order_plans)
        free_cash = max(0.0, equity if open_positions == 0 and open_orders == 0 else equity - exposure_notional)
        avg_latency = sum(item["latencyMs"] for item in symbols) / len(symbols) if symbols else 0.0
        runtime_identity = self._runtime_identity(
            snapshot,
            state_kind=state_kind,
            reason_code=reason_code,
            provider_id=provider_id,
            mode=mode,
        )
        performance = snapshot.performance_artifacts
        capital_util = _as_object(performance.get("capital_utilization_diagnostics"))
        expectancy = _as_object(performance.get("expectancy_engine_report"))
        maker_mix = _as_object(performance.get("maker_taker_mix_report"))
        target_gap = _as_object(performance.get("performance_gap_report"))

        return {
            "providerId": provider_id,
            "mode": mode,
            "runId": snapshot.run_id,
            "runSelection": {
                "mode": self.config.selection_mode(),
                "target": self.config.selection_target(),
                "resolvedRunDir": str(snapshot.run_dir.resolve()),
            },
            "runtimeIdentity": runtime_identity,
            "startedAt": _dt_to_iso(snapshot.started_at),
            "uptimeSec": max(0, int((snapshot.latest_artifact_at - snapshot.started_at).total_seconds())),
            "equityEur": round(equity, 2),
            "freeCashEur": round(free_cash, 2),
            "openPositions": open_positions,
            "openOrders": open_orders,
            "avgLatencyMs": round(avg_latency, 2),
            "wsConnected": bool(live_gate.get("event_feed_configured")),
            "restHealthy": quote_error is None,
            "stateKind": state_kind,
            "reasonCode": reason_code,
            "reasonText": reason_text,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "performance": {
                "capitalUtilizationPct": _optional_float(capital_util.get("capital_utilization_pct")),
                "netExpectancyBps": _optional_float(expectancy.get("net_expectancy_bps")),
                "fillRate": _optional_float(_as_object(expectancy.get("metadata")).get("fill_rate")),
                "makerRatio": _optional_float(maker_mix.get("maker_probability")),
                "targetGap": _as_object(target_gap.get("gaps")),
            },
        }

    def symbols(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        items, quote_error = self._build_symbols(snapshot)
        state_kind, reason_code, reason_text = self._current_state(snapshot, quote_error=quote_error)
        return {
            "items": items,
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "reasonCode": reason_code,
            "reasonText": reason_text,
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=reason_code,
            ),
        }

    def decisions(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        truth_gap_domains = self._truth_gap_domains(snapshot)
        manual_review = snapshot.manual_review
        items: list[dict[str, Any]] = []
        for row in snapshot.mastermind_journal[-8:]:
            symbol = str(row.get("symbol") or "UNKNOWN")
            ts = str(row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at))
            reasons = [str(reason) for reason in row.get("reasons", []) if str(reason)]
            if truth_gap_domains:
                reasons.extend(f"truth_gap:{domain}" for domain in truth_gap_domains)
            if manual_review.get("manual_review_required"):
                reasons.append("manual_review_required")
            unique_reasons = list(dict.fromkeys(reasons))
            veto = bool(row.get("veto"))
            risk_verdict = "block" if veto or manual_review.get("manual_review_required") else ("watch" if unique_reasons else "allow")
            items.append(
                {
                    "id": _hash_id(symbol, ts, str(row.get("decision"))),
                    "symbol": symbol,
                    "ts": ts,
                    "intent": str(row.get("decision") or "UNKNOWN").lower(),
                    "confidence": round(_coerce_float(row.get("confidence"), 0.0), 4),
                    "expectedEdgeBps": round(
                        _coerce_float(_as_object(row.get("raw")).get("forecast_edge_bps"), 0.0),
                        4,
                    ),
                    "blockers": unique_reasons,
                    "topReasons": unique_reasons[:3],
                    "riskVerdict": risk_verdict,
                    "lastAction": "manual_review" if manual_review.get("manual_review_required") else str(row.get("decision") or "wait").lower(),
                }
            )
        state_kind, reason_code, reason_text = self._current_state(snapshot)
        return {
            "items": list(reversed(items)),
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "reasonCode": reason_code,
            "reasonText": reason_text,
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=reason_code,
            ),
        }

    def alerts(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        items: list[dict[str, Any]] = []
        truth_gap_domains = self._truth_gap_domains(snapshot)
        if snapshot.manual_review.get("manual_review_required"):
            items.append(
                {
                    "id": _hash_id("manual_review", str(snapshot.manual_review.get("ts"))),
                    "severity": "critical",
                    "module": "human-escalation",
                    "message": "Manual review required before continuation.",
                    "ts": str(snapshot.manual_review.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                }
            )
        for domain in truth_gap_domains:
            items.append(
                {
                    "id": _hash_id("truth_gap", domain),
                    "severity": "warn",
                    "module": "truth-ownership",
                    "message": f"Truth ownership gap detected for {domain}.",
                    "ts": _dt_to_iso(snapshot.latest_artifact_at),
                }
            )
        if snapshot.artifact_fallback_active:
            items.append(
                {
                    "id": _hash_id("artifact_fallback", snapshot.run_id),
                    "severity": "warn",
                    "module": "runtime-api",
                    "message": "Canonical runtime bundles missing; reconstructed artifact mode is active.",
                    "ts": _dt_to_iso(snapshot.latest_artifact_at),
                }
            )
        live_gate = _as_object(snapshot.manifest.get("live_gate_status"))
        if not bool(live_gate.get("live_ordering_enabled", False)):
            items.append(
                {
                    "id": _hash_id("live_ordering_disabled", snapshot.run_id),
                    "severity": "info",
                    "module": "safety-gate",
                    "message": "Live ordering remains disabled by rollout gate.",
                    "ts": _dt_to_iso(snapshot.latest_artifact_at),
                }
            )
        outbox_lines = _read_jsonl(self._control_outbox_path())
        if outbox_lines:
            latest_outbox = outbox_lines[-1]
            items.append(
                {
                    "id": _hash_id("control_outbox", str(latest_outbox.get("auditReference"))),
                    "severity": "info",
                    "module": "control-outbox",
                    "message": f"Pending operator command: {latest_outbox.get('action', 'unknown')}.",
                    "ts": str(latest_outbox.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                }
            )
        state_kind, _, _ = self._current_state(snapshot)
        return {
            "items": items,
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=None,
            ),
        }

    def health(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        symbols, quote_error = self._build_symbols(snapshot)
        state_kind, _, reason_text = self._current_state(snapshot, quote_error=quote_error)
        age_seconds = int((self._now() - snapshot.latest_artifact_at).total_seconds())
        live_gate = _as_object(snapshot.manifest.get("live_gate_status"))
        warnings = list(snapshot.warnings)
        if reason_text:
            warnings.append(reason_text)
        details = [
            {
                "label": "Run directory",
                "value": str(snapshot.run_dir),
                "severity": "info",
            },
            {
                "label": "Artifact age",
                "value": _format_age(age_seconds),
                "severity": _state_tone("stale" if age_seconds > self.config.artifact_stale_after_seconds else "healthy"),
            },
            {
                "label": "Artifact fallback",
                "value": "active" if snapshot.artifact_fallback_active else "inactive",
                "severity": "warn" if snapshot.artifact_fallback_active else "good",
            },
            {
                "label": "Public quote path",
                "value": "healthy" if quote_error is None else "degraded",
                "severity": "good" if quote_error is None else "warn",
            },
            {
                "label": "Event feed",
                "value": "configured" if bool(live_gate.get("event_feed_configured")) else "not configured",
                "severity": "good" if bool(live_gate.get("event_feed_configured")) else "info",
            },
            {
                "label": "Open quote snapshots",
                "value": str(len(symbols)),
                "severity": "info",
            },
        ]
        return {
            "status": _health_status(state_kind),
            "bridgeHealthy": state_kind not in {"error", "unavailable"},
            "backendHealthy": bool(snapshot.manifest or snapshot.harmony_report),
            "artifactFallbackActive": snapshot.artifact_fallback_active,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "warnings": warnings,
            "details": details,
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=None,
            ),
        }

    def integrity(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        state_kind, _, _ = self._current_state(snapshot)
        truth_gap_domains = self._truth_gap_domains(snapshot)
        latest_doctrine = _latest_row(snapshot.doctrine_summary)
        latest_reconciliation = _latest_row(snapshot.reconciliation)
        live_gate = _as_object(snapshot.manifest.get("live_gate_status"))
        blockers: list[str] = []
        warnings = list(snapshot.warnings)
        if snapshot.manual_review.get("manual_review_required"):
            blockers.append("manual_review_required")
        blockers.extend(f"truth_gap:{domain}" for domain in truth_gap_domains)
        doctrine_reasons = _as_object(latest_doctrine.get("decision_doctrine")).get("reasons", [])
        blockers.extend(str(reason) for reason in doctrine_reasons[:3] if str(reason))
        blockers = list(dict.fromkeys(blockers))
        capability_confidence = (
            str(snapshot.provider_capability_journal.get("realized_pnl_truth_support"))
            or str(snapshot.provider_capability.get("realized_pnl_truth_support"))
            or "unknown"
        )
        details = [
            {
                "label": "Doctrine action",
                "value": str(_as_object(latest_doctrine.get("decision_doctrine")).get("recommended_action") or "unknown"),
                "severity": _severity_to_tone("warn" if blockers else "good"),
            },
            {
                "label": "Capability confidence",
                "value": capability_confidence,
                "severity": "info" if "authoritative" in capability_confidence else "warn",
            },
            {
                "label": "Reconciliation",
                "value": str(latest_reconciliation.get("code") or "missing"),
                "severity": "good" if bool(latest_reconciliation.get("ok")) else "warn",
            },
            {
                "label": "Live ordering",
                "value": "enabled" if bool(live_gate.get("live_ordering_enabled")) else "disabled",
                "severity": "good" if bool(live_gate.get("live_ordering_enabled")) else "warn",
            },
        ]
        if truth_gap_domains:
            warnings.append(f"Truth gaps remain in {', '.join(truth_gap_domains)}.")
        return {
            "doctrineStatus": str(_as_object(latest_doctrine.get("decision_doctrine")).get("recommended_action") or "unknown"),
            "capabilityConfidence": capability_confidence,
            "blockers": blockers,
            "unlockActions": [
                "emit canonical operator/replay bundles",
                "close truth ownership gaps",
                "wire runtime command bridge",
            ],
            "warnings": warnings,
            "degradationState": "reconstructed_artifact_runtime" if snapshot.artifact_fallback_active else "direct_runtime_bundle",
            "details": details,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "stateKind": state_kind,
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=None,
            ),
        }

    def replay(self, run_id: str) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        if run_id not in {snapshot.run_id, "latest"}:
            raise RuntimeApiError(f"run_not_found:{run_id}")

        timeline: list[dict[str, Any]] = []
        for row in snapshot.truth_events[-4:] + snapshot.risk_events[-4:] + snapshot.position_events[-2:]:
            timeline.append(
                {
                    "label": str(row.get("event_type") or "runtime-event").replace("_", " ").title(),
                    "detail": _payload_summary(_as_object(row.get("payload"))),
                    "ts": str(row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": _severity_to_tone(str(row.get("event_type", ""))),
                }
            )

        incidents: list[dict[str, Any]] = []
        if snapshot.manual_review:
            incidents.append(
                {
                    "label": "Manual review",
                    "detail": ", ".join(str(reason) for reason in snapshot.manual_review.get("reasons", [])) or "Manual review requested.",
                    "ts": str(snapshot.manual_review.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": "danger",
                }
            )
        for row in snapshot.risk_events[-4:]:
            incidents.append(
                {
                    "label": str(row.get("event_type") or "risk-event").replace("_", " ").title(),
                    "detail": _payload_summary(_as_object(row.get("payload"))),
                    "ts": str(row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": "warn",
                }
            )
        for row in _read_jsonl(self._incident_notes_path())[-4:]:
            incidents.append(
                {
                    "label": "Operator note",
                    "detail": str(row.get("note") or "no note"),
                    "ts": str(row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": "info",
                }
            )

        analog_matches: list[dict[str, Any]] = []
        for row in snapshot.mastermind_journal[-3:]:
            analog_matches.append(
                {
                    "label": str(row.get("signal") or "mastermind").replace("_", " ").title(),
                    "detail": str(row.get("reason") or "No analogous regime note."),
                    "ts": str(row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": "info",
                }
            )

        counterfactuals: list[dict[str, Any]] = []
        for row in snapshot.capital_strategy[-3:]:
            capital = _as_object(row.get("capital_sovereignty"))
            affect = _as_object(row.get("synthetic_affect"))
            counterfactuals.append(
                {
                    "label": "Capital posture",
                    "detail": f"capital={capital.get('action', 'unknown')} affect={affect.get('recommended_action', 'unknown')}",
                    "ts": str(capital.get("ts") or row.get("ts") or _dt_to_iso(snapshot.latest_artifact_at)),
                    "severity": "info",
                }
            )

        pnl_attribution = [
            {
                "label": "Equity",
                "detail": f"Reported paper equity {snapshot.report_row.get('equity', 0.0)}.",
                "ts": _dt_to_iso(snapshot.latest_artifact_at),
                "severity": "info",
            },
            {
                "label": "Fills",
                "detail": f"{len(snapshot.fills)} accepted fills recorded.",
                "ts": _dt_to_iso(snapshot.latest_artifact_at),
                "severity": "good" if snapshot.fills else "info",
            },
            {
                "label": "Reconciliation",
                "detail": str(_latest_row(snapshot.reconciliation).get("code") or "missing"),
                "ts": _dt_to_iso(snapshot.latest_artifact_at),
                "severity": "good" if bool(_latest_row(snapshot.reconciliation).get("ok")) else "warn",
            },
        ]

        notes = [
            {
                "label": "Truth ownership",
                "detail": f"{len(snapshot.truth_ownership)} declared domains.",
                "ts": _dt_to_iso(snapshot.latest_artifact_at),
                "severity": "info",
            },
            {
                "label": "Artifact fallback",
                "detail": "active" if snapshot.artifact_fallback_active else "inactive",
                "ts": _dt_to_iso(snapshot.latest_artifact_at),
                "severity": "warn" if snapshot.artifact_fallback_active else "good",
            },
        ]

        state_kind, _, _ = self._current_state(snapshot)
        return {
            "runId": snapshot.run_id,
            "timeline": timeline,
            "incidents": incidents,
            "analogMatches": analog_matches,
            "counterfactuals": counterfactuals,
            "pnlAttribution": pnl_attribution,
            "notes": notes,
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "runtimeIdentity": self._runtime_identity(
                snapshot,
                state_kind=state_kind,
                reason_code=None,
            ),
        }

    def brain(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        symbols, quote_error = self._build_symbols(snapshot)
        state_kind, reason_code, reason_text = self._current_state(snapshot, quote_error=quote_error)
        runtime_identity = self._runtime_identity(
            snapshot,
            state_kind=state_kind,
            reason_code=reason_code,
        )

        operator_summary = self._canonical_operator_summary(snapshot)
        replay_summary = self._canonical_replay_summary(snapshot)
        current_decision = _latest_row(snapshot.mastermind_journal)
        decision_raw = _as_object(current_decision.get("raw"))
        explainability = snapshot.decision_explainability or _as_object(operator_summary.get("explainability"))
        live_safety = snapshot.live_safety_summary
        latest_reconciliation = self._latest_reconciliation_report(snapshot)
        market_integrity = self._latest_market_integrity(snapshot)
        market_watch = self._latest_market_watch(snapshot)
        market_context = _as_object(operator_summary.get("market_context"))
        forecast = _as_object(market_context.get("forecast"))
        execution_quality = _as_object(market_context.get("execution_quality"))
        performance = snapshot.performance_artifacts
        opportunity_ranking = _as_object(performance.get("decision_ranking_explainability"))
        backlog_report = _as_object(performance.get("opportunity_backlog_report"))
        false_negative = _as_object(performance.get("false_negative_report"))
        false_positive = _as_object(performance.get("false_positive_report"))

        selected_symbol = (
            _string_or_none(current_decision.get("symbol"))
            or _string_or_none(replay_summary.get("symbol"))
            or _string_or_none(market_integrity.get("symbol"))
            or _string_or_none(market_watch.get("symbol"))
            or _string_or_none(snapshot.manifest.get("symbol"))
            or "UNKNOWN"
        )

        explainability_reasons = [str(value) for value in explainability.get("reason_codes", []) if str(value)]
        decision_reasons = [str(value) for value in current_decision.get("reasons", []) if str(value)]
        blocking_reasons = list(
            dict.fromkeys(
                [
                    *[str(value) for value in live_safety.get("blocking_reasons", []) if str(value)],
                    *decision_reasons,
                    *explainability_reasons,
                ]
            )
        )
        why_trade = [
            detail
            for detail in [
                _string_or_none(_as_object(explainability.get("investor_rationale")).get("thesis")),
                _string_or_none(current_decision.get("reason")),
                _string_or_none(_as_object(execution_quality.get("reasons")).get("liquidity_regime")),
            ]
            if detail
        ]
        why_not_trade = [
            detail
            for detail in [
                _string_or_none(_as_object(explainability.get("investor_rationale")).get("capital_protection")),
                _string_or_none(live_safety.get("preflight_reason")),
                blocking_reasons[0] if blocking_reasons else None,
            ]
            if detail
        ]
        supporting_signals = list(
            dict.fromkeys(
                [
                    *_as_object(market_watch.get("metadata")).get("regime_score_table", {}).keys(),
                    _string_or_none(current_decision.get("signal")) or "",
                    _string_or_none(decision_raw.get("regime")) or "",
                ]
            )
        )
        supporting_signals = [value for value in supporting_signals if value]

        cost_adjusted_edge_bps = (
            _optional_float(_as_object(operator_summary.get("decision")).get("net_edge_bps"))
            if operator_summary
            else None
        )
        if cost_adjusted_edge_bps is None:
            execution_plan = _as_object(_as_object(operator_summary.get("decision")).get("execution_plan"))
            components = execution_plan.get("reasons", {}).get("components", [])
            if isinstance(components, list) and components:
                cost_adjusted_edge_bps = _optional_float(_as_object(components[0]).get("net_after_cost_bps"))

        def step_status_from_flag(flag: bool | None, *, warn_on_false: bool = False) -> str:
            if flag is None:
                return "unavailable"
            if flag:
                return "pass"
            return "warn" if warn_on_false else "fail"

        artifact_age_ms = runtime_identity["artifactFreshness"]["ageSeconds"] * 1000
        pipeline = [
            {
                "id": "market_ingest",
                "title": "Market ingest",
                "status": "pass" if symbols else "unavailable",
                "reasonCodes": [quote_error] if quote_error else [],
                "latencyMs": None,
                "timestamp": symbols[0]["ts"] if symbols else _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": f"provider={self._provider_id(snapshot)} universe={len(symbols)} symbols",
                "outputSummary": "live public quote snapshots loaded" if symbols else "no symbol snapshots available",
                "evidence": ["config_manifest.json", "market_integrity_journal.jsonl"],
                "derived": False,
            },
            {
                "id": "freshness_validation",
                "title": "Freshness validation",
                "status": "fail" if runtime_identity["artifactFreshness"]["status"] == "stale" else "pass",
                "reasonCodes": [runtime_identity["reasonCode"]] if runtime_identity["reasonCode"] != "ok" else [],
                "latencyMs": artifact_age_ms,
                "timestamp": runtime_identity["lastArtifactUpdateAt"],
                "inputSummary": f"threshold={runtime_identity['artifactFreshness']['thresholdSeconds']}s",
                "outputSummary": f"age={runtime_identity['artifactFreshness']['ageSeconds']}s",
                "evidence": ["runtime_fingerprint.json", "health_summary.json"],
                "derived": False,
            },
            {
                "id": "feature_computation",
                "title": "Feature computation",
                "status": "pass" if decision_raw else "unavailable",
                "reasonCodes": [],
                "latencyMs": None,
                "timestamp": _string_or_none(current_decision.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": f"raw_feature_fields={len(decision_raw)}",
                "outputSummary": _payload_summary(
                    {
                        "regime": decision_raw.get("regime"),
                        "spread_bps": decision_raw.get("spread_bps"),
                        "forecast_confidence": decision_raw.get("forecast_confidence"),
                    }
                ),
                "evidence": ["mastermind_journal.jsonl"],
                "derived": False,
            },
            {
                "id": "forecast_policy",
                "title": "Forecast / policy",
                "status": "pass" if explainability or forecast else "unavailable",
                "reasonCodes": explainability_reasons,
                "latencyMs": None,
                "timestamp": _string_or_none(_as_object(forecast).get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "decision explainability and forecast bundle",
                "outputSummary": _payload_summary(
                    {
                        "action_state": explainability.get("action_state"),
                        "forecast_regime": _as_object(explainability.get("operator_rationale")).get("forecast_regime")
                        or forecast.get("regime"),
                        "doctrine_action": _as_object(explainability.get("operator_rationale")).get("doctrine_action"),
                    }
                ),
                "evidence": ["decision_explainability.json", "kraken_spot_operator_summary.json"],
                "derived": False,
            },
            {
                "id": "opportunity_scoring",
                "title": "Opportunity scoring",
                "status": "pass" if decision_raw or cost_adjusted_edge_bps is not None else "unavailable",
                "reasonCodes": [],
                "latencyMs": None,
                "timestamp": _string_or_none(current_decision.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "mastermind raw edge / operator decision net edge",
                "outputSummary": (
                    f"net_after_cost_bps={round(cost_adjusted_edge_bps, 2)}"
                    if cost_adjusted_edge_bps is not None
                    else f"forecast_edge_bps={round(_coerce_float(decision_raw.get('forecast_edge_bps'), 0.0), 2)}"
                ),
                "evidence": ["mastermind_journal.jsonl", "kraken_spot_operator_summary.jsonl"],
                "derived": cost_adjusted_edge_bps is None,
            },
            {
                "id": "risk_gating",
                "title": "Risk gating",
                "status": "fail"
                if str(market_integrity.get("action") or "").lower() in {"halt", "block", "flatten_only"}
                else ("warn" if market_integrity.get("reasons") else "pass"),
                "reasonCodes": [str(value) for value in market_integrity.get("reasons", []) if str(value)],
                "latencyMs": None,
                "timestamp": _string_or_none(market_integrity.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "market_integrity + live_safety summary",
                "outputSummary": _payload_summary(
                    {
                        "action": market_integrity.get("action"),
                        "confidence": market_integrity.get("confidence"),
                        "score": market_integrity.get("score"),
                    }
                ),
                "evidence": ["market_integrity_journal.jsonl", "live_safety_summary.json"],
                "derived": False,
            },
            {
                "id": "execution_eligibility",
                "title": "Execution eligibility",
                "status": step_status_from_flag(
                    bool(live_safety.get("ordering_allowed")) and bool(live_safety.get("preflight_ok")),
                ),
                "reasonCodes": [str(value) for value in live_safety.get("blocking_reasons", []) if str(value)],
                "latencyMs": None,
                "timestamp": _string_or_none(live_safety.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "live ordering gate, preflight, restart-state confidence",
                "outputSummary": _payload_summary(
                    {
                        "ordering_allowed": live_safety.get("ordering_allowed"),
                        "preflight_ok": live_safety.get("preflight_ok"),
                        "preflight_reason": live_safety.get("preflight_reason"),
                    }
                ),
                "evidence": ["live_safety_summary.json", "readiness_summary.json"],
                "derived": False,
            },
            {
                "id": "order_intent",
                "title": "Order intent",
                "status": "pass" if current_decision else "unavailable",
                "reasonCodes": decision_reasons,
                "latencyMs": None,
                "timestamp": _string_or_none(current_decision.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "latest mastermind journal row",
                "outputSummary": _payload_summary(
                    {
                        "decision": current_decision.get("decision"),
                        "signal": current_decision.get("signal"),
                        "confidence": current_decision.get("confidence"),
                    }
                ),
                "evidence": ["mastermind_journal.jsonl"],
                "derived": False,
            },
            {
                "id": "submission_result",
                "title": "Submission result",
                "status": "fail"
                if _coerce_int(snapshot.health_summary.get("orders_submitted"), 0) == 0
                and not bool(live_safety.get("ordering_allowed"))
                else ("pass" if _coerce_int(snapshot.health_summary.get("orders_submitted"), 0) > 0 else "unavailable"),
                "reasonCodes": [str(value) for value in snapshot.health_summary.get("blocking_reasons", []) if str(value)],
                "latencyMs": None,
                "timestamp": _string_or_none(snapshot.health_summary.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "health summary execution counters",
                "outputSummary": _payload_summary(
                    {
                        "execution_attempts": snapshot.health_summary.get("execution_attempts"),
                        "orders_submitted": snapshot.health_summary.get("orders_submitted"),
                        "fills": snapshot.health_summary.get("fills"),
                    }
                ),
                "evidence": ["health_summary.json", "events_orders.jsonl"],
                "derived": False,
            },
            {
                "id": "reconciliation_result",
                "title": "Reconciliation result",
                "status": "pass"
                if bool(latest_reconciliation.get("ok") or latest_reconciliation.get("preflight_ok"))
                else ("warn" if latest_reconciliation else "unavailable"),
                "reasonCodes": [str(latest_reconciliation.get("reason") or latest_reconciliation.get("code") or "")]
                if latest_reconciliation
                else [],
                "latencyMs": None,
                "timestamp": _string_or_none(_as_object(latest_reconciliation.get("recovery")).get("ts"))
                or _dt_to_iso(snapshot.latest_artifact_at),
                "inputSummary": "reconciliation report / journal",
                "outputSummary": _payload_summary(
                    {
                        "preflight_ok": latest_reconciliation.get("preflight_ok"),
                        "action": _as_object(latest_reconciliation.get("recovery")).get("action"),
                        "confidence": latest_reconciliation.get("restart_state_confidence"),
                    }
                ),
                "evidence": ["reconciliation_report.jsonl", "reconciliation_journal.jsonl"],
                "derived": False,
            },
        ]

        symbol_views: list[dict[str, Any]] = []
        for symbol_row in symbols[: max(1, min(len(symbols), 6))]:
            symbol = str(symbol_row.get("symbol") or selected_symbol)
            decision_for_symbol = next((row for row in reversed(snapshot.mastermind_journal) if str(row.get("symbol")) == symbol), current_decision)
            decision_for_symbol = decision_for_symbol or {}
            decision_raw_row = _as_object(decision_for_symbol.get("raw"))
            market_watch_for_symbol = market_watch if str(market_watch.get("symbol") or selected_symbol) == symbol else {}
            derived_fields: list[str] = []
            next_eligible_action = None
            if bool(live_safety.get("ordering_allowed")) and not decision_for_symbol.get("reasons"):
                next_eligible_action = str(decision_for_symbol.get("decision") or "continue").lower()
                derived_fields.append("nextEligibleAction derived from latest decision plus live ordering gate")
            elif live_safety:
                next_eligible_action = "blocked"
                derived_fields.append("nextEligibleAction derived from live_safety ordering gate")

            symbol_views.append(
                {
                    "symbol": symbol,
                    "venue": str(symbol_row.get("venue") or self._provider_id(snapshot)),
                    "bid": _optional_float(symbol_row.get("bid")),
                    "ask": _optional_float(symbol_row.get("ask")),
                    "spreadBps": _optional_float(symbol_row.get("spreadBps")),
                    "depthNotional": _optional_float(_as_object(market_watch_for_symbol.get("metadata")).get("depth_notional")),
                    "signal": _string_or_none(decision_for_symbol.get("signal")),
                    "forecast": _string_or_none(decision_raw_row.get("regime"))
                    or _string_or_none(_as_object(market_watch_for_symbol.get("metadata")).get("forecast_regime")),
                    "confidence": _optional_float(decision_for_symbol.get("confidence")),
                    "currentBlockReason": (
                        [str(value) for value in decision_for_symbol.get("reasons", []) if str(value)][0]
                        if decision_for_symbol.get("reasons")
                        else (
                            [str(value) for value in market_watch_for_symbol.get("reasons", []) if str(value)][0]
                            if market_watch_for_symbol.get("reasons")
                            else None
                        )
                    ),
                    "lastAction": _string_or_none(decision_for_symbol.get("decision")) or _string_or_none(explainability.get("action_state")),
                    "nextEligibleAction": next_eligible_action,
                    "derivedFields": derived_fields,
                    "ts": _string_or_none(symbol_row.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                }
            )

        replay_payload = self.replay(snapshot.run_id)
        evidence_items = [
            *replay_payload.get("incidents", [])[:3],
            *replay_payload.get("notes", [])[:3],
            *replay_payload.get("pnlAttribution", [])[:2],
        ]

        return {
            "runId": snapshot.run_id,
            "selectedSymbol": selected_symbol,
            "actionState": str(explainability.get("action_state") or _string_or_none(current_decision.get("decision")) or "unavailable"),
            "whyTrade": why_trade,
            "whyNotTrade": why_not_trade,
            "blockingReasons": blocking_reasons,
            "supportingSignals": supporting_signals,
            "costAdjustedEdgeBps": cost_adjusted_edge_bps,
            "costAdjustedEdgeSource": "operator_summary.decision.net_edge_bps"
            if cost_adjusted_edge_bps is not None
            else None,
            "sellFloorStatus": (
                f"min_net_profit_bps={live_safety.get('capital_protection', {}).get('minimum_sell_net_profit_bps')} "
                f"net_profit_sell_block={live_safety.get('capital_protection', {}).get('net_profit_sell_block')}"
                if live_safety.get("capital_protection")
                else "unavailable"
            ),
            "marketRegime": _string_or_none(_as_object(market_watch.get("metadata")).get("forecast_regime"))
            or _string_or_none(decision_raw.get("regime"))
            or _string_or_none(_as_object(explainability.get("operator_rationale")).get("forecast_regime"))
            or "unavailable",
            "riskGatingOutcome": str(market_integrity.get("action") or "unavailable"),
            "executionEligibilityOutcome": (
                "ordering_allowed"
                if bool(live_safety.get("ordering_allowed"))
                else str(live_safety.get("preflight_reason") or "blocked")
            ),
            "pipeline": pipeline,
            "symbolViews": symbol_views,
            "decisionReplay": {
                "finalVerdict": str(explainability.get("action_state") or current_decision.get("decision") or "unavailable"),
                "timeline": replay_payload.get("timeline", []),
                "evidence": evidence_items,
                "linkedArtifacts": self._linked_artifacts(
                    snapshot,
                    "decision_explainability.json",
                    "kraken_spot_operator_summary.json",
                    "kraken_spot_replay_summary.json",
                    "live_safety_summary.json",
                    "market_integrity_journal.jsonl",
                    "market_watch_journal.jsonl",
                    "mastermind_journal.jsonl",
                    "reconciliation_report.jsonl",
                ),
            },
            "evidenceNotes": [
                "costAdjustedEdgeBps is only populated when a direct net-after-cost field exists in runtime artifacts.",
                "nextEligibleAction is marked derived when inferred from decision intent plus current live ordering gate.",
                *( [reason_text] if reason_text else [] ),
            ],
            "opportunityRanking": {
                "selectedPlaybook": _string_or_none(opportunity_ranking.get("selected_playbook")),
                "selectedScore": _optional_float(opportunity_ranking.get("selected_score")),
                "backlogPressure": _optional_float(backlog_report.get("backlog_pressure")),
                "falseNegativeRate": _optional_float(false_negative.get("false_negative_rate")),
                "falsePositiveRate": _optional_float(false_positive.get("false_positive_rate")),
                "topCandidates": [
                    {
                        "symbol": _string_or_none(_as_object(candidate).get("symbol")) or "UNKNOWN",
                        "playbook": _string_or_none(_as_object(candidate).get("playbook")) or "unknown",
                        "score": _coerce_float(_as_object(candidate).get("score"), 0.0),
                        "netEdgeBps": _optional_float(
                            _as_object(candidate).get("net_edge_bps")
                            if _as_object(candidate).get("net_edge_bps") is not None
                            else _as_object(candidate).get("net_after_cost_bps")
                        ),
                        "qualityOfEdge": _optional_float(_as_object(candidate).get("quality_of_edge")),
                        "executionPreference": _string_or_none(_as_object(candidate).get("execution_preference")),
                    }
                    for candidate in list(opportunity_ranking.get("ranked_candidates", []) or [])[:5]
                ],
            },
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "runtimeIdentity": runtime_identity,
        }

    def shield(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        state_kind, reason_code, reason_text = self._current_state(snapshot)
        runtime_identity = self._runtime_identity(
            snapshot,
            state_kind=state_kind,
            reason_code=reason_code,
        )
        live_safety = snapshot.live_safety_summary
        readiness = snapshot.readiness_summary
        health_summary = snapshot.health_summary
        market_integrity = self._latest_market_integrity(snapshot)
        market_context = self._latest_market_context(snapshot)
        venue_limit = self._latest_venue_limit(snapshot)
        health_signal = self._latest_health_signal(snapshot)
        control_state = self._latest_control_state(snapshot)
        queued_command = self._latest_queued_command(snapshot)
        user_stream_state = self._user_stream_state(snapshot)
        operator_summary = self._canonical_operator_summary(snapshot)
        performance = snapshot.performance_artifacts
        promotion_gate = _as_object(performance.get("promotion_gate_report"))
        rollback_trigger = _as_object(performance.get("rollback_trigger_report"))
        recovery_mode_report = _as_object(performance.get("recovery_mode_report"))
        live_degradation_report = _as_object(performance.get("live_degradation_detector_report"))
        self_throttling_report = _as_object(performance.get("self_throttling_state_report"))
        private_stream_health = _as_object(performance.get("private_stream_health"))
        performance_gap = _as_object(performance.get("performance_gap_report"))
        rollout_readiness = _as_object(performance.get("rollout_readiness_report"))
        live_gate = _as_object(_as_object(operator_summary.get("harmony")).get("live_gate_status"))
        rollout_profile = _as_object(live_gate.get("rollout_profile")) or _as_object(
            _as_object(operator_summary.get("harmony")).get("rollout_profile")
        )
        latest_account = self._latest_account_snapshot(snapshot)
        latest_position = self._latest_position_snapshot(snapshot)
        observed_exposure = _optional_float(latest_position.get("exposure_notional"))
        if observed_exposure is None:
            observed_exposure = _optional_float(latest_account.get("gross_exposure_notional"))
        spread_bps = _optional_float(_as_object(market_integrity.get("metadata")).get("spread_bps"))
        depth_notional = _optional_float(_as_object(market_integrity.get("metadata")).get("depth_notional"))

        trust_reasons: list[str] = []
        if runtime_identity["pinIntegrityStatus"] in {"mismatch", "unresolved"}:
            trust_reasons.append(f"pin_integrity:{runtime_identity['pinIntegrityStatus']}")
        if runtime_identity["driftStatus"] in {"mismatch", "unresolved"}:
            trust_reasons.append(f"runtime_drift:{runtime_identity['driftStatus']}")
        if state_kind in {"error", "unavailable"}:
            trust_reasons.append(f"runtime_state:{state_kind}")
        if state_kind in {"stale", "degraded", "partial"}:
            trust_reasons.append(f"runtime_state:{state_kind}")
        if not bool(live_safety.get("safety_ready", True)):
            trust_reasons.append("safety_ready:false")
        if venue_limit:
            trust_reasons.extend(str(value) for value in venue_limit.get("reasons", []) if str(value))
        if reason_text:
            trust_reasons.append(reason_text)
        trust_reasons = list(dict.fromkeys(trust_reasons))

        trust_verdict = "trusted"
        if runtime_identity["pinIntegrityStatus"] in {"mismatch", "unresolved"} or state_kind in {"error", "unavailable"}:
            trust_verdict = "unsafe"
        elif trust_reasons:
            trust_verdict = "caution"

        def safety_status(condition: bool | None, *, inverted: bool = False) -> str:
            if condition is None:
                return "unavailable"
            effective = not condition if inverted else condition
            return "trusted" if effective else "unsafe"

        runtime_safety = [
            {
                "label": "Runtime identity",
                "status": "trusted"
                if runtime_identity["pinIntegrityStatus"] == "ok"
                else ("caution" if runtime_identity["pinIntegrityStatus"] == "not_pinned" else "unsafe"),
                "detail": f"selection={runtime_identity['runSelectionMode']} drift={runtime_identity['driftStatus']}",
                "evidence": ["runtimeIdentity.runSelectionMode", "runtimeIdentity.driftStatus"],
                "ts": runtime_identity["lastArtifactUpdateAt"],
            },
            {
                "label": "Data freshness",
                "status": "trusted"
                if runtime_identity["artifactFreshness"]["status"] == "fresh"
                else ("unsafe" if runtime_identity["artifactFreshness"]["status"] == "stale" else "unavailable"),
                "detail": f"age={runtime_identity['artifactFreshness']['ageSeconds']}s threshold={runtime_identity['artifactFreshness']['thresholdSeconds']}s",
                "evidence": ["runtimeIdentity.artifactFreshness"],
                "ts": runtime_identity["lastArtifactUpdateAt"],
            },
            {
                "label": "Execution gate",
                "status": "trusted"
                if bool(live_safety.get("ordering_allowed"))
                else ("caution" if "readonly" in str(live_safety.get("runtime_mode") or "") else "unsafe"),
                "detail": f"preflight_ok={live_safety.get('preflight_ok')} rollout_stage={live_safety.get('rollout_stage')}",
                "evidence": ["live_safety_summary.json"],
                "ts": _string_or_none(live_safety.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
            },
            {
                "label": "Market integrity",
                "status": "unsafe"
                if str(market_integrity.get("action") or "").lower() in {"halt", "block"}
                else ("caution" if market_integrity.get("reasons") else "trusted"),
                "detail": _payload_summary(
                    {
                        "action": market_integrity.get("action"),
                        "confidence": market_integrity.get("confidence"),
                        "score": market_integrity.get("score"),
                    }
                ),
                "evidence": ["market_integrity_journal.jsonl", "kraken_spot_replay_summary.json"],
                "ts": _string_or_none(market_integrity.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
            },
            {
                "label": "Exchange / lifecycle connectivity",
                "status": "trusted"
                if user_stream_state["status"] == "connected"
                else ("caution" if user_stream_state["status"] == "partial" else "unsafe"),
                "detail": _payload_summary(
                    {
                        "user_stream_connected": _as_object(_as_object(market_integrity.get("metadata")).get("capability_evidence")).get("user_stream_connected"),
                        "user_stream_confidence": _as_object(_as_object(market_integrity.get("metadata")).get("capability")).get("user_stream_confidence"),
                        "lifecycle_completeness": _as_object(_as_object(market_integrity.get("metadata")).get("capability")).get("lifecycle_completeness"),
                    }
                ),
                "evidence": ["market_integrity_journal.jsonl", *user_stream_state["evidence"]],
                "ts": user_stream_state["lastEventAt"] or _string_or_none(market_integrity.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
            },
            {
                "label": "Operator permission path",
                "status": "trusted"
                if bool(live_gate.get("provider_supported")) and bool(live_gate.get("provider_whitelisted"))
                else "unsafe",
                "detail": _payload_summary(
                    {
                        "provider_supported": live_gate.get("provider_supported"),
                        "provider_whitelisted": live_gate.get("provider_whitelisted"),
                        "unlock_acknowledged": live_gate.get("unlock_acknowledged"),
                    }
                ),
                "evidence": ["kraken_spot_operator_summary.json"],
                "ts": _string_or_none(_as_object(operator_summary.get("harmony")).get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
            },
            {
                "label": "User stream",
                "status": "trusted"
                if user_stream_state["status"] == "connected"
                else ("caution" if user_stream_state["status"] == "partial" else "unsafe"),
                "detail": str(user_stream_state["detail"]),
                "evidence": user_stream_state["evidence"],
                "ts": user_stream_state["lastEventAt"] or _dt_to_iso(snapshot.latest_artifact_at),
            },
            {
                "label": "Rate limit / venue pressure",
                "status": "caution"
                if venue_limit
                else "unavailable",
                "detail": _payload_summary(
                    {
                        "action": venue_limit.get("action"),
                        "size_multiplier": venue_limit.get("size_multiplier"),
                        "reduce_only_only": venue_limit.get("reduce_only_only"),
                    }
                )
                if venue_limit
                else "venue limit telemetry unavailable",
                "evidence": ["venue_limit_journal.jsonl"] if venue_limit else [],
                "ts": _string_or_none(venue_limit.get("ts")) if venue_limit else _dt_to_iso(snapshot.latest_artifact_at),
            },
        ]

        def guard_row(
            *,
            name: str,
            configured_threshold: str,
            observed_value: str,
            status: str,
            impact: str,
            evidence: list[str],
            last_triggered_at: str | None = None,
            derived: bool = False,
        ) -> dict[str, Any]:
            return {
                "name": name,
                "configuredThreshold": configured_threshold,
                "observedValue": observed_value,
                "status": status,
                "impact": impact,
                "evidence": evidence,
                "lastTriggeredAt": last_triggered_at,
                "derived": derived,
            }

        guard_matrix = [
            guard_row(
                name="Max exposure",
                configured_threshold=str(rollout_profile.get("max_exposure_notional", "unavailable")),
                observed_value=str(observed_exposure) if observed_exposure is not None else "unavailable",
                status=(
                    "block"
                    if observed_exposure is not None
                    and _optional_float(rollout_profile.get("max_exposure_notional")) is not None
                    and observed_exposure > _coerce_float(rollout_profile.get("max_exposure_notional"))
                    else ("ok" if observed_exposure is not None else "unavailable")
                ),
                impact="Blocks new entries when gross exposure exceeds rollout envelope.",
                evidence=["events_account.jsonl", "events_positions.jsonl", "live_gate.rollout_profile.max_exposure_notional"],
            ),
            guard_row(
                name="Max position notional",
                configured_threshold=str(rollout_profile.get("max_position_notional", "unavailable")),
                observed_value=str(observed_exposure) if observed_exposure is not None else "unavailable",
                status=(
                    "block"
                    if observed_exposure is not None
                    and _optional_float(rollout_profile.get("max_position_notional")) is not None
                    and observed_exposure > _coerce_float(rollout_profile.get("max_position_notional"))
                    else ("ok" if observed_exposure is not None else "unavailable")
                ),
                impact="Prevents any single live position from exceeding configured notional.",
                evidence=["events_positions.jsonl", "live_gate.rollout_profile.max_position_notional"],
            ),
            guard_row(
                name="Daily loss cap",
                configured_threshold="unavailable",
                observed_value="unavailable",
                status="unavailable",
                impact="No direct daily loss cap artifact was found for the active run.",
                evidence=["runtime artifacts missing explicit daily loss cap"],
            ),
            guard_row(
                name="Weekly loss cap",
                configured_threshold="unavailable",
                observed_value="unavailable",
                status="unavailable",
                impact="No direct weekly loss cap artifact was found for the active run.",
                evidence=["runtime artifacts missing explicit weekly loss cap"],
            ),
            guard_row(
                name="Stale market block",
                configured_threshold=f"{runtime_identity['artifactFreshness']['thresholdSeconds']}s",
                observed_value=f"{runtime_identity['artifactFreshness']['ageSeconds']}s",
                status="block" if runtime_identity["artifactFreshness"]["status"] == "stale" else "ok",
                impact="Stale artifacts make execution truth unsafe; operator should not trust live action paths.",
                evidence=["runtimeIdentity.artifactFreshness"],
            ),
            guard_row(
                name="Spread guard",
                configured_threshold=str(
                    _as_object(_as_object(operator_summary.get("harmony")).get("market_watch")).get("entry_block_max_spread_bps")
                    or rollout_profile.get("max_spread_bps")
                    or "unavailable"
                ),
                observed_value=str(spread_bps) if spread_bps is not None else "unavailable",
                status=(
                    "block"
                    if spread_bps is not None
                    and (
                        spread_bps
                        > _coerce_float(
                            _as_object(_as_object(operator_summary.get("harmony")).get("market_watch")).get("entry_block_max_spread_bps")
                            or rollout_profile.get("max_spread_bps"),
                            0.0,
                        )
                    )
                    else ("ok" if spread_bps is not None else "unavailable")
                ),
                impact="Blocks entry when spread exceeds rollout or market-watch threshold.",
                evidence=["market_integrity_journal.jsonl", "kraken_spot_operator_summary.json"],
            ),
            guard_row(
                name="Min depth guard",
                configured_threshold=str(
                    _as_object(_as_object(operator_summary.get("harmony")).get("market_watch")).get("entry_degrade_min_depth_notional")
                    or rollout_profile.get("min_depth_notional")
                    or "unavailable"
                ),
                observed_value=str(depth_notional) if depth_notional is not None else "unavailable",
                status=(
                    "block"
                    if depth_notional is not None
                    and (
                        depth_notional
                        < _coerce_float(
                            _as_object(_as_object(operator_summary.get("harmony")).get("market_watch")).get("entry_degrade_min_depth_notional")
                            or rollout_profile.get("min_depth_notional"),
                            0.0,
                        )
                    )
                    else ("ok" if depth_notional is not None else "unavailable")
                ),
                impact="Blocks or degrades entries when book depth is too thin.",
                evidence=["market_integrity_journal.jsonl", "market_watch_journal.jsonl"],
            ),
            guard_row(
                name="Execution throttle",
                configured_threshold=str(rollout_profile.get("max_orders_per_min", "unavailable")),
                observed_value="unavailable",
                status="unavailable",
                impact="Per-minute throttle observation is not emitted in the active run artifacts.",
                evidence=["live_gate.rollout_profile.max_orders_per_min"],
            ),
            guard_row(
                name="Sell floor guard",
                configured_threshold=str(_as_object(live_safety.get("capital_protection")).get("minimum_sell_net_profit_bps", "unavailable")),
                observed_value="inventory flat"
                if _coerce_float(latest_account.get("gross_exposure_notional"), 0.0) == 0.0
                else "guard active",
                status="ok"
                if _coerce_float(latest_account.get("gross_exposure_notional"), 0.0) == 0.0
                else "warn",
                impact="Reduce-only sells remain blocked below configured net profit floor.",
                evidence=["live_safety_summary.json"],
            ),
            guard_row(
                name="No-trade regime",
                configured_threshold="market_watch action must continue",
                observed_value=str(self._latest_market_watch(snapshot).get("action") or "unavailable"),
                status="block"
                if str(self._latest_market_watch(snapshot).get("action") or "").lower() in {"block_entries", "halt"}
                else ("ok" if self._latest_market_watch(snapshot) else "unavailable"),
                impact="Blocks entries when the market regime says stand down.",
                evidence=["market_watch_journal.jsonl", "kraken_spot_replay_summary.json"],
            ),
            guard_row(
                name="Flatten-only",
                configured_threshold="venue limit must not force flatten_only",
                observed_value=str(venue_limit.get("action") or "unavailable"),
                status="block"
                if str(venue_limit.get("action") or "").lower() in {"flatten_only", "halt"}
                else ("ok" if venue_limit else "unavailable"),
                impact="Restricts runtime to flatten/reduce-only actions when venue lifecycle trust is weak.",
                evidence=["venue_limit_journal.jsonl"],
                last_triggered_at=_string_or_none(venue_limit.get("ts")),
            ),
            guard_row(
                name="Readonly mode",
                configured_threshold="runtime_mode != live_readonly",
                observed_value=str(live_safety.get("runtime_mode") or self._mode(snapshot)),
                status="block" if "readonly" in str(live_safety.get("runtime_mode") or self._mode(snapshot)) else "ok",
                impact="Readonly mode disables live order submission by design.",
                evidence=["live_safety_summary.json", "kraken_spot_operator_summary.json"],
            ),
        ]

        rollback_triggered = (
            None if performance.get("rollback_trigger_report") is None else bool(rollback_trigger.get("rollback_triggered"))
        )
        recovery_mode_active = (
            None if performance.get("recovery_mode_report") is None else bool(recovery_mode_report.get("recovery_mode"))
        )
        target_implausible = (
            None
            if performance.get("performance_gap_report") is None
            else bool(performance_gap.get("theoretically_implausible_under_current_capital_envelope"))
        )
        target_gap = _optional_float(_as_object(performance_gap.get("gaps")).get("net_bps_per_trade_gap"))

        if rollback_triggered is True:
            promotion_status = "blocked_rollback_triggered"
        elif bool(promotion_gate.get("eligible")):
            promotion_status = "promotable"
        elif target_implausible is True:
            promotion_status = "blocked_target_implausible"
        elif performance.get("promotion_gate_report") is not None or performance.get("rollout_readiness_report") is not None:
            promotion_status = "evidence_collect"
        else:
            promotion_status = None

        if recovery_mode_active is None:
            recovery_mode = None
        else:
            recovery_mode = "active" if recovery_mode_active else "inactive"

        live_degradation_status = _string_or_none(live_degradation_report.get("status"))
        rollback_risk = None
        if rollback_triggered is True or live_degradation_status == "degraded":
            rollback_risk = "high"
        elif live_degradation_status in {"caution", "watch"} or recovery_mode_active:
            rollback_risk = "medium"
        elif live_degradation_status is not None:
            rollback_risk = "low"

        authority_boundary = "legacy_live_path_only"
        if "readonly" in str(live_safety.get("runtime_mode") or self._mode(snapshot)):
            authority_boundary = "readonly_no_live_orders"

        return {
            "runId": snapshot.run_id,
            "trustVerdict": trust_verdict,
            "trustReasons": trust_reasons,
            "runtimeSafety": runtime_safety,
            "appliedControl": (
                {
                    "action": _string_or_none(control_state.get("action")) or "unavailable",
                    "controlSurface": _string_or_none(control_state.get("control_surface")) or "unavailable",
                    "mode": _string_or_none(control_state.get("mode")),
                    "degradationApplied": (
                        None if control_state == {} and not control_state.get("degradation_applied") else bool(control_state.get("degradation_applied"))
                    ),
                    "forcedRiskMode": _string_or_none(control_state.get("forced_risk_mode")),
                    "sizeMultiplier": _optional_float(control_state.get("size_multiplier")),
                    "reasons": [str(value) for value in control_state.get("reasons", []) if str(value)],
                    "flattenedStatus": (
                        ",".join(str(value) for value in control_state.get("flattened", []) if str(value))
                        if isinstance(control_state.get("flattened"), list)
                        else _string_or_none(control_state.get("flattened"))
                    ),
                    "killPath": _string_or_none(control_state.get("kill_path")),
                    "steps": _optional_int(control_state.get("steps")),
                    "ts": _string_or_none(control_state.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                }
                if control_state
                else None
            ),
            "queuedCommand": (
                {
                    "action": _string_or_none(queued_command.get("action")) or "unavailable",
                    "reasonCode": _string_or_none(queued_command.get("reasonCode")) or "unavailable",
                    "reasonText": _string_or_none(queued_command.get("reasonText")),
                    "operatorId": _string_or_none(queued_command.get("operatorId")),
                    "effectiveState": _string_or_none(queued_command.get("effectiveState")) or "unavailable",
                    "auditReference": _string_or_none(queued_command.get("auditReference")),
                    "ts": _string_or_none(queued_command.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                }
                if queued_command
                else None
            ),
            "userStream": user_stream_state,
            "guardMatrix": guard_matrix,
            "performanceControl": {
                "promotionScore": _optional_float(_as_object(performance.get("promotion_score_report")).get("promotion_score")),
                "promotionStatus": promotion_status,
                "rollbackTriggered": rollback_triggered,
                "recoveryMode": recovery_mode,
                "liveDegradationStatus": live_degradation_status,
                "selfThrottlingActive": (
                    None if performance.get("self_throttling_state_report") is None else bool(self_throttling_report.get("active"))
                ),
                "privateStreamHealth": _string_or_none(private_stream_health.get("status")),
                "authorityBoundary": authority_boundary,
                "rollbackRisk": rollback_risk,
                "targetPlausibility": (
                    "implausible_under_current_capital_envelope"
                    if target_implausible is True
                    else ("not_flagged" if target_implausible is False else None)
                ),
                "targetGapNetBps": target_gap,
                "readinessStatus": (
                    "ready"
                    if bool(rollout_readiness.get("ready"))
                    else ("not_ready" if rollout_readiness else None)
                ),
            },
            "truthNotes": [
                "Pinned mode never silently falls back to latest; unresolved pin integrity is surfaced as unsafe.",
                "Guard statuses only compare direct observed values against direct configured thresholds; missing evidence stays unavailable.",
                "Applied runtime control is sourced from control_journal.jsonl; queued operator commands are sourced from rcc_control_outbox.jsonl.",
                "User-stream posture is derived only from emitted auth stream audit/events artifacts.",
                *(
                    [f"market_context_event_status={_payload_summary(_as_object(market_context.get('event_status')))}"]
                    if market_context
                    else []
                ),
                *( [reason_text] if reason_text else [] ),
            ],
            "linkedArtifacts": self._linked_artifacts(
                snapshot,
                "live_safety_summary.json",
                "readiness_summary.json",
                "health_summary.json",
                "health_journal.jsonl",
                "market_integrity_journal.jsonl",
                "market_context_summary.jsonl",
                "venue_limit_journal.jsonl",
                "control_journal.jsonl",
                "events_user_stream.jsonl",
                "user_stream_audit.jsonl",
                "kraken_spot_operator_summary.json",
            ),
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "runtimeIdentity": runtime_identity,
        }

    def execution(self) -> dict[str, Any]:
        snapshot = self._read_snapshot()
        state_kind, reason_code, reason_text = self._current_state(snapshot)
        runtime_identity = self._runtime_identity(
            snapshot,
            state_kind=state_kind,
            reason_code=reason_code,
        )
        health_summary = snapshot.health_summary or snapshot.throughput_diagnostics
        latest_account = self._latest_account_snapshot(snapshot)
        latest_position = self._latest_position_snapshot(snapshot)
        live_safety = snapshot.live_safety_summary
        venue_limit = self._latest_venue_limit(snapshot)
        lifecycle_summary = self._latest_lifecycle_summary(snapshot)
        user_stream_state = self._user_stream_state(snapshot)
        latest_reconciliation = self._latest_reconciliation_report(snapshot)
        latest_execution_plan = _latest_row(snapshot.execution_journal)
        performance = snapshot.performance_artifacts
        phase2_operator_summary = _as_object(performance.get("phase2_operator_summary"))
        phase2_execution_truth = _as_object(performance.get("phase2_execution_truth_review"))
        phase2_edge_capture = _as_object(performance.get("phase2_edge_capture_review"))
        phase2_exit_effectiveness = _as_object(performance.get("phase2_exit_effectiveness_review"))

        def normalize_order_status(raw_status: str) -> str:
            normalized = raw_status.lower().replace("_", " ").strip()
            if normalized in {"submitted", "pending"}:
                return normalized
            if normalized in {"ack", "acknowledged"}:
                return "acknowledged"
            if "partial" in normalized:
                return "partially filled"
            if "filled" in normalized:
                return "filled"
            if "cancel" in normalized:
                return "canceled"
            if "reject" in normalized:
                return "rejected"
            return normalized or "pending"

        orders_by_id: dict[str, dict[str, Any]] = {}

        def ensure_order(order_id: str) -> dict[str, Any]:
            if order_id not in orders_by_id:
                orders_by_id[order_id] = {
                    "id": order_id,
                    "symbol": "UNKNOWN",
                    "side": None,
                    "quantity": None,
                    "targetNotional": None,
                    "price": None,
                    "fees": None,
                    "slippage": None,
                    "status": "pending",
                    "venueResponseSummary": None,
                    "rejectionReason": None,
                    "decisionTs": None,
                    "submittedTs": None,
                    "acknowledgedTs": None,
                    "filledTs": None,
                    "canceledTs": None,
                    "rejectedTs": None,
                    "transitions": [],
                    "derivedFields": [],
                    "_fillLatencies": [],
                }
            return orders_by_id[order_id]

        for row in snapshot.order_events:
            payload = _as_object(row.get("payload"))
            event_type = str(row.get("event_type") or "")
            event_ts = _string_or_none(payload.get("ts")) or _string_or_none(row.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at)
            raw_idempotency = _string_or_none(row.get("idempotency_key"))
            order_id = (
                _string_or_none(payload.get("order_key"))
                or _string_or_none(payload.get("order_id"))
                or _string_or_none(payload.get("clientOrderId"))
                or (raw_idempotency.split(":", 1)[0] if raw_idempotency else None)
            )
            if not order_id:
                continue
            order = ensure_order(order_id)
            order["symbol"] = _string_or_none(payload.get("symbol")) or _string_or_none(row.get("symbol")) or order["symbol"]
            metadata = _as_object(payload.get("metadata"))
            order["side"] = _string_or_none(payload.get("side")) or _string_or_none(metadata.get("side")) or order["side"]
            order["targetNotional"] = _optional_float(payload.get("target_notional")) if payload.get("target_notional") is not None else order["targetNotional"]
            order["quantity"] = _optional_float(payload.get("quantity") or payload.get("qty")) if (payload.get("quantity") is not None or payload.get("qty") is not None) else order["quantity"]
            order["price"] = _optional_float(payload.get("price") or payload.get("limit_price")) if (payload.get("price") is not None or payload.get("limit_price") is not None) else order["price"]

            transition_label = event_type.replace("_", " ").title()
            transition_detail = _payload_summary(payload)
            if event_type == "ORDER_INTENT":
                order["decisionTs"] = event_ts
                order["status"] = "pending"
                order["venueResponseSummary"] = "order intent emitted"
                if order["quantity"] is None and order["targetNotional"] is not None:
                    order["derivedFields"].append("quantity unavailable; targetNotional retained from order intent")
            elif event_type == "ORDER_ACK":
                order["acknowledgedTs"] = event_ts
                order["status"] = "acknowledged"
                order["venueResponseSummary"] = _string_or_none(payload.get("order_id")) or "venue acknowledged"
            elif event_type == "ORDER_UPDATE":
                order["venueResponseSummary"] = _string_or_none(payload.get("clientOrderId")) or order["venueResponseSummary"]
            elif event_type == "ORDER_LIFECYCLE_TRANSITION":
                to_state = _string_or_none(payload.get("to_state")) or "pending"
                normalized_status = normalize_order_status(to_state)
                order["status"] = normalized_status
                if normalized_status == "submitted":
                    order["submittedTs"] = event_ts
                elif normalized_status == "acknowledged":
                    order["acknowledgedTs"] = event_ts
                elif normalized_status == "rejected":
                    order["rejectedTs"] = event_ts
                elif normalized_status == "filled":
                    order["filledTs"] = event_ts
                elif normalized_status == "canceled":
                    order["canceledTs"] = event_ts
                order["rejectionReason"] = _string_or_none(metadata.get("error")) or (
                    _string_or_none(payload.get("reason")) if normalized_status == "rejected" else order["rejectionReason"]
                )
                order["venueResponseSummary"] = (
                    f"{_string_or_none(payload.get('source')) or 'runtime'}:{_string_or_none(payload.get('reason')) or 'transition'}"
                )
            order["transitions"].append(
                {
                    "label": transition_label,
                    "detail": transition_detail,
                    "ts": event_ts,
                    "severity": "warn" if "reject" in transition_label.lower() else "info",
                }
            )

        for row in snapshot.fill_events:
            payload = _as_object(row.get("payload"))
            event_ts = _string_or_none(row.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at)
            order_id = _string_or_none(payload.get("order_id")) or _string_or_none(row.get("idempotency_key"))
            if not order_id:
                continue
            order = ensure_order(order_id)
            order["symbol"] = _string_or_none(payload.get("symbol")) or _string_or_none(row.get("symbol")) or order["symbol"]
            order["side"] = _string_or_none(payload.get("side")) or order["side"]
            if order["targetNotional"] is None:
                order["targetNotional"] = _optional_float(payload.get("notional"))
                if order["targetNotional"] is not None:
                    order["derivedFields"].append("targetNotional derived from fill.notional because order intent target was unavailable")
            fee = _optional_float(payload.get("fee"))
            slippage = _optional_float(payload.get("slippage_cost"))
            if fee is not None:
                order["fees"] = round((order["fees"] or 0.0) + fee, 8)
            if slippage is not None:
                order["slippage"] = round((order["slippage"] or 0.0) + slippage, 8)
            latency_ms = _optional_int(payload.get("latency_ms"))
            if latency_ms is not None:
                order["_fillLatencies"].append(latency_ms)
            fill_status = normalize_order_status(_string_or_none(payload.get("status")) or "filled")
            order["status"] = fill_status
            order["filledTs"] = event_ts
            order["transitions"].append(
                {
                    "label": "Fill",
                    "detail": _payload_summary(payload),
                    "ts": event_ts,
                    "severity": "good" if fill_status == "filled" else "info",
                }
            )

        for row in snapshot.lifecycle_evidence:
            row_type = str(row.get("type") or "").lower()
            if row_type == "summary":
                continue
            order_id = _string_or_none(row.get("order_key")) or _string_or_none(row.get("clientOrderId"))
            if not order_id:
                continue
            order = ensure_order(order_id)
            event_ts = _string_or_none(row.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at)
            order["symbol"] = _string_or_none(row.get("symbol")) or order["symbol"]
            metadata = _as_object(row.get("metadata"))
            order["side"] = _string_or_none(metadata.get("side")) or order["side"]
            next_state = normalize_order_status(_string_or_none(row.get("to_state")) or "pending")
            order["status"] = next_state
            if next_state == "submitted" and order["submittedTs"] is None:
                order["submittedTs"] = event_ts
            elif next_state == "acknowledged" and order["acknowledgedTs"] is None:
                order["acknowledgedTs"] = event_ts
            elif next_state == "rejected":
                order["rejectedTs"] = event_ts
            elif next_state == "filled":
                order["filledTs"] = event_ts
            elif next_state == "canceled":
                order["canceledTs"] = event_ts
            rejection_reason = _string_or_none(metadata.get("error")) or _string_or_none(row.get("reason"))
            if rejection_reason and next_state == "rejected":
                order["rejectionReason"] = rejection_reason
            order["venueResponseSummary"] = (
                f"{_string_or_none(row.get('source')) or 'lifecycle'}:{_string_or_none(row.get('reason')) or next_state}"
            )
            order["transitions"].append(
                {
                    "label": "Lifecycle evidence",
                    "detail": _payload_summary(
                        {
                            "from_state": row.get("from_state"),
                            "to_state": row.get("to_state"),
                            "reason": row.get("reason"),
                            "source": row.get("source"),
                        }
                    ),
                    "ts": event_ts,
                    "severity": "warn" if next_state == "rejected" else "info",
                }
            )

        orders = list(orders_by_id.values())
        for order in orders:
            order.pop("_fillLatencies", None)
            order["transitions"] = sorted(
                order["transitions"],
                key=lambda item: _safe_datetime_from_iso(item.get("ts")) or datetime.min.replace(tzinfo=UTC),
            )

        latest_trade_log = snapshot.trade_log[-1] if snapshot.trade_log else {}
        realized_pnl = _optional_float(latest_account.get("realized_pnl"))
        unrealized_pnl = _optional_float(latest_account.get("unrealized_pnl"))
        exposure_notional = _optional_float(latest_position.get("exposure_notional"))
        if exposure_notional is None:
            exposure_notional = _optional_float(latest_account.get("gross_exposure_notional"))

        positions: list[dict[str, Any]] = []
        if exposure_notional is not None and exposure_notional > 0:
            positions.append(
                {
                    "symbol": _string_or_none(latest_position.get("symbol"))
                    or _string_or_none(latest_trade_log.get("symbol"))
                    or _string_or_none(snapshot.manifest.get("symbol"))
                    or "UNKNOWN",
                    "side": _string_or_none(latest_trade_log.get("side")),
                    "quantity": _optional_float(latest_position.get("qty")),
                    "exposureNotional": exposure_notional,
                    "entryPrice": _optional_float(latest_trade_log.get("entry_price")),
                    "markPrice": _optional_float(latest_trade_log.get("mark_price")),
                    "unrealizedPnl": unrealized_pnl,
                    "realizedPnl": realized_pnl,
                    "costBasis": _optional_float(latest_trade_log.get("cost_basis")),
                    "holdDurationSec": None,
                    "exitEligibility": "reduce_only" if bool(venue_limit.get("reduce_only_only")) else (
                        "eligible" if bool(live_safety.get("ordering_allowed")) else "blocked"
                    ),
                    "sellFloorStatus": (
                        f"min_net_profit_bps={live_safety.get('capital_protection', {}).get('minimum_sell_net_profit_bps')}"
                        if live_safety.get("capital_protection")
                        else None
                    ),
                    "derivedFields": [
                        "exposureNotional derived from latest position/account snapshot"
                        if latest_position or latest_account
                        else "position telemetry unavailable"
                    ],
                    "ts": _string_or_none(latest_position.get("ts"))
                    or _string_or_none(latest_account.get("ts"))
                    or _dt_to_iso(snapshot.latest_artifact_at),
                }
            )

        account_snapshot = (
            {
                "venue": _string_or_none(latest_account.get("venue")),
                "symbol": _string_or_none(latest_account.get("symbol")) or _string_or_none(snapshot.manifest.get("symbol")),
                "baselineBalance": _optional_float(latest_account.get("baseline_balance")),
                "exchangeBalance": _optional_float(latest_account.get("exchange_balance")),
                "grossExposureNotional": _optional_float(latest_account.get("gross_exposure_notional")),
                "localCashDelta": _optional_float(latest_account.get("local_cash_delta")),
                "realizedPnl": realized_pnl,
                "unrealizedPnl": unrealized_pnl,
                "cumulativeFees": _optional_float(latest_account.get("cumulative_fees")),
                "cumulativeSlippage": _optional_float(latest_account.get("cumulative_slippage")),
                "fillCount": _optional_int(latest_account.get("fill_count")),
                "ts": _string_or_none(latest_account.get("ts")) or _dt_to_iso(snapshot.latest_artifact_at),
                "derivedFields": [
                    "Account snapshot is direct from events_account.jsonl."
                ],
            }
            if latest_account
            else None
        )

        venue_telemetry = {
            "userStreamStatus": str(user_stream_state.get("status") or "unavailable"),
            "lastUserStreamEvent": _string_or_none(user_stream_state.get("lastEventType")),
            "subscribedChannels": [str(value) for value in user_stream_state.get("subscribedChannels", []) if str(value)],
            "lifecycleStatus": str(lifecycle_summary.get("result_status") or _string_or_none(lifecycle_summary.get("to_state")) or "unavailable"),
            "lifecycleUpgradeEligible": (
                _as_object(lifecycle_summary.get("proof")).get("upgrade_eligible")
                if lifecycle_summary
                else None
            ),
            "lifecycleGapReasons": [str(value) for value in lifecycle_summary.get("gap_reasons", []) if str(value)] if lifecycle_summary else [],
            "lastLifecycleReason": _string_or_none(_as_object(lifecycle_summary.get("proof")).get("last_reason")) or _string_or_none(lifecycle_summary.get("reason")),
            "reconciliationStatus": _string_or_none(latest_reconciliation.get("code")) or _string_or_none(latest_reconciliation.get("reason")),
            "executionPlanStyle": _string_or_none(_as_object(latest_execution_plan.get("plan")).get("order_style")),
            "fillProbability": _optional_float(_as_object(latest_execution_plan.get("forecast")).get("fill_probability")),
            "ts": (
                _string_or_none(lifecycle_summary.get("ts"))
                or _string_or_none(latest_execution_plan.get("ts"))
                or user_stream_state.get("lastEventAt")
                or _dt_to_iso(snapshot.latest_artifact_at)
            ),
            "evidence": self._linked_artifacts(
                snapshot,
                "events_user_stream.jsonl",
                "user_stream_audit.jsonl",
                "lifecycle_evidence_journal.jsonl",
                "execution_journal.jsonl",
                "reconciliation_report.jsonl",
            ),
        }

        orders_submitted = _optional_float(health_summary.get("orders_submitted"))
        orders_rejected = _optional_float(health_summary.get("orders_rejected"))
        fills_count = _optional_float(health_summary.get("fills"))
        if fills_count is None and snapshot.fill_events:
            fills_count = float(len(snapshot.fill_events))
        fill_rate = (
            round((fills_count / orders_submitted) * 100.0, 2)
            if orders_submitted and fills_count is not None and orders_submitted > 0
            else None
        )
        rejection_rate = (
            round((orders_rejected / orders_submitted) * 100.0, 2)
            if orders_submitted and orders_rejected is not None and orders_submitted > 0
            else None
        )
        cancel_count = sum(1 for order in orders if order["status"] == "canceled")
        cancel_rate = (
            round((cancel_count / orders_submitted) * 100.0, 2)
            if orders_submitted and orders_submitted > 0
            else None
        )
        avg_fill_latency = None
        fill_latencies = [
            _optional_int(_as_object(row.get("payload")).get("latency_ms"))
            for row in snapshot.fill_events
        ]
        fill_latencies = [value for value in fill_latencies if value is not None]
        if fill_latencies:
            avg_fill_latency = round(sum(fill_latencies) / len(fill_latencies), 2)
        total_fees = round(sum(_coerce_float(_as_object(row.get("payload")).get("fee"), 0.0) for row in snapshot.fill_events), 8)
        total_slippage = round(sum(_coerce_float(_as_object(row.get("payload")).get("slippage_cost"), 0.0) for row in snapshot.fill_events), 8)
        phase2_edge_capture_efficiency = _optional_float(phase2_edge_capture.get("edge_capture_efficiency"))
        phase2_slippage_gap_bps = _optional_float(phase2_execution_truth.get("slippage_gap_bps"))
        phase2_delay_gap_ms = _optional_float(phase2_execution_truth.get("delay_gap_ms"))
        phase2_exit_efficiency = _optional_float(phase2_exit_effectiveness.get("exit_efficiency"))
        phase2_feedback_confidence = _optional_float(phase2_execution_truth.get("feedback_confidence"))
        phase2_feedback_sample_count = _optional_int(phase2_execution_truth.get("feedback_sample_count"))

        summary = [
            {
                "label": "Execution attempts",
                "value": _optional_float(health_summary.get("execution_attempts")),
                "unit": "count",
                "detail": "Direct from health_summary.execution_attempts when emitted.",
                "derived": False,
            },
            {
                "label": "Orders submitted",
                "value": orders_submitted,
                "unit": "count",
                "detail": "Direct from health summary or throughput diagnostics.",
                "derived": False,
            },
            {
                "label": "Fill rate",
                "value": fill_rate,
                "unit": "percent",
                "detail": "Derived as fills / orders_submitted * 100 when denominator exists.",
                "derived": True,
            },
            {
                "label": "Rejection rate",
                "value": rejection_rate,
                "unit": "percent",
                "detail": "Derived as orders_rejected / orders_submitted * 100 when denominator exists.",
                "derived": True,
            },
            {
                "label": "Order-to-fill latency",
                "value": avg_fill_latency,
                "unit": "ms",
                "detail": "Derived from fill payload latency_ms samples.",
                "derived": True,
            },
            {
                "label": "Cancel rate",
                "value": cancel_rate,
                "unit": "percent",
                "detail": "Derived from observed order lifecycle transitions only.",
                "derived": True,
            },
            {
                "label": "Fee leakage",
                "value": total_fees if snapshot.fill_events else None,
                "unit": "quote",
                "detail": "Sum of direct fill fee fields when fill telemetry exists.",
                "derived": True,
            },
            {
                "label": "Slippage cost",
                "value": total_slippage if snapshot.fill_events else None,
                "unit": "quote",
                "detail": "Sum of direct fill slippage_cost fields when emitted.",
                "derived": True,
            },
            {
                "label": "Edge capture efficiency",
                "value": phase2_edge_capture_efficiency,
                "unit": "percent",
                "detail": (
                    "Direct from phase2_edge_capture_review.json when forecast-vs-realized edge truth exists."
                    if phase2_edge_capture
                    else "Unavailable without direct fill-to-expected-edge attribution in the active run."
                ),
                "derived": bool(phase2_edge_capture),
            },
            {
                "label": "Slippage gap vs forecast",
                "value": phase2_slippage_gap_bps,
                "unit": "bps",
                "detail": (
                    "Positive values mean realized slippage was worse than forecast."
                    if phase2_execution_truth
                    else "Unavailable without realized execution calibration evidence."
                ),
                "derived": bool(phase2_execution_truth),
            },
            {
                "label": "Fill delay gap vs forecast",
                "value": phase2_delay_gap_ms,
                "unit": "ms",
                "detail": (
                    "Positive values mean realized fill delay exceeded forecast."
                    if phase2_execution_truth
                    else "Unavailable without realized execution calibration evidence."
                ),
                "derived": bool(phase2_execution_truth),
            },
            {
                "label": "Exit efficiency",
                "value": phase2_exit_efficiency,
                "unit": "ratio",
                "detail": (
                    "Direct from phase2_exit_effectiveness_review.json when realized exit truth exists."
                    if phase2_exit_effectiveness
                    else "Unavailable without realized exit attribution."
                ),
                "derived": bool(phase2_exit_effectiveness),
            },
        ]

        timeline: list[dict[str, Any]] = []
        for order in orders:
            for transition in order["transitions"][-6:]:
                timeline.append(
                    {
                        **transition,
                        "detail": f"{order['symbol']} {transition['detail']}",
                    }
                )
        timeline = sorted(
            timeline,
            key=lambda item: _safe_datetime_from_iso(item.get("ts")) or datetime.min.replace(tzinfo=UTC),
        )[-12:]

        data_notes = [
            "Orders surface only uses direct order/fill lifecycle artifacts. Missing OMS fields remain unavailable.",
            "Position rows are emitted only when current exposure is observable from account or position snapshots.",
            "Venue telemetry uses direct auth-stream, lifecycle-evidence, execution-journal, and reconciliation artifacts only.",
            *( [reason_text] if reason_text else [] ),
        ]
        if not snapshot.order_events:
            data_notes.append("No events_orders.jsonl artifact present for the active run.")
        if not snapshot.fill_events:
            data_notes.append("No events_fills.jsonl artifact present for the active run.")
        if not snapshot.user_stream_audit and not snapshot.user_stream_events:
            data_notes.append("No authenticated user-stream audit artifacts are present for the active run.")
        if not snapshot.lifecycle_evidence:
            data_notes.append("No lifecycle_evidence_journal.jsonl artifact present for the active run.")
        if not phase2_execution_truth:
            data_notes.append("No phase2_execution_truth_review.json artifact present for the active run.")
        if not phase2_edge_capture:
            data_notes.append("No phase2_edge_capture_review.json artifact present for the active run.")
        if not phase2_exit_effectiveness:
            data_notes.append("No phase2_exit_effectiveness_review.json artifact present for the active run.")

        return {
            "runId": snapshot.run_id,
            "summary": summary,
            "orders": orders,
            "positions": positions,
            "accountSnapshot": account_snapshot,
            "venueTelemetry": venue_telemetry,
            "timeline": timeline,
            "dataNotes": data_notes,
            "phase2Review": {
                "operatorSummary": phase2_operator_summary,
                "executionTruth": phase2_execution_truth,
                "edgeTruth": phase2_edge_capture,
                "exitTruth": phase2_exit_effectiveness,
                "calibration": {
                    "feedbackConfidence": phase2_feedback_confidence,
                    "sampleCount": phase2_feedback_sample_count,
                    "partial": bool(
                        phase2_execution_truth.get("partial", True)
                        if phase2_execution_truth
                        else True
                    ),
                },
                "linkedArtifacts": self._linked_artifacts(
                    snapshot,
                    "phase2_operator_summary.json",
                    "phase2_execution_truth_review.json",
                    "phase2_edge_capture_review.json",
                    "phase2_exit_effectiveness_review.json",
                ),
            },
            "linkedArtifacts": self._linked_artifacts(
                snapshot,
                "events_orders.jsonl",
                "events_fills.jsonl",
                "events_account.jsonl",
                "events_positions.jsonl",
                "events_user_stream.jsonl",
                "user_stream_audit.jsonl",
                "lifecycle_evidence_journal.jsonl",
                "execution_journal.jsonl",
                "health_summary.json",
                "execution_simulation_journal.jsonl",
                "trade_log.json",
                "reconciliation_report.jsonl",
                "phase2_operator_summary.json",
                "phase2_execution_truth_review.json",
                "phase2_edge_capture_review.json",
                "phase2_exit_effectiveness_review.json",
            ),
            "alphaTelemetry": {
                "privateStreamHealth": _as_object(performance.get("private_stream_health")),
                "orderRejectTaxonomy": performance.get("order_reject_taxonomy", {}),
                "makerFirstEffectiveness": _as_object(performance.get("maker_first_effectiveness")),
                "executionQualityBucket": _as_object(performance.get("execution_quality_bucket_report")),
                "entryTimingOptimizer": _as_object(performance.get("entry_timing_optimizer_report")),
                "adaptiveCadence": _as_object(performance.get("adaptive_cadence_report")),
                "liveDegradation": _as_object(performance.get("live_degradation_detector_report")),
                "selfThrottling": _as_object(performance.get("self_throttling_state_report")),
            },
            "stateKind": state_kind,
            "lastUpdatedAt": _dt_to_iso(snapshot.latest_artifact_at),
            "runtimeIdentity": runtime_identity,
        }

    def _parse_operator_header(self, authorization_header: str | None) -> tuple[str, str]:
        if not authorization_header:
            raise RuntimeApiError("operator_identity_required")
        prefix = "Operator "
        if not authorization_header.startswith(prefix):
            raise RuntimeApiError("operator_identity_required")
        payload = authorization_header[len(prefix) :].strip()
        if ":" not in payload:
            raise RuntimeApiError("operator_identity_required")
        operator_id, session_id = payload.split(":", 1)
        operator_id = operator_id.strip()
        session_id = session_id.strip()
        if not operator_id or not session_id:
            raise RuntimeApiError("operator_identity_required")
        return operator_id, session_id

    def control(
        self,
        action: str,
        payload: dict[str, Any],
        authorization_header: str | None,
    ) -> dict[str, Any]:
        operator_id, session_id = self._parse_operator_header(authorization_header)
        now = _dt_to_iso(self._now())
        accepted_actions = {"pause", "resume", "freeze", "flatten"}
        if action not in accepted_actions:
            raise RuntimeApiError(f"unsupported_control_action:{action}")
        record = {
            "ts": now,
            "action": action,
            "reasonCode": str(payload.get("reasonCode") or f"operator_{action}"),
            "reasonText": str(payload.get("reasonText") or "manual operator action"),
            "operatorId": operator_id,
            "sessionId": session_id,
            "auditReference": _hash_id(action, operator_id, session_id, now),
            "status": "queued",
            "effectiveState": "awaiting_runtime_ack",
        }
        with self._write_lock:
            path = self._control_outbox_path()
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        return {
            "accepted": True,
            "rejected": False,
            "status": record["status"],
            "reasonCode": record["reasonCode"],
            "operatorMessage": f"{action} queued for runtime bridge acknowledgement.",
            "auditReference": record["auditReference"],
            "effectiveState": record["effectiveState"],
            "operatorId": operator_id,
            "ts": now,
        }

    def write_incident_note(
        self,
        payload: dict[str, Any],
        authorization_header: str | None,
    ) -> dict[str, Any]:
        operator_id, session_id = self._parse_operator_header(authorization_header)
        now = _dt_to_iso(self._now())
        note = {
            "ts": now,
            "runId": str(payload.get("runId") or self._run_dir().resolve().name),
            "operatorId": operator_id,
            "sessionId": session_id,
            "note": str(payload.get("note") or ""),
            "severity": str(payload.get("severity") or "SEV-3"),
            "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
        }
        note["noteId"] = _hash_id(note["runId"], operator_id, note["note"], now)
        with self._write_lock:
            path = self._incident_notes_path()
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(note, sort_keys=True) + "\n")
        return {
            "accepted": True,
            "noteId": note["noteId"],
            "auditReference": _hash_id("incident", note["noteId"], now),
            "operatorMessage": "Incident note appended to runtime audit trail.",
            "ts": now,
        }
