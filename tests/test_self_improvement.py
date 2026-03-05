from __future__ import annotations

import json
from pathlib import Path

from autonomous_investment_robot.services.research.self_improvement import (
    MISSING_KEY_MESSAGE,
    OpenAISelfImprovementAdvisor,
)


def _write_audit(run_dir: Path, rows: list[dict]) -> None:
    payload = "\n".join(json.dumps(r) for r in rows) + "\n"
    (run_dir / "audit.log").write_text(payload, encoding="utf-8")


def test_self_improve_reports_missing_openai_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_audit(
        run_dir,
        [
            {"event_type": "heartbeat", "payload": {"symbol": "XBTEUR"}},
        ],
    )

    advisor = OpenAISelfImprovementAdvisor(str(run_dir))
    out = advisor.run(last_hours=24.0)

    assert out["status"] == "ok"
    assert out["openai_enabled"] is False
    assert out["message"] == MISSING_KEY_MESSAGE
    assert Path(out["output_file"]).exists()


def test_self_improve_generates_rate_limit_suggestion(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_audit(
        run_dir,
        [
            {"event_type": "fill_sync_error", "payload": {"error": "Kraken rate limit: EAPI:Rate limit exceeded"}}
            for _ in range(6)
        ],
    )

    advisor = OpenAISelfImprovementAdvisor(str(run_dir))
    out = advisor.run(last_hours=24.0)

    assert out["status"] == "ok"
    assert out["openai_enabled"] is True
    assert out["message"] == ""
    keys = {row["key"] for row in out["suggestions"]}
    assert "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S" in keys
    suggestion_file = Path(out["output_file"])
    assert suggestion_file.exists()
    text = suggestion_file.read_text(encoding="utf-8")
    assert "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S" in text


def test_self_improve_cannot_submit_orders(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    advisor = OpenAISelfImprovementAdvisor(str(run_dir), api_key="dummy")
    assert not hasattr(advisor, "add_order")
    assert not hasattr(advisor, "send_order")
