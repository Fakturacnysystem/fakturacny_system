from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HarmonyConfigResolver:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def _first_env_float(self, *names: str) -> tuple[float | None, str | None]:
        for name in names:
            raw = os.getenv(name)
            if raw is None or raw == "":
                continue
            try:
                value = float(raw)
            except Exception:
                continue
            if value > 0.0:
                return value, name
        return None, None

    def resolve(self) -> dict[str, Any]:
        cadence_s, cadence_source = self._first_env_float(
            "AUTONOMOUS_ORDER_CADENCE_S",
            "AUTONOMOUS_LIVE_POLL_SECONDS",
            "AUTONOMOUS_POLL_SECONDS",
            "AUTONOMOUS_ORDER_COOLDOWN_S",
        )
        if cadence_s is None:
            cadence_s = max(1.0, float(getattr(self.settings.harmony, "default_order_cadence_s", 5.0) or 5.0))
            cadence_source = "settings.harmony.default_order_cadence_s"
        provider_id = str(self.settings.execution.provider_id)
        doctrine_provider = str(getattr(self.settings.doctrine, "target_provider", "") or provider_id)
        doctrine_product = str(getattr(self.settings.doctrine, "product_target", "") or ("spot" if provider_id.endswith("_spot") else "perps"))
        report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "rollout_profile": self.settings.rollout_profile(),
            "provider_target": provider_id,
            "product_target": doctrine_product,
            "doctrine_target_provider": doctrine_provider,
            "doctrine": {
                "kraken_spot_only": doctrine_provider == "kraken_spot",
                "long_only": bool(getattr(self.settings.doctrine, "long_only", False)),
                "never_open_new_short_exposure": bool(getattr(self.settings.doctrine, "never_open_new_short_exposure", False)),
                "cost_basis_sell_block": bool(getattr(self.settings.doctrine, "enforce_cost_basis_sell_block", False)),
                "net_profit_sell_block": bool(getattr(self.settings.doctrine, "enforce_net_profit_sell_block", False)),
                "minimum_sell_net_profit_bps": float(getattr(self.settings.doctrine, "minimum_sell_net_profit_bps", 120.0) or 120.0),
                "block_non_reduce_only_sells": bool(getattr(self.settings.doctrine, "block_non_reduce_only_sells", False)),
            },
            "order_cadence_s": cadence_s,
            "order_cadence_source": cadence_source,
            "live_gate_status": self.settings.live_gate_status(),
            "live_activation": {
                "canary_mode": bool(getattr(self.settings, "canary_mode", False)),
                "full_live_stage_enabled": bool(getattr(self.settings, "full_live_stage_enabled", lambda: False)()),
                "event_feed_configured": bool(getattr(self.settings, "kraken_spot_event_feed_path", lambda: "")()),
                "event_feed_path": str(getattr(self.settings, "kraken_spot_event_feed_path", lambda: "")()),
            },
            "risk_mode_default": "defensive" if bool(self.settings.safe_mode_default) else "normal",
            "market_watch": {
                "enabled": bool(getattr(self.settings.market_watch, "enabled", False)),
                "blackout_windows": list(getattr(self.settings.market_watch, "blackout_windows", [])),
                "entry_block_max_spread_bps": float(getattr(self.settings.market_watch, "entry_block_max_spread_bps", 0.0) or 0.0),
                "entry_degrade_max_spread_bps": float(getattr(self.settings.market_watch, "entry_degrade_max_spread_bps", 0.0) or 0.0),
                "entry_block_min_depth_notional": float(getattr(self.settings.market_watch, "entry_block_min_depth_notional", 0.0) or 0.0),
                "entry_degrade_min_depth_notional": float(getattr(self.settings.market_watch, "entry_degrade_min_depth_notional", 0.0) or 0.0),
                "liquidity_map_min_depth_notional": float(getattr(self.settings.market_watch, "liquidity_map_min_depth_notional", 0.0) or 0.0),
                "block_new_entries_on_blackout": bool(getattr(self.settings.market_watch, "block_new_entries_on_blackout", False)),
            },
            "universe": list(self.settings.universe),
            "performance_targets": {
                "monthly_return_pct": float(getattr(self.settings.performance_targets, "monthly_return_pct", 0.0) or 0.0),
                "max_monthly_drawdown_pct": float(getattr(self.settings.performance_targets, "max_monthly_drawdown_pct", 0.0) or 0.0),
                "max_intraday_drawdown_pct": float(getattr(self.settings.performance_targets, "max_intraday_drawdown_pct", 0.0) or 0.0),
                "round_trips_per_day": float(getattr(self.settings.performance_targets, "round_trips_per_day", 0.0) or 0.0),
                "capital_utilization_pct": float(getattr(self.settings.performance_targets, "capital_utilization_pct", 0.0) or 0.0),
                "net_bps_per_trade": float(getattr(self.settings.performance_targets, "net_bps_per_trade", 0.0) or 0.0),
                "expectancy_bps_floor": float(getattr(self.settings.performance_targets, "expectancy_bps_floor", 0.0) or 0.0),
                "fill_rate": float(getattr(self.settings.performance_targets, "fill_rate", 0.0) or 0.0),
                "maker_ratio": float(getattr(self.settings.performance_targets, "maker_ratio", 0.0) or 0.0),
                "max_inventory_age_minutes": float(getattr(self.settings.performance_targets, "max_inventory_age_minutes", 0.0) or 0.0),
            },
            "capital_envelope": {
                "max_pair_exposure_notional": float(getattr(self.settings.capital_envelope, "max_pair_exposure_notional", 0.0) or 0.0),
                "reserve_fraction": float(getattr(self.settings.capital_envelope, "reserve_fraction", 0.0) or 0.0),
                "max_portfolio_heat": float(getattr(self.settings.capital_envelope, "max_portfolio_heat", 0.0) or 0.0),
                "max_regime_heat": float(getattr(self.settings.capital_envelope, "max_regime_heat", 0.0) or 0.0),
                "max_playbook_heat": float(getattr(self.settings.capital_envelope, "max_playbook_heat", 0.0) or 0.0),
                "idle_capital_alert_threshold": float(getattr(self.settings.capital_envelope, "idle_capital_alert_threshold", 0.0) or 0.0),
                "target_capital_utilization_min": float(getattr(self.settings.capital_envelope, "target_capital_utilization_min", 0.0) or 0.0),
                "max_capital_lock_time_min": float(getattr(self.settings.capital_envelope, "max_capital_lock_time_min", 0.0) or 0.0),
                "capital_efficiency_min_score": float(getattr(self.settings.capital_envelope, "capital_efficiency_min_score", 0.0) or 0.0),
            },
            "market_universe": {
                "pair_universe": list(getattr(self.settings.market_universe, "pair_universe", []) or []),
                "max_active_pairs": int(getattr(self.settings.market_universe, "max_active_pairs", 1) or 1),
                "pair_rotation_interval_s": int(getattr(self.settings.market_universe, "pair_rotation_interval_s", 0) or 0),
                "pair_min_depth_notional": float(getattr(self.settings.market_universe, "pair_min_depth_notional", 0.0) or 0.0),
                "pair_max_spread_bps": float(getattr(self.settings.market_universe, "pair_max_spread_bps", 0.0) or 0.0),
                "pair_min_expectancy_bps": float(getattr(self.settings.market_universe, "pair_min_expectancy_bps", 0.0) or 0.0),
                "pair_min_fill_rate": float(getattr(self.settings.market_universe, "pair_min_fill_rate", 0.0) or 0.0),
                "pair_clustering_enabled": bool(getattr(self.settings.market_universe, "pair_clustering_enabled", False)),
                "pair_admission_lookback_trades": int(getattr(self.settings.market_universe, "pair_admission_lookback_trades", 0) or 0),
                "pair_expulsion_expectancy_floor_bps": float(getattr(self.settings.market_universe, "pair_expulsion_expectancy_floor_bps", 0.0) or 0.0),
            },
            "playbooks": asdict(getattr(self.settings, "playbooks")),
            "expectancy": asdict(getattr(self.settings, "expectancy")),
            "experiments": asdict(getattr(self.settings, "experiments")),
            "operator_kpis": asdict(getattr(self.settings, "operator_kpis")),
            "config_hash": self.settings.config_hash(),
            "config_manifest": self.settings.config_manifest(),
        }
        return report

    def write_reports(self, run_dir: str) -> dict[str, str]:
        payload = self.resolve()
        base = Path(run_dir)
        base.mkdir(parents=True, exist_ok=True)
        harmony_report = base / "harmony_report.json"
        harmony_boot_report = base / "harmony_boot_report.json"
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        harmony_report.write_text(serialized + "\n", encoding="utf-8")
        harmony_boot_report.write_text(serialized + "\n", encoding="utf-8")
        return {
            "harmony_report": str(harmony_report),
            "harmony_boot_report": str(harmony_boot_report),
        }
