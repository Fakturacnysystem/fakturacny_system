from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from autonomous_investment_robot.services.llm import (
    LLMProviderClient,
    resolve_provider_config,
)

MISSING_KEY_MESSAGE = (
    "LLM self-improvement is disabled because no compatible provider credentials were found. "
    "Set GROQ_API_KEY (preferred here) or OPENAI_API_KEY and restart."
)


@dataclass
class SelfImproveSuggestion:
    key: str
    value: str
    reason: str
    confidence: float


class LLMSelfImprovementAdvisor:
    """Generates bounded config suggestions from recent runtime logs.

    Safety boundary:
    - No exchange connectors are used.
    - No order submission APIs are called.
    - Only reads logs/metrics and writes suggestion artifacts.
    """

    def __init__(
        self,
        run_dir: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        model_fallback: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
        remote_healthcheck: bool | None = None,
        llm_augment_enabled: bool | None = None,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_path = self.run_dir / "audit.log"
        self.metrics_path = self.run_dir / "metrics.json"
        self.output_path = self.run_dir / "config_suggestions.yaml"
        self.diag_path = self.run_dir / "llm_self_improvement_diagnostics.json"

        env_map: dict[str, str] = dict(os.environ)
        key_override = str(api_key or "").strip()
        provider_hint = str(provider or env_map.get("LLM_PROVIDER", "") or "").strip().lower()
        if key_override:
            if provider_hint == "groq" or str(base_url or "").strip().startswith("https://api.groq.com/"):
                env_map["GROQ_API_KEY"] = key_override
            else:
                env_map["OPENAI_API_KEY"] = key_override
        self.provider_config = resolve_provider_config(
            env=env_map,
            provider=provider,
            model=model,
            model_fallback=model_fallback,
            base_url=base_url,
            enabled=enabled,
            healthcheck_remote=remote_healthcheck,
        )
        self.provider_client = LLMProviderClient(self.provider_config, env=env_map)
        self.model = self.provider_config.model
        self.provider = self.provider_config.provider
        if llm_augment_enabled is None:
            llm_augment_enabled = str(os.getenv("AUTONOMOUS_SELF_IMPROVEMENT_LLM_ENABLED", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
        self.llm_augment_enabled = bool(llm_augment_enabled)

    @property
    def enabled(self) -> bool:
        return bool(self.provider_config.enabled)

    @property
    def openai_enabled(self) -> bool:
        return bool(self.enabled and self.provider == "openai")

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

    def _merge_suggestions(
        self,
        base: list[SelfImproveSuggestion],
        extra: list[SelfImproveSuggestion],
    ) -> list[SelfImproveSuggestion]:
        out: dict[str, SelfImproveSuggestion] = {row.key: row for row in base if row.key}
        for row in extra:
            if not row.key:
                continue
            prev = out.get(row.key)
            if prev is None or float(row.confidence) >= float(prev.confidence):
                out[row.key] = row
        return sorted(out.values(), key=lambda x: x.key)

    def _llm_suggestions(
        self,
        *,
        events: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> list[SelfImproveSuggestion]:
        if not self.llm_augment_enabled:
            return []
        if not self.enabled:
            return []
        schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["suggestions"],
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["key", "value", "reason", "confidence"],
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                            "reason": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                    },
                }
            },
        }
        instructions = (
            "Return only safe env tuning suggestions as JSON. "
            "Allowed keys: AUTONOMOUS_RATE_LIMIT_COOLDOWN_S, AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S, "
            "AUTONOMOUS_MAX_ORDERS_PER_MIN, AUTONOMOUS_MARKET_WATCH_EVERY_S, AUTONOMOUS_CONFIDENCE_THRESHOLD. "
            "Never suggest disabling safety, kill switches, min-profit floor, or guards mode."
        )
        payload = {
            "events_recent_count": len(events),
            "events_tail": events[-120:],
            "metrics": metrics,
        }
        try:
            raw = self.provider_client.create_structured_json(
                instructions=instructions,
                user_payload=payload,
                schema_name="llm_self_improve_suggestions",
                schema=schema,
            )
        except Exception:
            return []
        rows = raw.get("suggestions", []) if isinstance(raw, dict) else []
        out: list[SelfImproveSuggestion] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("key", "") or "").strip()
            val = str(row.get("value", "") or "").strip()
            reason = str(row.get("reason", "") or "").strip()
            try:
                conf = float(row.get("confidence", 0.0) or 0.0)
            except Exception:
                conf = 0.0
            if not key or not val:
                continue
            if key not in {
                "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S",
                "AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S",
                "AUTONOMOUS_MAX_ORDERS_PER_MIN",
                "AUTONOMOUS_MARKET_WATCH_EVERY_S",
                "AUTONOMOUS_CONFIDENCE_THRESHOLD",
            }:
                continue
            conf = max(0.0, min(1.0, conf))
            out.append(
                SelfImproveSuggestion(
                    key=key,
                    value=val,
                    reason=reason or "llm_advice",
                    confidence=conf,
                )
            )
        return out

    def _write_yaml_suggestions(self, suggestions: list[SelfImproveSuggestion], *, generated_at: str, window_hours: float) -> None:
        lines: list[str] = [
            f"generated_at: \"{generated_at}\"",
            f"window_hours: {window_hours}",
            f"model: \"{self.model}\"",
            "source: \"heuristic+optional-llm\"",
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
        llm_health = self.provider_client.health_check(remote=self.provider_config.healthcheck_remote)
        llm_generated = self._llm_suggestions(events=events, metrics=metrics)
        suggestions = self._merge_suggestions(suggestions, llm_generated)
        self._write_yaml_suggestions(
            suggestions,
            generated_at=now.isoformat(),
            window_hours=window_h,
        )

        diag = {
            "provider": self.provider,
            "model": self.model,
            "model_fallback": self.provider_config.model_fallback,
            "model_effective": self.provider_client.last_model_used,
            "llm_enabled": self.enabled,
            "llm_augment_enabled": self.llm_augment_enabled,
            "provider_health": llm_health,
            "events_scanned": len(events),
            "suggestions_count": len(suggestions),
            "ts": now.isoformat(),
        }
        try:
            self.diag_path.write_text(json.dumps(diag, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

        report = {
            "status": "ok",
            "llm_enabled": self.enabled,
            "openai_enabled": self.openai_enabled,
            "provider": self.provider,
            "message": "" if self.enabled else MISSING_KEY_MESSAGE,
            "model": self.model,
            "model_fallback": self.provider_config.model_fallback,
            "model_effective": self.provider_client.last_model_used,
            "run_dir": str(self.run_dir),
            "output_file": str(self.output_path),
            "diagnostics_file": str(self.diag_path),
            "provider_health": llm_health,
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


class OpenAISelfImprovementAdvisor(LLMSelfImprovementAdvisor):
    """Backward-compatible alias for legacy imports/tests."""
