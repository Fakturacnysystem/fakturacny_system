from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "prepare_tiny_live_run_dir.py"
SPEC = importlib.util.spec_from_file_location("prepare_tiny_live_run_dir", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _Settings:
    def __init__(self, run_dir: str) -> None:
        self.storage = type("Storage", (), {"run_dir": run_dir})()
        self.execution = type("Execution", (), {"provider_id": "kraken_spot", "kraken_spot": object()})()
        self.universe = ["BTC/USD"]

    def execution_mode_enum(self):
        return MODULE.ExecutionMode.LIVE


def test_prepare_tiny_live_run_dir_archives_flat_stale_local_state(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "kraken_spot_tiny_live"
        archive_root = Path(tmp) / "run_archives"
        run_dir.mkdir(parents=True)
        (run_dir / "events_fills.jsonl").write_text(json.dumps({"id": "fill"}) + "\n", encoding="utf-8")
        (run_dir / "events_orders.jsonl").write_text(json.dumps({"id": "order"}) + "\n", encoding="utf-8")
        settings = _Settings(str(run_dir))

        monkeypatch.setattr(
            MODULE,
            "inspect_exchange_state",
            lambda settings: {
                "ok": True,
                "flat": True,
                "open_order_count": 0,
                "reason": "exchange_flat_no_open_orders",
            },
        )

        payload = MODULE.prepare_tiny_live_run_dir(settings, archive_root=archive_root)

        assert payload["action"] == "archive_and_reset"
        assert Path(payload["archived_run_dir"]).exists()
        assert run_dir.exists()
        assert not (run_dir / "events_fills.jsonl").exists()
        assert (Path(payload["archived_run_dir"]) / "events_fills.jsonl").exists()


def test_prepare_tiny_live_run_dir_archives_non_flat_session_when_exchange_history_can_rebuild(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "kraken_spot_tiny_live"
        archive_root = Path(tmp) / "run_archives"
        run_dir.mkdir(parents=True)
        (run_dir / "events_fills.jsonl").write_text(json.dumps({"id": "fill"}) + "\n", encoding="utf-8")
        settings = _Settings(str(run_dir))

        monkeypatch.setattr(
            MODULE,
            "inspect_exchange_state",
            lambda settings: {
                "ok": True,
                "flat": False,
                "open_order_count": 0,
                "reason": "exchange_session_active",
            },
        )

        payload = MODULE.prepare_tiny_live_run_dir(settings, archive_root=archive_root)

        assert payload["action"] == "archive_and_reset"
        assert payload["reason"] == "exchange_inventory_session_rehydrate"
        assert run_dir.exists()
        assert not (run_dir / "events_fills.jsonl").exists()
        assert archive_root.exists()
        archived = Path(payload["archived_run_dir"])
        assert (archived / "events_fills.jsonl").exists()
        manifest = json.loads((archived / "tiny_live_session_prepare.json").read_text(encoding="utf-8"))
        assert manifest["rehydrate_expected_from_exchange_history"] is True


def test_prepare_tiny_live_run_dir_preserves_existing_session_when_exchange_open_orders_present(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "kraken_spot_tiny_live"
        archive_root = Path(tmp) / "run_archives"
        run_dir.mkdir(parents=True)
        (run_dir / "events_fills.jsonl").write_text(json.dumps({"id": "fill"}) + "\n", encoding="utf-8")
        settings = _Settings(str(run_dir))

        monkeypatch.setattr(
            MODULE,
            "inspect_exchange_state",
            lambda settings: {
                "ok": True,
                "flat": False,
                "open_order_count": 1,
                "reason": "exchange_session_active",
            },
        )

        payload = MODULE.prepare_tiny_live_run_dir(settings, archive_root=archive_root)

        assert payload["action"] == "preserve_existing_session"
        assert payload["reason"] == "exchange_open_orders_present"
        assert (run_dir / "events_fills.jsonl").exists()
        assert not archive_root.exists()


def test_prepare_tiny_live_run_dir_noops_when_run_dir_has_no_runtime_state(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "kraken_spot_tiny_live"
        archive_root = Path(tmp) / "run_archives"
        settings = _Settings(str(run_dir))

        monkeypatch.setattr(
            MODULE,
            "inspect_exchange_state",
            lambda settings: {
                "ok": True,
                "flat": True,
                "open_order_count": 0,
                "reason": "exchange_flat_no_open_orders",
            },
        )

        payload = MODULE.prepare_tiny_live_run_dir(settings, archive_root=archive_root)

        assert payload["action"] == "none"
        assert payload["reason"] == "no_local_runtime_state"
        assert run_dir.exists()
