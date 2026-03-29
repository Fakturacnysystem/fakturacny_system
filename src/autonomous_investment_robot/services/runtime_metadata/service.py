from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomous_investment_robot.services.execution.constraints import VenueConstraintsNormalizer


class RuntimeMetadataService:
    def __init__(self, settings: Any, *, repo_root: str | Path | None = None) -> None:
        self.settings = settings
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), *args],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception:
            return ""
        return result.stdout.strip()

    def git_metadata(self) -> dict[str, Any]:
        status = self._git("status", "--short")
        return {
            "branch": self._git("branch", "--show-current"),
            "head": self._git("rev-parse", "HEAD"),
            "dirty": bool(status),
            "status_short": status.splitlines(),
        }

    def runtime_surface(self) -> dict[str, Any]:
        path = self.repo_root / "ops" / "runtime_surface.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def effective_min_order_quote(self) -> dict[str, Any]:
        symbol = self.settings.universe[0] if getattr(self.settings, "universe", []) else "UNKNOWN"
        provider_id = str(self.settings.execution.provider_id)
        constraints = VenueConstraintsNormalizer().for_provider(provider_id, symbol)
        raw_user_floor = os.getenv("AUTONOMOUS_MIN_ORDER_QUOTE", "").strip()
        try:
            user_floor = float(raw_user_floor) if raw_user_floor else 0.0
        except Exception:
            user_floor = 0.0
        exchange_min = float(constraints.min_notional)
        legacy_min = float(constraints.min_notional)
        effective = max(exchange_min, legacy_min, user_floor, 0.0)
        return {
            "provider_id": provider_id,
            "symbol": symbol,
            "exchange_min_order_quote": exchange_min,
            "legacy_min_order_quote": legacy_min,
            "user_min_order_quote": user_floor,
            "user_min_order_quote_source": "env:AUTONOMOUS_MIN_ORDER_QUOTE" if raw_user_floor else "not_configured",
            "effective_min_order_quote": effective,
        }

    def config_truth_report(self, *, harmony_payload: dict[str, Any]) -> dict[str, Any]:
        gate = self.settings.live_gate_status()
        conflicts: list[str] = []
        warnings: list[str] = []
        if gate["unlock_sources"]["legacy_top_level_enable_live_trading"] and gate["unlock_sources"]["env_enable_live_trading"]:
            warnings.append("dual_live_unlock_sources_present")
        if gate["unlock_sources"]["legacy_top_level_ack_i_understand_risks"] and gate["unlock_sources"]["env_ack_i_understand_risks"]:
            warnings.append("dual_live_ack_sources_present")
        if gate["full_live_stage_sources"]["env_allow_full_live_stage"] and self.settings.rollout_stage().value != "normal_live":
            warnings.append("full_live_stage_env_set_outside_normal_live")
        if not gate["doctrine_launch_safe"]:
            conflicts.append("doctrine_launch_safe=false")
        effective_min = self.effective_min_order_quote()
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "config_hash": self.settings.config_hash(),
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "provider_id": self.settings.execution.provider_id,
            "doctrine_target_provider": self.settings.doctrine_target_provider(),
            "doctrine_product_target": self.settings.doctrine_product_target(),
            "doctrine_minimum_sell_net_profit_bps": float(self.settings.doctrine.minimum_sell_net_profit_bps),
            "live_gate_status": gate,
            "rollout_profile": self.settings.rollout_profile(),
            "effective_min_order_quote": effective_min,
            "conflicts": conflicts,
            "warnings": warnings,
            "harmony_config_hash": harmony_payload.get("config_hash"),
        }

    def release_manifest(self) -> dict[str, Any]:
        git_meta = self.git_metadata()
        runtime_surface = self.runtime_surface()
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "repo_root": str(self.repo_root),
            "git": git_meta,
            "runtime_surface_schema_version": runtime_surface.get("schema_version"),
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "provider_id": self.settings.execution.provider_id,
            "config_hash": self.settings.config_hash(),
            "python": {
                "executable": sys.executable,
                "version": sys.version.split()[0],
            },
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
        }
        payload["release_fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return payload

    def deployment_stamp(self) -> dict[str, Any]:
        release = self.release_manifest()
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "release_fingerprint": release["release_fingerprint"],
            "git_head": release["git"]["head"],
            "git_branch": release["git"]["branch"],
            "config_hash": release["config_hash"],
            "runtime_mode": release["runtime_mode"],
            "rollout_stage": release["rollout_stage"],
        }

    def runtime_fingerprint(self) -> dict[str, Any]:
        release = self.release_manifest()
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "release_fingerprint": release["release_fingerprint"],
            "config_hash": self.settings.config_hash(),
            "run_dir": self.settings.storage.run_dir,
            "provider_id": self.settings.execution.provider_id,
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "universe": list(self.settings.universe),
        }
        payload["runtime_fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return payload

    def live_safety_summary(
        self,
        *,
        preflight_ok: bool,
        preflight_reason: str,
        ordering_allowed: bool,
        confidence: str,
        recovery_action: str,
    ) -> dict[str, Any]:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider_id": self.settings.execution.provider_id,
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "safety_ready": bool(
                preflight_ok
                and ordering_allowed
                and confidence not in {"insufficient", "degraded"}
                and recovery_action == "continue"
            ),
            "preflight_ok": preflight_ok,
            "preflight_reason": preflight_reason,
            "ordering_allowed": ordering_allowed,
            "restart_state_confidence": confidence,
            "recovery_action": recovery_action,
            "capital_protection": {
                "cost_basis_sell_block": bool(self.settings.doctrine.enforce_cost_basis_sell_block),
                "net_profit_sell_block": bool(self.settings.doctrine.enforce_net_profit_sell_block),
                "block_non_reduce_only_sells": bool(self.settings.doctrine.block_non_reduce_only_sells),
                "minimum_sell_net_profit_bps": float(self.settings.doctrine.minimum_sell_net_profit_bps),
            },
        }

    def health_summary(
        self,
        *,
        preflight_ok: bool,
        ordering_allowed: bool,
        throughput: dict[str, Any],
        failure_taxonomy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "runtime_mode": self.settings.execution_mode_enum().value,
            "rollout_stage": self.settings.rollout_stage().value,
            "ordering_allowed": ordering_allowed,
            "preflight_ok": preflight_ok,
            "execution_attempts": int(throughput.get("execution_attempts", 0) or 0),
            "orders_submitted": int(throughput.get("orders_submitted", 0) or 0),
            "orders_rejected": int(throughput.get("orders_rejected", 0) or 0),
            "fills": int(throughput.get("fills", 0) or 0),
            "submission_efficiency": float(throughput.get("submission_efficiency", 0.0) or 0.0),
            "fill_efficiency": float(throughput.get("fill_efficiency", 0.0) or 0.0),
            "failure_taxonomy": failure_taxonomy,
        }
