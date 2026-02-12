import json
from datetime import datetime, timezone


class OpsService:
    def record_metric(self, name: str, value: float) -> None:
        print(f"METRIC {name}={value}")

    def emit_alert(self, alert_type: str, text: str) -> None:
        print(f"ALERT {alert_type}: {text}")

    def audit_event(self, event_type: str, payload: dict) -> None:
        print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "payload": payload}))
