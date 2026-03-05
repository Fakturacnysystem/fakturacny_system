from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import yaml

from autonomous_investment_robot.config.settings import _load_yaml_like
from autonomous_investment_robot.services.storage import SQLiteStore


try:  # pragma: no cover - exercised in runtime if flask is installed
    from flask import Flask, jsonify, request  # type: ignore
    _HAS_FLASK = True
except Exception:  # pragma: no cover - fallback path tested via unit tests
    _HAS_FLASK = False

    class _MiniResponse:
        def __init__(self, payload: Any, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = int(status_code)

        def get_json(self) -> Any:
            return self._payload

    def jsonify(payload: Any) -> _MiniResponse:
        return _MiniResponse(payload, 200)

    class _MiniRequest:
        def __init__(self) -> None:
            self.args: dict[str, Any] = {}
            self._json: Any = None

        def get_json(self, silent: bool = False) -> Any:
            _ = silent
            return self._json

    request = _MiniRequest()

    class Flask:  # type: ignore[misc]
        def __init__(self, _name: str) -> None:
            self._routes: dict[tuple[str, str], Any] = {}

        def get(self, path: str):
            def _deco(fn):
                self._routes[("GET", str(path))] = fn
                return fn

            return _deco

        def post(self, path: str):
            def _deco(fn):
                self._routes[("POST", str(path))] = fn
                return fn

            return _deco

        def test_client(self):
            app = self

            class _Client:
                def _call(self, method: str, path: str, json_payload: Any = None) -> _MiniResponse:
                    pure_path, _, query = str(path).partition("?")
                    handler = app._routes.get((method.upper(), pure_path))
                    if handler is None:
                        return _MiniResponse({"ok": False, "reason": "not_found"}, 404)
                    request.args = {k: v[-1] for k, v in parse_qs(query).items()} if query else {}
                    request._json = json_payload
                    result = handler()
                    if isinstance(result, tuple):
                        resp, code = result
                        payload = resp.get_json() if hasattr(resp, "get_json") else resp
                        return _MiniResponse(payload, int(code))
                    if hasattr(result, "get_json"):
                        return _MiniResponse(result.get_json(), getattr(result, "status_code", 200))
                    return _MiniResponse(result, 200)

                def get(self, path: str):
                    return self._call("GET", path)

                def post(self, path: str, json: Any | None = None):
                    return self._call("POST", path, json_payload=json)

            return _Client()

        def run(self, host: str, port: int, debug: bool = False, use_reloader: bool = False) -> None:
            _ = debug, use_reloader
            from wsgiref.simple_server import make_server

            def app(environ, start_response):
                method = str(environ.get("REQUEST_METHOD", "GET")).upper()
                path = str(environ.get("PATH_INFO", "/"))
                qs = str(environ.get("QUERY_STRING", "") or "")
                handler = self._routes.get((method, path))
                if handler is None:
                    payload = json.dumps({"ok": False, "reason": "not_found"}).encode("utf-8")
                    start_response("404 Not Found", [("Content-Type", "application/json")])
                    return [payload]
                request.args = {k: v[-1] for k, v in parse_qs(qs).items()} if qs else {}
                if method == "POST":
                    try:
                        length = int(environ.get("CONTENT_LENGTH", "0") or "0")
                    except Exception:
                        length = 0
                    raw = environ.get("wsgi.input").read(length) if length > 0 else b""
                    try:
                        request._json = json.loads(raw.decode("utf-8")) if raw else None
                    except Exception:
                        request._json = None
                else:
                    request._json = None
                result = handler()
                status = 200
                body: Any = result
                if isinstance(result, tuple):
                    body, status = result
                if hasattr(body, "get_json"):
                    body = body.get_json()
                payload = json.dumps(body).encode("utf-8")
                start_response(f"{int(status)} OK", [("Content-Type", "application/json")])
                return [payload]

            srv = make_server(str(host), int(port), app)
            srv.serve_forever()


LIVE_SAFE_MUTABLE_KEYS = {
    "AUTONOMOUS_SYMBOL_TOPK",
    "AUTONOMOUS_SYMBOL_SCORE_REFRESH_S",
    "AUTONOMOUS_PROBE_NOTIONAL_QUOTE",
    "AUTONOMOUS_PROBE_DISTANCE_TICKS",
    "AUTONOMOUS_ENTRY_LADDER_STEPS",
    "AUTONOMOUS_ENTRY_LADDER_MAX_BPS",
    "AUTONOMOUS_EXIT_REPRICE_INTERVAL_S",
    "AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN",
    "AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _tail_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines[-max(1, int(limit)) :]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _extract_env_override(payload: dict[str, Any]) -> dict[str, Any]:
    env_map = payload.get("env")
    if isinstance(env_map, dict):
        return {str(k): v for k, v in env_map.items()}
    flat = {}
    for k, v in payload.items():
        if isinstance(k, str) and k.startswith("AUTONOMOUS_"):
            flat[k] = v
    return flat


def create_dashboard_app(
    *,
    run_dir: str,
    config_path: str,
    live_mode: bool,
    override_path: str | None = None,
) -> Flask:
    app = Flask(__name__)
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(config_path)
    ovr_path = Path(override_path) if override_path else (run_path / "override.yaml")

    def _store() -> SQLiteStore:
        return SQLiteStore(str(run_path))

    @app.get("/health")
    def health() -> Any:
        st = _store().health()
        st.update(
            {
                "ok": True,
                "ts": _now_iso(),
                "dashboard_enabled": True,
                "framework": "flask" if _HAS_FLASK else "mini",
                "run_dir": str(run_path),
                "config_path": str(cfg_path),
                "override_path": str(ovr_path),
            }
        )
        return jsonify(st)

    @app.get("/status")
    def status() -> Any:
        runtime = _read_json(run_path / "runtime_health.json", {})
        watchdog = _read_json(run_path / "watchdog_state.json", {})
        snapshot = _read_json(run_path / "dashboard_snapshot.json", {})
        return jsonify(
            {
                "ts": _now_iso(),
                "runtime_health": runtime,
                "watchdog": watchdog,
                "dashboard_snapshot": snapshot,
                "modules": {
                    "ws_integrity": runtime.get("ws_integrity", {}),
                    "rate_limit_governor": runtime.get("rate_limit", {}),
                    "stuck_governor": runtime.get("stuck", {}),
                    "hedge_manager": runtime.get("hedge", {}),
                    "capital_unlock": runtime.get("capital_unlock", {}),
                    "exit_order_manager": runtime.get("exit_manager", {}),
                },
            }
        )

    @app.get("/positions")
    def positions() -> Any:
        store = _store()
        rows = store.latest_positions(limit=200)
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            sym = str(r.get("symbol", "") or "")
            if sym and sym not in latest:
                latest[sym] = r
        return jsonify({"positions": list(latest.values()), "count": len(latest)})

    @app.get("/pnl")
    def pnl() -> Any:
        store = _store()
        with store.session() as s:
            rows = s.execute(
                __import__("sqlalchemy").text(
                    "SELECT ts, symbol, realized_quote, unrealized_quote, fees_quote FROM pnl ORDER BY id DESC LIMIT :lim"
                ),
                {"lim": 500},
            ).mappings().all()
        return jsonify({"rows": [dict(r) for r in rows]})

    @app.get("/metrics")
    def metrics() -> Any:
        snap = _read_json(run_path / "dashboard_snapshot.json", {})
        return jsonify(snap)

    @app.get("/audit-events")
    def audit_events() -> Any:
        try:
            limit = max(1, int(request.args.get("limit", "200")))
        except Exception:
            limit = 200
        rows = _tail_jsonl(run_path / "audit.log", limit=limit)
        return jsonify({"rows": rows, "count": len(rows)})

    @app.get("/slippage")
    def slippage() -> Any:
        events = _tail_jsonl(run_path / "audit.log", limit=1000)
        calib = [e for e in events if e.get("event_type") in {"slippage_calibration", "heartbeat"}]
        return jsonify({"events": calib[-120:]})

    @app.get("/config")
    def get_config() -> Any:
        base_cfg = _load_yaml_like(str(cfg_path)) if cfg_path.exists() else {}
        ovr_cfg: dict[str, Any] = {}
        if ovr_path.exists():
            try:
                raw = yaml.safe_load(ovr_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    ovr_cfg = raw
            except Exception:
                ovr_cfg = {}
        effective = _deep_merge(base_cfg if isinstance(base_cfg, dict) else {}, ovr_cfg)
        return jsonify(
            {
                "base": base_cfg,
                "override": ovr_cfg,
                "effective": effective,
                "live_mode": bool(live_mode),
                "mutable_keys_live": sorted(LIVE_SAFE_MUTABLE_KEYS),
            }
        )

    @app.get("/ui")
    def config_ui() -> Any:
        html = (
            "<html><body><h2>Autonomous Dashboard Config</h2>"
            "<p>Safe runtime overrides (applied on restart/reload marker).</p>"
            "<form method='post' action='/config'>"
            "<label>topK:</label><input name='AUTONOMOUS_SYMBOL_TOPK' /><br/>"
            "<label>ladder steps:</label><input name='AUTONOMOUS_ENTRY_LADDER_STEPS' /><br/>"
            "<label>slippage bps:</label><input name='AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS' /><br/>"
            "<label>churn budget:</label><input name='AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN' /><br/>"
            "<p>POST JSON to /config for authoritative updates.</p>"
            "</form>"
            "</body></html>"
        )
        if _HAS_FLASK:
            # Flask path
            from flask import Response  # type: ignore

            return Response(html, mimetype="text/html")
        return _MiniResponse({"html": html}, 200)  # type: ignore[name-defined]

    @app.post("/config")
    def update_config() -> Any:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "reason": "invalid_payload"}), 400
        updates = _extract_env_override(payload)
        if not updates:
            return jsonify({"ok": False, "reason": "no_updates"}), 400

        blocked: list[str] = []
        if live_mode:
            for key in list(updates.keys()):
                if key not in LIVE_SAFE_MUTABLE_KEYS:
                    blocked.append(key)
                    updates.pop(key, None)
        if blocked and not updates:
            return jsonify({"ok": False, "reason": "live_mode_keys_blocked", "blocked": blocked}), 403

        existing: dict[str, Any] = {}
        if ovr_path.exists():
            try:
                raw = yaml.safe_load(ovr_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    existing = raw
            except Exception:
                existing = {}

        merged = dict(existing)
        merged.setdefault("env", {})
        if not isinstance(merged["env"], dict):
            merged["env"] = {}
        merged["env"].update(updates)
        ovr_path.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")

        _store().record_audit_checkpoint(
            kind="dashboard_config_update",
            payload={"updates": updates, "blocked": blocked, "live_mode": bool(live_mode)},
        )
        return jsonify(
            {
                "ok": True,
                "updates": updates,
                "blocked": blocked,
                "override_path": str(ovr_path),
                "apply_mode": "on_restart_or_reload",
            }
        )

    @app.post("/reload")
    def request_reload() -> Any:
        marker = run_path / "reload.request.json"
        marker.write_text(json.dumps({"ts": _now_iso(), "source": "dashboard"}, sort_keys=True), encoding="utf-8")
        return jsonify({"ok": True, "reload_marker": str(marker), "note": "restart worker to apply overrides"})

    return app
