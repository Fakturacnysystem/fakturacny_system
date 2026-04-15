#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.services.runtime_api import (  # noqa: E402
    RuntimeApiError,
    RuntimeApiService,
    RuntimeApiServiceConfig,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--artifact-stale-after-seconds", type=int, default=300)
    return parser


def _json_error(status: int, code: str, detail: str) -> tuple[int, dict[str, str]]:
    return status, {"error": code, "detail": detail}


class RuntimeApiHandler(BaseHTTPRequestHandler):
    service: RuntimeApiService

    server_version = "RobotControlCenterRuntimeApi/0.1"

    def _allow_origin(self) -> str:
        origin = self.headers.get("Origin", "").strip()
        if origin:
            return origin
        return "http://127.0.0.1:3000"

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self._allow_origin())
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeApiError(f"invalid_json:{exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeApiError("invalid_json:object_required")
        return payload

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", self._allow_origin())
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/runtime/summary":
                self._send_json(HTTPStatus.OK, self.service.summary())
                return
            if path == "/runtime/runs":
                self._send_json(HTTPStatus.OK, self.service.runs())
                return
            if path == "/runtime/symbols":
                self._send_json(HTTPStatus.OK, self.service.symbols())
                return
            if path == "/runtime/decisions":
                self._send_json(HTTPStatus.OK, self.service.decisions())
                return
            if path == "/runtime/alerts":
                self._send_json(HTTPStatus.OK, self.service.alerts())
                return
            if path == "/runtime/health":
                self._send_json(HTTPStatus.OK, self.service.health())
                return
            if path == "/runtime/integrity":
                self._send_json(HTTPStatus.OK, self.service.integrity())
                return
            if path == "/runtime/brain":
                self._send_json(HTTPStatus.OK, self.service.brain())
                return
            if path == "/runtime/shield":
                self._send_json(HTTPStatus.OK, self.service.shield())
                return
            if path == "/runtime/execution":
                self._send_json(HTTPStatus.OK, self.service.execution())
                return
            if path.startswith("/runtime/replay/"):
                run_id = path.split("/runtime/replay/", 1)[1]
                self._send_json(HTTPStatus.OK, self.service.replay(run_id))
                return
            self._send_json(*_json_error(HTTPStatus.NOT_FOUND, "not_found", f"Unknown path: {path}"))
        except RuntimeApiError as exc:
            detail = str(exc)
            if detail.startswith("run_not_found:"):
                self._send_json(HTTPStatus.NOT_FOUND, self.service.unresolved_selection_payload(detail))
                return
            self._send_json(*_json_error(HTTPStatus.BAD_REQUEST, "runtime_api_error", detail))
        except Exception as exc:  # pragma: no cover - defensive server guard.
            self._send_json(*_json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc)))

    def do_POST(self) -> None:  # noqa: N802
        payload: dict[str, object] = {}
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            payload = self._read_json_body()
            authorization_header = self.headers.get("Authorization")
            if path.startswith("/runtime/control/"):
                action = path.split("/runtime/control/", 1)[1]
                self._send_json(
                    HTTPStatus.OK,
                    self.service.control(action, payload, authorization_header),
                )
                return
            if path == "/runtime/select-run":
                self._send_json(
                    HTTPStatus.OK,
                    self.service.select_run(payload),
                )
                return
            if path == "/runtime/incident-note":
                self._send_json(
                    HTTPStatus.OK,
                    self.service.write_incident_note(payload, authorization_header),
                )
                return
            self._send_json(*_json_error(HTTPStatus.NOT_FOUND, "not_found", f"Unknown path: {path}"))
        except RuntimeApiError as exc:
            detail = str(exc)
            if detail == "operator_identity_required":
                self._send_json(
                    *_json_error(
                        HTTPStatus.UNAUTHORIZED,
                        "operator_identity_required",
                        "Authenticated operator identity is required.",
                    )
                )
                return
            if detail.startswith("run_not_found:"):
                self._send_json(HTTPStatus.NOT_FOUND, self.service.unresolved_selection_payload(detail, payload))
                return
            self._send_json(*_json_error(HTTPStatus.BAD_REQUEST, "runtime_api_error", detail))
        except Exception as exc:  # pragma: no cover - defensive server guard.
            self._send_json(*_json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc)))

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        sys.stderr.write(f"[runtime-api] {self.address_string()} - {fmt % args}\n")


def main() -> int:
    args = build_parser().parse_args()
    run_dir_value = (
        args.run_dir.strip()
        or os.environ.get("RUNTIME_API_RUN_DIR", "").strip()
        or os.environ.get("RCC_RUNTIME_RUN_DIR", "").strip()
    )
    run_id_value = (
        args.run_id.strip()
        or os.environ.get("RUNTIME_API_RUN_ID", "").strip()
        or os.environ.get("RCC_RUNTIME_RUN_ID", "").strip()
    )
    if run_dir_value and run_id_value:
        raise SystemExit("runtime_api_run_selection_conflict: set run-dir or run-id, not both")
    config = RuntimeApiServiceConfig(
        repo_root=REPO,
        run_dir=Path(run_dir_value).expanduser().resolve() if run_dir_value else None,
        run_id=run_id_value or None,
        artifact_stale_after_seconds=args.artifact_stale_after_seconds,
    )
    service = RuntimeApiService(config)
    RuntimeApiHandler.service = service
    server = ThreadingHTTPServer((args.host, args.port), RuntimeApiHandler)
    print(
        json.dumps(
            {
                "status": "listening",
                "host": args.host,
                "port": args.port,
                "run_dir": str(config.resolve_run_dir()),
                "run_selection_mode": config.selection_mode(),
                "run_resolution_source": config.resolution_source(),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
