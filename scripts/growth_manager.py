#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import smtplib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _parse_export_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or not line.startswith("export "):
            continue
        body = line[len("export ") :]
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        k = key.strip()
        if not k:
            continue
        out[k] = value.strip().strip("'").strip('"')
    return out


def _apply_process_overrides(repo_root: Path) -> None:
    control_run_dir = repo_root / os.getenv("AUTONOMOUS_CONTROL_RUN_DIR", "runs/kraken_spot_live")
    merged: dict[str, str] = {}
    merged.update(_parse_export_file(control_run_dir / "env_overrides.sh"))
    merged.update(_parse_export_file(control_run_dir / "operator_overrides.sh"))
    for k, v in merged.items():
        os.environ[k] = v


@dataclass
class MetricsSample:
    ts: float
    intents_total: float
    attempted_total: float
    rejected_total: float
    fills_total: float


class GrowthManager:
    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        _apply_process_overrides(self.repo_root)
        self.run_dir = self.repo_root / os.getenv("AUTONOMOUS_GROWTH_RUN_DIR", "runs/live")
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.live_config = self.repo_root / os.getenv("AUTONOMOUS_LIVE_CONFIG", "config.kraken_spot.live_growth.yaml")
        self.audit_log = self.repo_root / os.getenv("AUTONOMOUS_GROWTH_AUDIT_LOG", "runs/kraken_spot_live/audit.log")
        self.dashboard_snapshot = self.repo_root / os.getenv("AUTONOMOUS_GROWTH_DASHBOARD_SNAPSHOT", "runs/kraken_spot_live/dashboard_snapshot.json")

        self.live_out = self.run_dir / "kraken_growth.out"
        self.manager_log = self.run_dir / "kraken_growth_manager.log"
        self.snapshot_jsonl = self.run_dir / "growth_5m_snapshots.jsonl"
        self.snapshot_latest = self.run_dir / "growth_latest_snapshot.json"

        self.lock_dir = self.run_dir / "kraken_growth_manager.lock"
        self.pid_file = self.lock_dir / "manager.pid"

        self.health_interval_s = max(2.0, _env_float("AUTONOMOUS_HEALTHCHECK_INTERVAL_S", 10.0))
        self.snapshot_interval_s = max(30.0, _env_float("AUTONOMOUS_SNAPSHOT_INTERVAL_S", 300.0))
        self.max_runtime_s = max(60.0, _env_float("AUTONOMOUS_MANAGER_MAX_RUNTIME_S", 86400.0))

        self.max_daily_loss_pct = max(0.1, _env_float("AUTONOMOUS_MAX_DAILY_LOSS_PCT", 3.0))
        self.max_drawdown_pct = max(0.1, _env_float("AUTONOMOUS_MAX_DRAWDOWN_PCT", 8.0))

        self.quality_window_s = max(60.0, _env_float("AUTONOMOUS_QUALITY_WINDOW_S", 600.0))
        self.quality_trigger_ratio = max(0.1, min(1.0, _env_float("AUTONOMOUS_QUALITY_REJECT_RATIO_TRIGGER", 0.8)))
        self.quality_min_attempts = max(1, _env_int("AUTONOMOUS_QUALITY_MIN_ATTEMPTS", 8))
        self.quality_edge_step_bps = max(0.05, _env_float("AUTONOMOUS_QUALITY_EDGE_STEP_BPS", 0.2))
        self.quality_orders_step = max(1, _env_int("AUTONOMOUS_QUALITY_ORDERS_STEP", 2))
        self.quality_min_orders_floor = max(1, _env_int("AUTONOMOUS_QUALITY_MIN_ORDERS_FLOOR", 3))
        self.quality_max_edge_cap = max(0.2, _env_float("AUTONOMOUS_QUALITY_MAX_EDGE_CAP_BPS", 2.5))
        self.quality_adjust_cooldown_s = max(30.0, _env_float("AUTONOMOUS_QUALITY_ADJUST_COOLDOWN_S", 300.0))

        self.no_fill_window_s = max(300.0, _env_float("AUTONOMOUS_NO_FILL_WINDOW_S", 7200.0))
        self.no_fill_pause_s = max(60.0, _env_float("AUTONOMOUS_NO_FILL_PAUSE_S", 1800.0))
        self.no_fill_action_cooldown_s = max(60.0, _env_float("AUTONOMOUS_NO_FILL_ACTION_COOLDOWN_S", 600.0))
        self.no_fill_min_intents = max(1.0, _env_float("AUTONOMOUS_NO_FILL_MIN_INTENTS", 20.0))

        self.fallback_consecutive_rejects = max(1, _env_int("AUTONOMOUS_FALLBACK_CONSECUTIVE_REJECTS", 3))
        self.fallback_cooldown_s = max(10.0, _env_float("AUTONOMOUS_FALLBACK_COOLDOWN_S", 90.0))

        self.rate_limit_window_s = max(60.0, _env_float("AUTONOMOUS_RATE_LIMIT_WINDOW_S", 600.0))
        self.rate_limit_storm_threshold = max(1, _env_int("AUTONOMOUS_RATE_LIMIT_STORM_THRESHOLD", 12))
        self.rate_limit_cooldown_normal_s = max(0.25, _env_float("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", 5.0))
        self.rate_limit_cooldown_storm_s = max(self.rate_limit_cooldown_normal_s, _env_float("AUTONOMOUS_RATE_LIMIT_COOLDOWN_STORM_S", 9.0))
        self.rate_limit_relax_after_s = max(60.0, _env_float("AUTONOMOUS_RATE_LIMIT_RELAX_AFTER_S", 900.0))
        self.rate_limit_adjust_cooldown_s = max(30.0, _env_float("AUTONOMOUS_RATE_LIMIT_ADJUST_COOLDOWN_S", 120.0))

        self.current_min_net_edge_bps = max(0.1, _env_float("AUTONOMOUS_MIN_NET_EDGE_BPS", 1.1))
        self.current_max_orders_per_min = max(1, _env_int("AUTONOMOUS_MAX_ORDERS_PER_MIN", 8))
        # Never allow quality cap to start below the current edge floor.
        self.quality_max_edge_cap = max(self.quality_max_edge_cap, self.current_min_net_edge_bps)
        self.current_rate_limit_cooldown_s = self.rate_limit_cooldown_normal_s
        self.canary_enabled = _env_bool("AUTONOMOUS_CANARY_AUTOPILOT", True)
        canary_fraction_cap = max(0.1, min(1.0, _env_float("AUTONOMOUS_CANARY_FRACTION_CAP", 1.0)))
        self.canary_fraction = min(canary_fraction_cap, max(0.1, _env_float("AUTONOMOUS_CANARY_FRACTION", 0.2)))
        self.promoted_fraction = max(self.canary_fraction, min(1.0, _env_float("AUTONOMOUS_PROMOTED_FRACTION", 1.0)))
        self.current_sizing_fraction = self.canary_fraction if self.canary_enabled else self.promoted_fraction
        self.canary_stage = "canary" if self.canary_enabled else "promoted"
        self.canary_eval_cooldown_s = max(30.0, _env_float("AUTONOMOUS_CANARY_EVAL_COOLDOWN_S", 300.0))
        self.canary_promote_min_submitted = max(1.0, _env_float("AUTONOMOUS_CANARY_PROMOTE_MIN_SUBMITTED", 10.0))
        self.canary_promote_max_reject_rate = max(0.0, min(1.0, _env_float("AUTONOMOUS_CANARY_PROMOTE_MAX_REJECT_RATE", 0.6)))
        self.canary_promote_max_cost_to_alpha = max(0.1, _env_float("AUTONOMOUS_CANARY_PROMOTE_MAX_COST_TO_ALPHA", 1.2))
        self.canary_promote_min_net_pnl = _env_float("AUTONOMOUS_CANARY_PROMOTE_MIN_NET_PNL_AFTER_FEES", 0.0)
        self.canary_rollback_divergence_bps = max(0.0, _env_float("AUTONOMOUS_CANARY_ROLLBACK_DIVERGENCE_BPS", 12.0))
        self.canary_rollback_net_pnl = _env_float("AUTONOMOUS_CANARY_ROLLBACK_NET_PNL_AFTER_FEES", -0.75)

        self.alert_webhook_url = os.getenv("AUTONOMOUS_ALERT_WEBHOOK_URL", "").strip()
        self.discord_webhook_url = os.getenv("AUTONOMOUS_DISCORD_WEBHOOK_URL", "").strip()
        self.telegram_token = os.getenv("AUTONOMOUS_TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("AUTONOMOUS_TELEGRAM_CHAT_ID", "").strip()
        self.smtp_host = os.getenv("AUTONOMOUS_SMTP_HOST", "").strip()
        self.smtp_port = _env_int("AUTONOMOUS_SMTP_PORT", 587)
        self.smtp_user = os.getenv("AUTONOMOUS_SMTP_USER", "").strip()
        self.smtp_pass = os.getenv("AUTONOMOUS_SMTP_PASS", "").strip()
        self.smtp_from = os.getenv("AUTONOMOUS_SMTP_FROM", "").strip()
        self.smtp_to = os.getenv("AUTONOMOUS_SMTP_TO", "").strip()

        self.start_ts = time.time()
        self.stop_ts = self.start_ts + self.max_runtime_s

        self.samples: deque[MetricsSample] = deque(maxlen=5000)
        self.exec_events: deque[tuple[float, str, str, str]] = deque(maxlen=40000)
        self.rate_limit_events: deque[float] = deque(maxlen=40000)
        start_from_beginning = str(os.getenv("AUTONOMOUS_MANAGER_AUDIT_FROM_START", "false") or "false").strip().lower() in {"1", "true", "yes", "on"}
        if start_from_beginning:
            self.audit_offset = 0
        elif self.audit_log.exists():
            self.audit_offset = self.audit_log.stat().st_size
        else:
            self.audit_offset = 0

        self.live_child: subprocess.Popen[str] | None = None
        self.live_out_handle = None
        self.running = True
        self.shutdown_reason = ""

        self.latest_dashboard: dict[str, Any] = {}
        self.latest_equity: float = 1.0
        self.start_equity: float | None = None

        self.paused_until_ts = 0.0
        self.last_snapshot_ts = 0.0
        self.last_switch_ts = 0.0
        self.last_quality_adjust_ts = 0.0
        self.last_no_fill_action_ts = 0.0
        self.last_rate_adjust_ts = 0.0
        self.last_rate_limit_seen_ts = 0.0
        self.last_canary_eval_ts = 0.0
        self.canary_baseline: dict[str, float] = {}

        self.symbols = self._load_symbols()
        self.current_symbol_idx = self._choose_primary_index()
        self.current_symbol = self.symbols[self.current_symbol_idx]
        self.base_max_order_notional = self._resolve_base_max_order_notional()

    def _load_export_overrides(self) -> dict[str, str]:
        override_dir = self.dashboard_snapshot.parent
        out: dict[str, str] = {}
        out.update(_parse_export_file(override_dir / "env_overrides.sh"))
        out.update(_parse_export_file(override_dir / "operator_overrides.sh"))
        return out

    def _log(self, message: str) -> None:
        line = f"{_now_iso()} {message}"
        print(line, flush=True)
        with self.manager_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _post_json(self, url: str, payload: dict[str, Any], timeout: float = 4.0) -> None:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout):
            return

    def _send_alert(self, event: str, details: str) -> None:
        text = f"[growth-manager] {event} symbol={self.current_symbol} {details}"
        self._log(f"alert event={event} details={details}")
        if self.alert_webhook_url:
            try:
                self._post_json(self.alert_webhook_url, {"text": text})
            except Exception as exc:
                self._log(f"alert_webhook_error event={event} err={exc}")
        if self.discord_webhook_url:
            try:
                self._post_json(self.discord_webhook_url, {"content": text})
            except Exception as exc:
                self._log(f"alert_discord_error event={event} err={exc}")
        if self.telegram_token and self.telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": self.telegram_chat_id, "text": text}).encode("utf-8")
                req = urllib.request.Request(url, data=data)
                with urllib.request.urlopen(req, timeout=4.0):
                    pass
            except Exception as exc:
                self._log(f"alert_telegram_error event={event} err={exc}")
        if self.smtp_host and self.smtp_to:
            try:
                msg = EmailMessage()
                msg["Subject"] = f"[growth-manager] {event}"
                msg["From"] = self.smtp_from or self.smtp_user or "growth-manager@localhost"
                msg["To"] = self.smtp_to
                msg.set_content(text)
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=6) as smtp:
                    smtp.starttls()
                    if self.smtp_user:
                        smtp.login(self.smtp_user, self.smtp_pass)
                    smtp.send_message(msg)
            except Exception as exc:
                self._log(f"alert_email_error event={event} err={exc}")

    def _load_config(self) -> dict[str, Any]:
        text = self.live_config.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            out = yaml.safe_load(text)
            if isinstance(out, dict):
                return out
        except Exception:
            pass
        return json.loads(text)

    def _save_config(self, cfg: dict[str, Any]) -> None:
        try:
            import yaml  # type: ignore

            self.live_config.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
            return
        except Exception:
            self.live_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def _load_symbols(self) -> list[str]:
        raw = os.getenv("AUTONOMOUS_FALLBACK_SYMBOLS", "").strip()
        symbols: list[str] = []
        if raw:
            for s in raw.split(","):
                ss = s.strip().upper()
                if ss and ss not in symbols:
                    symbols.append(ss)
        if symbols:
            return symbols
        cfg = self._load_config()
        for s in cfg.get("universe", []):
            if isinstance(s, str):
                ss = s.strip().upper()
                if ss and ss not in symbols:
                    symbols.append(ss)
        if not symbols:
            raise SystemExit("No symbols available in AUTONOMOUS_FALLBACK_SYMBOLS or config universe.")
        return symbols

    def _choose_primary_index(self) -> int:
        primary = os.getenv("AUTONOMOUS_PRIMARY_SYMBOL", "").strip().upper()
        if not primary:
            return 0
        for idx, symbol in enumerate(self.symbols):
            if symbol == primary:
                return idx
        return 0

    def _resolve_base_max_order_notional(self) -> float:
        env_val = _env_float("AUTONOMOUS_CANARY_BASE_MAX_ORDER_NOTIONAL", 0.0)
        if env_val > 0.0:
            return env_val
        cfg = self._load_config()
        policy = cfg.get("policy", {}) if isinstance(cfg, dict) else {}
        risk = cfg.get("risk", {}) if isinstance(cfg, dict) else {}
        if isinstance(policy, dict):
            v = _to_float(policy.get("base_risk_budget"), 0.0)
            if v > 0.0:
                return v
        if isinstance(risk, dict):
            v = _to_float(risk.get("max_position_notional"), 0.0)
            if v > 0.0:
                return v
        return max(1.0, _env_float("AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE", 1.0))

    def _effective_max_order_notional(self) -> float:
        return max(0.0, self.base_max_order_notional * max(0.01, self.current_sizing_fraction))

    def _process_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _acquire_lock(self) -> None:
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            if self.pid_file.exists():
                try:
                    old_pid = int(self.pid_file.read_text(encoding="utf-8").strip())
                except Exception:
                    old_pid = 0
                if old_pid > 0 and self._process_alive(old_pid):
                    self._log(f"manager_already_running pid={old_pid}")
                    raise SystemExit(0)
            for path in sorted(self.lock_dir.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
            self.lock_dir.rmdir()
            self.lock_dir.mkdir(parents=True, exist_ok=False)
        self.pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def _release_lock(self) -> None:
        try:
            self.pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            self.lock_dir.rmdir()
        except Exception:
            pass

    def _set_config_symbol_and_limits(self, symbol: str) -> None:
        cfg = self._load_config()
        cfg["universe"] = [symbol]
        providers = cfg.get("provider_whitelist")
        if isinstance(providers, list):
            if "kraken_spot" not in providers:
                providers.append("kraken_spot")
        else:
            cfg["provider_whitelist"] = ["kraken_spot"]

        policy = cfg.get("policy")
        if not isinstance(policy, dict):
            policy = {}
        allowed_policy = {"confidence_threshold", "estimated_cost_bps", "safety_buffer_bps", "base_risk_budget"}
        policy = {k: v for k, v in policy.items() if k in allowed_policy}
        cfg["policy"] = policy

        risk = cfg.get("risk")
        if not isinstance(risk, dict):
            risk = {}
        risk["max_orders_per_min"] = int(self.current_max_orders_per_min)
        risk["max_daily_loss_pct"] = min(self.max_daily_loss_pct, _to_float(risk.get("max_daily_loss_pct"), self.max_daily_loss_pct))
        risk["max_drawdown_pct"] = min(self.max_drawdown_pct, _to_float(risk.get("max_drawdown_pct"), self.max_drawdown_pct))
        cfg["risk"] = risk

        ub = cfg.get("universe_builder")
        if not isinstance(ub, dict):
            ub = {}
        ub["trade_max_positions"] = 1
        cfg["universe_builder"] = ub

        self._save_config(cfg)

    def _kill_orphan_live_processes(self, exclude_pids: set[int] | None = None) -> None:
        exclude = exclude_pids or set()
        pattern = "autonomous_investment_robot live --config"
        try:
            out = subprocess.check_output(["pgrep", "-fl", pattern], text=True)
        except subprocess.CalledProcessError:
            return
        target_name = self.live_config.name
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
            except Exception:
                continue
            cmdline = parts[1]
            if target_name not in cmdline:
                continue
            if pid in exclude:
                continue
            try:
                os.kill(pid, 15)
                # Avoid leaking sensitive values that may appear in process args.
                self._log(f"orphan_live_kill pid={pid} target={target_name}")
            except Exception as exc:
                self._log(f"orphan_live_kill_error pid={pid} err={exc}")

    def _child_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._load_export_overrides())
        env["TESTNET_VALIDATED"] = "true"
        env["ENABLE_LIVE_TRADING"] = "true"
        env["ACK_I_UNDERSTAND_RISKS"] = "true"
        env.setdefault("ORDER_SUBMISSION_INTERVAL_SECONDS", "60")
        env.setdefault("AUTONOMOUS_PROFIT_TARGET_NET", "0.02")
        env.setdefault("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "200")
        env.setdefault("AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS", "500")
        env.setdefault("AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S", "90")
        env.setdefault("AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS", "30")
        env.setdefault("AUTONOMOUS_DYNAMIC_UNIVERSE", "true")
        env.setdefault("AUTONOMOUS_DYNAMIC_UNIVERSE_ALL", "false")
        env.setdefault("AUTONOMOUS_DYNAMIC_UNIVERSE_MAX", "120")
        env.setdefault("AUTONOMOUS_KRAKEN_TRADE_ALL", "false")
        if not str(env.get("AUTONOMOUS_FALLBACK_SYMBOLS", "") or "").strip():
            env["AUTONOMOUS_FALLBACK_SYMBOLS"] = ",".join(self.symbols)
        if not str(env.get("AUTONOMOUS_UNIVERSE_ALLOWLIST", "") or "").strip():
            env["AUTONOMOUS_UNIVERSE_ALLOWLIST"] = str(env.get("AUTONOMOUS_FALLBACK_SYMBOLS", "") or "")
        env["AUTONOMOUS_WALK_FORWARD_ENFORCE"] = "false"
        env["AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE"] = "false"
        env["AUTONOMOUS_MIN_NET_EDGE_BPS"] = f"{self.current_min_net_edge_bps:.6g}"
        env["AUTONOMOUS_RATE_LIMIT_COOLDOWN_S"] = f"{self.current_rate_limit_cooldown_s:.6g}"
        env["AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S"] = env["AUTONOMOUS_RATE_LIMIT_COOLDOWN_S"]
        env["AUTONOMOUS_MAX_ORDERS_PER_MIN"] = str(int(self.current_max_orders_per_min))
        env["AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE"] = f"{self._effective_max_order_notional():.6g}"
        env["AUTONOMOUS_GROWTH_MAX_FRACTION"] = f"{self.current_sizing_fraction:.6g}"
        env["AUTONOMOUS_MODE_LABEL"] = "canary" if self.canary_stage == "canary" else "main"
        env["PYTHONPATH"] = "src"
        return env

    def _start_live(self, reason: str) -> None:
        self._kill_orphan_live_processes(exclude_pids=set())
        self._set_config_symbol_and_limits(self.current_symbol)
        if self.live_out_handle is None or self.live_out_handle.closed:
            self.live_out_handle = self.live_out.open("a", encoding="utf-8")
        cmd = [sys.executable, "-m", "autonomous_investment_robot", "live", "--config", str(self.live_config)]
        self.live_child = subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            env=self._child_env(),
            stdout=self.live_out_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._log(
            "live_start "
            f"reason={reason} symbol={self.current_symbol} pid={self.live_child.pid} "
            f"edge_bps={self.current_min_net_edge_bps:.3f} "
            f"max_orders_per_min={self.current_max_orders_per_min} "
            f"rate_limit_cooldown_s={self.current_rate_limit_cooldown_s:.2f} "
            f"stage={self.canary_stage} sizing_fraction={self.current_sizing_fraction:.3f} "
            f"max_order_quote={self._effective_max_order_notional():.6g}"
        )

    def _stop_live(self, reason: str) -> None:
        child = self.live_child
        if child is None:
            return
        if child.poll() is not None:
            self._log(f"live_stop_skip reason={reason} already_stopped=1")
            self.live_child = None
            return
        self._log(f"live_stop reason={reason} pid={child.pid}")
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        self.live_child = None

    def _restart_live(self, reason: str) -> None:
        self._stop_live(reason=f"{reason}_restart")
        if time.time() < self.paused_until_ts:
            return
        self._start_live(reason=reason)

    def _rotate_symbol(self) -> bool:
        if len(self.symbols) <= 1:
            return False
        self.current_symbol_idx = (self.current_symbol_idx + 1) % len(self.symbols)
        self.current_symbol = self.symbols[self.current_symbol_idx]
        self.last_switch_ts = time.time()
        return True

    def _read_new_audit_events(self) -> None:
        if not self.audit_log.exists():
            return
        size = self.audit_log.stat().st_size
        if size < self.audit_offset:
            self.audit_offset = 0
        with self.audit_log.open("r", encoding="utf-8", errors="ignore") as fh:
            fh.seek(self.audit_offset)
            text = fh.read()
            self.audit_offset = fh.tell()
        if not text:
            return
        now = time.time()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            et = str(event.get("event_type", ""))
            payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
            symbol = str(payload.get("symbol", "")).upper()
            if et == "live_exec":
                self.exec_events.append(
                    (
                        now,
                        str(payload.get("status", "")),
                        str(payload.get("reason", "")),
                        symbol,
                    )
                )
            elif et == "fill_sync_error":
                err = str(payload.get("error", ""))
                if "Rate limit exceeded" in err or "rate limit" in err.lower():
                    self.rate_limit_events.append(now)
                    self.last_rate_limit_seen_ts = now
            elif et == "heartbeat":
                eq = payload.get("equity")
                if eq is not None:
                    self.latest_equity = _to_float(eq, self.latest_equity)

    def _read_dashboard(self) -> dict[str, Any]:
        if not self.dashboard_snapshot.exists():
            return {}
        try:
            data = json.loads(self.dashboard_snapshot.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        groups = data.get("groups", {})
        if not isinstance(groups, dict):
            return {}

        execution = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
        risk = groups.get("risk", {}) if isinstance(groups.get("risk"), dict) else {}
        performance = groups.get("performance", {}) if isinstance(groups.get("performance"), dict) else {}

        sample = MetricsSample(
            ts=time.time(),
            intents_total=_to_float(execution.get("intents_total"), 0.0),
            attempted_total=_to_float(execution.get("executions_attempted_total"), 0.0),
            rejected_total=_to_float(execution.get("orders_rejected_total"), 0.0),
            fills_total=_to_float(execution.get("fills_confirmed_total"), 0.0),
        )
        self.samples.append(sample)

        drawdown_pct = max(
            _to_float(risk.get("drawdown"), 0.0),
            _to_float(performance.get("max_drawdown"), 0.0),
        )

        self.latest_dashboard = {
            "raw": data,
            "groups": groups,
            "execution": execution,
            "risk": risk,
            "performance": performance,
            "drawdown_pct": drawdown_pct,
        }
        return self.latest_dashboard

    def _window_delta(self, window_s: float) -> dict[str, float]:
        if len(self.samples) < 2:
            return {"attempted": 0.0, "rejected": 0.0, "intents": 0.0, "fills": 0.0}
        now = self.samples[-1].ts
        cutoff = now - window_s
        base = self.samples[0]
        for sample in reversed(self.samples):
            if sample.ts <= cutoff:
                base = sample
                break
        curr = self.samples[-1]
        return {
            "attempted": max(0.0, curr.attempted_total - base.attempted_total),
            "rejected": max(0.0, curr.rejected_total - base.rejected_total),
            "intents": max(0.0, curr.intents_total - base.intents_total),
            "fills": max(0.0, curr.fills_total - base.fills_total),
        }

    def _consecutive_bad_execs(self, symbol: str) -> int:
        bad_tokens = (
            "insufficient_balance_block",
            "insufficient_base_balance_block",
            "min_order_block",
            "Invalid permissions",
            "EAccount:Invalid permissions",
        )
        count = 0
        for _, status, reason, sym in reversed(self.exec_events):
            if sym != symbol:
                continue
            if status not in {"blocked", "rejected"}:
                break
            if any(tok in reason for tok in bad_tokens):
                count += 1
                continue
            break
        return count

    def _write_snapshot(self, quality: dict[str, float], no_fill: dict[str, float], rate_limit_count: int) -> None:
        snap = {
            "ts": _now_iso(),
            "uptime_s": int(time.time() - self.start_ts),
            "active_symbol": self.current_symbol,
            "live_pid": self.live_child.pid if self.live_child and self.live_child.poll() is None else None,
            "paused_until_epoch": self.paused_until_ts,
            "aggressiveness": {
                "min_net_edge_bps": self.current_min_net_edge_bps,
                "max_orders_per_min": self.current_max_orders_per_min,
                "rate_limit_cooldown_s": self.current_rate_limit_cooldown_s,
                "max_order_notional_quote": self._effective_max_order_notional(),
            },
            "canary": {
                "enabled": self.canary_enabled,
                "stage": self.canary_stage,
                "sizing_fraction": self.current_sizing_fraction,
                "base_max_order_notional_quote": self.base_max_order_notional,
            },
            "equity": self.latest_equity,
            "daily_loss_pct": self._daily_loss_pct(),
            "drawdown_pct": _to_float(self.latest_dashboard.get("drawdown_pct"), 0.0),
            "quality_gate_10m": quality,
            "no_fill_gate_2h": no_fill,
            "rate_limit_events_10m": rate_limit_count,
            "kpi": {
                "efficiency": self.latest_dashboard.get("groups", {}).get("efficiency", {}),
                "execution": self.latest_dashboard.get("execution", {}),
                "risk": self.latest_dashboard.get("risk", {}),
                "performance": self.latest_dashboard.get("performance", {}),
            },
        }
        with self.snapshot_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snap, ensure_ascii=True) + "\n")
        self.snapshot_latest.write_text(json.dumps(snap, indent=2, ensure_ascii=True), encoding="utf-8")

    def _daily_loss_pct(self) -> float:
        if self.start_equity is None or self.start_equity <= 0:
            return 0.0
        return max(0.0, (self.start_equity - self.latest_equity) / self.start_equity * 100.0)

    def _check_loss_stop(self) -> bool:
        dd = _to_float(self.latest_dashboard.get("drawdown_pct"), 0.0)
        daily_loss = self._daily_loss_pct()
        if daily_loss >= self.max_daily_loss_pct or dd >= self.max_drawdown_pct:
            self._send_alert(
                "drawdown_limit",
                f"daily_loss_pct={daily_loss:.3f} max_daily={self.max_daily_loss_pct:.3f} "
                f"drawdown_pct={dd:.3f} max_drawdown={self.max_drawdown_pct:.3f}",
            )
            self._stop_live(reason="drawdown_limit")
            self.shutdown_reason = "drawdown_limit"
            return True
        return False

    def _check_quality_gate(self, now: float) -> dict[str, float]:
        delta = self._window_delta(self.quality_window_s)
        attempted = delta["attempted"]
        rejected = delta["rejected"]
        reject_ratio = 0.0 if attempted <= 0 else rejected / attempted
        out = {"attempted": attempted, "rejected": rejected, "reject_ratio": reject_ratio}

        if attempted < self.quality_min_attempts:
            return out
        if reject_ratio <= self.quality_trigger_ratio:
            return out
        if now - self.last_quality_adjust_ts < self.quality_adjust_cooldown_s:
            return out

        prev_orders = self.current_max_orders_per_min
        prev_edge = self.current_min_net_edge_bps
        self.current_max_orders_per_min = max(self.quality_min_orders_floor, self.current_max_orders_per_min - self.quality_orders_step)
        edge_cap = max(self.quality_max_edge_cap, prev_edge)
        self.current_min_net_edge_bps = min(edge_cap, prev_edge + self.quality_edge_step_bps)
        changed = prev_orders != self.current_max_orders_per_min or abs(prev_edge - self.current_min_net_edge_bps) > 1e-12
        if not changed:
            return out

        self.last_quality_adjust_ts = now
        self._send_alert(
            "quality_gate_degrade",
            f"reject_ratio_10m={reject_ratio:.3f} attempted_10m={attempted:.1f} rejected_10m={rejected:.1f} "
            f"max_orders_per_min:{prev_orders}->{self.current_max_orders_per_min} "
            f"min_net_edge_bps:{prev_edge:.3f}->{self.current_min_net_edge_bps:.3f}",
        )
        self._restart_live(reason="quality_gate_degrade")
        return out

    def _check_no_fill_gate(self, now: float) -> dict[str, float]:
        delta = self._window_delta(self.no_fill_window_s)
        intents = delta["intents"]
        fills = delta["fills"]
        if intents < self.no_fill_min_intents or fills > 0:
            return {"intents": intents, "fills": fills, "triggered": 0.0}
        if now - self.last_no_fill_action_ts < self.no_fill_action_cooldown_s:
            return {"intents": intents, "fills": fills, "triggered": 0.0}

        self.last_no_fill_action_ts = now
        triggered = 1.0
        if now - self.last_switch_ts >= self.fallback_cooldown_s and self._rotate_symbol():
            self._send_alert(
                "no_fill_gate_switch",
                f"intents_2h={intents:.1f} fills_2h={fills:.1f} switched_to={self.current_symbol}",
            )
            self._restart_live(reason="no_fill_gate_switch")
        else:
            self.paused_until_ts = now + self.no_fill_pause_s
            self._send_alert(
                "no_fill_gate_pause",
                f"intents_2h={intents:.1f} fills_2h={fills:.1f} pause_s={self.no_fill_pause_s:.0f}",
            )
            self._stop_live(reason="no_fill_gate_pause")
        return {"intents": intents, "fills": fills, "triggered": triggered}

    def _canary_metrics(self) -> dict[str, float]:
        groups = self.latest_dashboard.get("groups", {})
        execution = groups.get("execution", {}) if isinstance(groups, dict) and isinstance(groups.get("execution"), dict) else {}
        efficiency = groups.get("efficiency", {}) if isinstance(groups, dict) and isinstance(groups.get("efficiency"), dict) else {}
        performance = groups.get("performance", {}) if isinstance(groups, dict) and isinstance(groups.get("performance"), dict) else {}
        return {
            "submitted_total": _to_float(execution.get("executions_submitted_total"), 0.0),
            "reject_rate": _to_float(execution.get("reject_rate"), 0.0),
            "cost_to_alpha": _to_float(efficiency.get("cost_to_alpha_ratio_modeled"), 0.0),
            "net_pnl_after_fees": _to_float(performance.get("net_pnl_after_fees"), 0.0),
            "divergence_bps": _to_float(efficiency.get("live_vs_backtest_divergence_bps"), 0.0),
        }

    def _check_canary_autopilot(self, now: float, rate_limit_count: int) -> None:
        if not self.canary_enabled:
            return
        if now - self.last_canary_eval_ts < self.canary_eval_cooldown_s:
            return
        metrics = self._canary_metrics()
        submitted_total = metrics["submitted_total"]
        reject_rate = metrics["reject_rate"]
        cost_to_alpha = metrics["cost_to_alpha"]
        net_pnl_after_fees = metrics["net_pnl_after_fees"]
        divergence_bps = metrics["divergence_bps"]
        if submitted_total <= 0.0:
            return

        if self.canary_stage == "canary" and not self.canary_baseline:
            self.canary_baseline = dict(metrics)

        self.last_canary_eval_ts = now
        baseline_reject = _to_float(self.canary_baseline.get("reject_rate"), self.canary_promote_max_reject_rate)
        baseline_cost = _to_float(self.canary_baseline.get("cost_to_alpha"), self.canary_promote_max_cost_to_alpha)
        baseline_net = _to_float(self.canary_baseline.get("net_pnl_after_fees"), self.canary_promote_min_net_pnl)

        if self.canary_stage == "canary":
            promote_ok = (
                submitted_total >= self.canary_promote_min_submitted
                and reject_rate <= min(self.canary_promote_max_reject_rate, baseline_reject + 0.05)
                and cost_to_alpha > 0.0
                and cost_to_alpha <= min(self.canary_promote_max_cost_to_alpha, max(0.1, baseline_cost + 0.1))
                and net_pnl_after_fees >= max(self.canary_promote_min_net_pnl, baseline_net)
                and rate_limit_count < self.rate_limit_storm_threshold
                and abs(divergence_bps) <= self.canary_rollback_divergence_bps
            )
            if promote_ok:
                prev = self.current_sizing_fraction
                self.canary_stage = "promoted"
                self.current_sizing_fraction = self.promoted_fraction
                self._send_alert(
                    "canary_promote",
                    (
                        f"submitted={submitted_total:.1f} reject_rate={reject_rate:.3f} "
                        f"cost_to_alpha={cost_to_alpha:.3f} net_pnl_after_fees={net_pnl_after_fees:.3f} "
                        f"sizing_fraction:{prev:.3f}->{self.current_sizing_fraction:.3f}"
                    ),
                )
                self._restart_live(reason="canary_promote")
            return

        rollback_trigger = (
            rate_limit_count >= self.rate_limit_storm_threshold
            or abs(divergence_bps) > self.canary_rollback_divergence_bps
            or net_pnl_after_fees <= self.canary_rollback_net_pnl
        )
        if rollback_trigger:
            prev = self.current_sizing_fraction
            self.canary_stage = "canary"
            self.current_sizing_fraction = self.canary_fraction
            self.canary_baseline = dict(metrics)
            self._send_alert(
                "canary_rollback",
                (
                    f"rate_limit_10m={rate_limit_count} divergence_bps={divergence_bps:.3f} "
                    f"net_pnl_after_fees={net_pnl_after_fees:.3f} "
                    f"sizing_fraction:{prev:.3f}->{self.current_sizing_fraction:.3f}"
                ),
            )
            self._restart_live(reason="canary_rollback")

    def _check_fallback_consecutive(self, now: float) -> None:
        if now - self.last_switch_ts < self.fallback_cooldown_s:
            return
        nbad = self._consecutive_bad_execs(self.current_symbol)
        if nbad < self.fallback_consecutive_rejects:
            return
        if not self._rotate_symbol():
            self._send_alert(
                "fallback_no_alternative",
                f"reason=consecutive_bad_execs count={nbad} symbol={self.current_symbol}",
            )
            return
        self._send_alert(
            "fallback_switch",
            f"reason=consecutive_bad_execs count={nbad} switched_to={self.current_symbol}",
        )
        self._restart_live(reason="fallback_switch")

    def _check_rate_limit_storm(self, now: float) -> int:
        while self.rate_limit_events and self.rate_limit_events[0] < now - self.rate_limit_window_s:
            self.rate_limit_events.popleft()
        count = len(self.rate_limit_events)
        if count >= self.rate_limit_storm_threshold:
            if self.current_rate_limit_cooldown_s < self.rate_limit_cooldown_storm_s and now - self.last_rate_adjust_ts >= self.rate_limit_adjust_cooldown_s:
                prev = self.current_rate_limit_cooldown_s
                self.current_rate_limit_cooldown_s = self.rate_limit_cooldown_storm_s
                self.last_rate_adjust_ts = now
                self._send_alert(
                    "rate_limit_storm",
                    f"events_10m={count} cooldown_s:{prev:.2f}->{self.current_rate_limit_cooldown_s:.2f}",
                )
                self._restart_live(reason="rate_limit_storm")
            return count

        if (
            self.current_rate_limit_cooldown_s > self.rate_limit_cooldown_normal_s
            and now - self.last_rate_limit_seen_ts >= self.rate_limit_relax_after_s
            and now - self.last_rate_adjust_ts >= self.rate_limit_adjust_cooldown_s
        ):
            prev = self.current_rate_limit_cooldown_s
            self.current_rate_limit_cooldown_s = self.rate_limit_cooldown_normal_s
            self.last_rate_adjust_ts = now
            self._send_alert(
                "rate_limit_relaxed",
                f"events_10m={count} cooldown_s:{prev:.2f}->{self.current_rate_limit_cooldown_s:.2f}",
            )
            self._restart_live(reason="rate_limit_relaxed")
        return count

    def _maybe_handle_child_exit(self) -> None:
        if self.live_child is None:
            return
        rc = self.live_child.poll()
        if rc is None:
            return
        pid = self.live_child.pid
        self.live_child = None
        self._send_alert("live_exit", f"pid={pid} return_code={rc}")

    def run(self) -> int:
        self._acquire_lock()
        self._log(
            "manager_start "
            f"symbols={','.join(self.symbols)} primary={self.current_symbol} runtime_s={self.max_runtime_s:.0f} "
            f"loss_limits=daily:{self.max_daily_loss_pct:.2f}% dd:{self.max_drawdown_pct:.2f}% "
            f"canary_stage={self.canary_stage} sizing_fraction={self.current_sizing_fraction:.3f}"
        )
        self._send_alert(
            "manager_start",
            (
                f"symbols={','.join(self.symbols)} primary={self.current_symbol} runtime_s={self.max_runtime_s:.0f} "
                f"canary_stage={self.canary_stage} sizing_fraction={self.current_sizing_fraction:.3f}"
            ),
        )
        try:
            self._start_live(reason="initial_start")
            while self.running:
                now = time.time()
                self._read_new_audit_events()
                self._read_dashboard()
                if self.start_equity is None:
                    self.start_equity = self.latest_equity

                self._maybe_handle_child_exit()

                if now >= self.stop_ts:
                    self._send_alert("runtime_complete", f"runtime_s={self.max_runtime_s:.0f}")
                    self._stop_live(reason="runtime_complete")
                    self.shutdown_reason = "runtime_complete"
                    break

                if self._check_loss_stop():
                    break

                if now < self.paused_until_ts:
                    if self.live_child is not None:
                        self._stop_live(reason="paused_window")
                else:
                    if self.live_child is None:
                        self._start_live(reason="resume_or_restart")

                quality = self._check_quality_gate(now)
                no_fill = self._check_no_fill_gate(now)
                rate_limit_count = self._check_rate_limit_storm(now)
                self._check_canary_autopilot(now, rate_limit_count)
                self._check_fallback_consecutive(now)

                if now - self.last_snapshot_ts >= self.snapshot_interval_s:
                    self._write_snapshot(quality=quality, no_fill=no_fill, rate_limit_count=rate_limit_count)
                    self.last_snapshot_ts = now

                time.sleep(self.health_interval_s)

            rc = 0 if self.shutdown_reason in {"runtime_complete", ""} else 1
            return rc
        except KeyboardInterrupt:
            self.shutdown_reason = "manual_interrupt"
            return 0
        finally:
            self._stop_live(reason="manager_shutdown")
            if self.live_out_handle is not None:
                try:
                    self.live_out_handle.close()
                except Exception:
                    pass
            self._release_lock()
            self._log(f"manager_stop reason={self.shutdown_reason or 'manual_or_unknown'}")


def main() -> int:
    mgr = GrowthManager()
    return mgr.run()


if __name__ == "__main__":
    raise SystemExit(main())
