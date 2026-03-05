from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any


MISSING_KEY_MESSAGE = (
    "OpenAI self-improvement is disabled because OPENAI_API_KEY is missing. "
    "Why are you not using OpenAI API keys for self-improvement? "
    "If you want it enabled, set OPENAI_API_KEY and restart."
)


@dataclass
class SelfImproveSuggestion:
    key: str
    value: str
    reason: str
    confidence: float


class OpenAISelfImprovementAdvisor:
    """Generates config suggestions from recent runtime logs.

    Safety boundary:
    - No exchange connectors are used.
    - No order submission APIs are called.
    - Only reads logs/metrics and writes suggestion artifacts.
    """

    def __init__(self, run_dir: str, *, model: str | None = None, api_key: str | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.model = str(model or os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()
        self.api_key = str(api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.audit_log_path = self.run_dir / "audit.log"
        self.metrics_path = self.run_dir / "metrics.json"
        self.output_path = self.run_dir / "config_suggestions.yaml"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _read_recent_events(self, *, since_ts: float) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.audit_log_path.exists():
            return out
        for raw in self.audit_log_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            ts = row.get("ts") or row.get("timestamp") or row.get("time")
            keep = True
            if ts is not None:
                try:
                    keep = float(ts) >= since_ts
                except Exception:
                    keep = True
            if keep:
                out.append(row)
        return out

    def _metrics_snapshot(self) -> dict[str, Any]:
        if not self.metrics_path.exists():
            return {}
        try:
            raw = json.loads(self.metrics_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _heuristic_suggestions(self, events: list[dict[str, Any]], metrics: dict[str, Any]) -> list[SelfImproveSuggestion]:
        rate_limit_hits = 0
        insufficient_hits = 0
        reject_hits = 0
        for row in events:
            event_type = str(row.get("event_type", "")).lower()
            payload = row.get("payload", {}) if isinstance(row.get("payload", {}), dict) else {}
            reason = str(payload.get("reason", row.get("reason", ""))).lower()
            err = str(payload.get("error", "")).lower()
            if "rate limit" in err or "rate_limit" in reason:
                rate_limit_hits += 1
            if "insufficient_balance" in reason or "insufficient funds" in reason:
                insufficient_hits += 1
            if "reject_rate" in reason or event_type == "risk_reject":
                reject_hits += 1

        out: list[SelfImproveSuggestion] = []
        if rate_limit_hits >= 5:
            out.append(
                SelfImproveSuggestion(
                    key="AUTONOMOUS_RATE_LIMIT_COOLDOWN_S",
                    value="9",
                    reason=f"Observed frequent rate-limit pressure ({rate_limit_hits} events).",
                    confidence=0.86,
                )
            )
        if insufficient_hits >= 3:
            out.append(
                SelfImproveSuggestion(
                    key="AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE",
                    value="0.25",
                    reason=f"Observed balance insufficiency bursts ({insufficient_hits} events).",
                    confidence=0.78,
                )
            )
        if reject_hits >= 5:
            out.append(
                SelfImproveSuggestion(
                    key="AUTONOMOUS_MAX_ORDERS_PER_MIN",
                    value="6",
                    reason=f"Observed high reject pressure ({reject_hits} events).",
                    confidence=0.73,
                )
            )

        health_score = metrics.get("health_score")
        try:
            health_val = float(health_score)
            if health_val < 85.0:
                out.append(
                    SelfImproveSuggestion(
                        key="AUTONOMOUS_HEALTH_AUDIT_INTERVAL_S",
                        value="300",
                        reason="Health score is below target; recommend tighter audit cadence.",
                        confidence=0.70,
                    )
                )
        except Exception:
            pass
        return out

    def _write_yaml_suggestions(self, suggestions: list[SelfImproveSuggestion], *, generated_at: str, window_hours: float) -> None:
        lines: list[str] = [
            f"generated_at: \"{generated_at}\"",
            f"window_hours: {window_hours}",
            f"model: \"{self.model}\"",
            "source: \"heuristic+optional-openai\"",
            "suggestions:",
        ]
        for row in suggestions:
            lines.extend(
                [
                    f"  - key: \"{row.key}\"",
                    f"    value: \"{row.value}\"",
                    f"    reason: \"{row.reason}\"",
                    f"    confidence: {max(0.0, min(1.0, float(row.confidence))):.2f}",
                ]
            )
        if not suggestions:
            lines.append("  - key: \"none\"")
            lines.append("    value: \"noop\"")
            lines.append("    reason: \"No robust suggestion from recent telemetry.\"")
            lines.append("    confidence: 0.50")
        self.output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self, *, last_hours: float = 24.0) -> dict[str, Any]:
        window_h = max(1.0, float(last_hours))
        now = datetime.now(timezone.utc)
        since_ts = (now - timedelta(hours=window_h)).timestamp()
        events = self._read_recent_events(since_ts=since_ts)
        metrics = self._metrics_snapshot()

        suggestions = self._heuristic_suggestions(events, metrics)
        self._write_yaml_suggestions(
            suggestions,
            generated_at=now.isoformat(),
            window_hours=window_h,
        )

        report = {
            "status": "ok",
            "openai_enabled": self.enabled,
            "message": "" if self.enabled else MISSING_KEY_MESSAGE,
            "model": self.model,
            "run_dir": str(self.run_dir),
            "output_file": str(self.output_path),
            "events_scanned": len(events),
            "suggestions": [
                {
                    "key": x.key,
                    "value": x.value,
                    "reason": x.reason,
                    "confidence": x.confidence,
                }
                for x in suggestions
            ],
        }
        return report
