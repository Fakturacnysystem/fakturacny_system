from __future__ import annotations

import json

import pytest

from autonomous_investment_robot.universe_gateway.app import create_universe_gateway_app


@pytest.fixture()
def gateway_app(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runtime_health.json").write_text(
        json.dumps({"status": "running", "mode": "Canary", "version": "1.2.3", "uptime": 123.0}),
        encoding="utf-8",
    )
    return create_universe_gateway_app(
        run_dir=str(run_dir),
        redis_url="",
        postgres_dsn=f"sqlite:///{tmp_path / 'gateway.db'}",
        jwt_secret="test-secret",
    )


def _token(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/token", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_and_compatibility_parity(gateway_app) -> None:
    from fastapi.testclient import TestClient

    with TestClient(gateway_app) as client:
        admin = _token(client, "admin", "universe-admin")

        unauthorized = client.get("/api/system/status")
        assert unauthorized.status_code == 401

        legacy = client.get("/status")
        modern = client.get("/api/system/status", headers=_headers(admin))

        assert legacy.status_code == 200
        assert modern.status_code == 200
        assert modern.json()["mode"] == legacy.json()["runtime_health"]["mode"]


def test_rbac_matrix_for_execution_endpoint(gateway_app) -> None:
    from fastapi.testclient import TestClient

    with TestClient(gateway_app) as client:
        admin = _token(client, "admin", "universe-admin")

        create_observer = client.post(
            "/api/auth/users",
            headers=_headers(admin),
            json={"username": "obs", "password": "pw1", "role": "observer"},
        )
        assert create_observer.status_code == 200, create_observer.text

        create_operator = client.post(
            "/api/auth/users",
            headers=_headers(admin),
            json={"username": "op", "password": "pw2", "role": "operator"},
        )
        assert create_operator.status_code == 200, create_operator.text

        observer = _token(client, "obs", "pw1")
        operator = _token(client, "op", "pw2")

        denied = client.get("/api/execution/stats", headers=_headers(observer))
        allowed = client.get("/api/execution/stats", headers=_headers(operator))

        assert denied.status_code == 403
        assert allowed.status_code == 200


def test_websocket_rbac_for_execution_channel(gateway_app) -> None:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    with TestClient(gateway_app) as client:
        admin = _token(client, "admin", "universe-admin")
        user_resp = client.post(
            "/api/auth/users",
            headers=_headers(admin),
            json={"username": "wsobs", "password": "pw", "role": "observer"},
        )
        assert user_resp.status_code == 200

        observer = _token(client, "wsobs", "pw")

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws/execution?token={observer}"):
                pass
        assert excinfo.value.code == 4403

        with client.websocket_connect(f"/ws/telemetry?token={observer}") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["channel"] == "telemetry"


def test_ui_renders_command_center(gateway_app) -> None:
    from fastapi.testclient import TestClient

    with TestClient(gateway_app) as client:
        response = client.get("/ui")

    assert response.status_code == 200
    assert "Universe Control Center" in response.text
    assert "Capital Core" in response.text
    assert "/api/auth/token" in response.text
    assert "/ui/manifest.webmanifest" in response.text
    assert "Install Universe App" in response.text


def test_ui_pwa_routes(gateway_app) -> None:
    from fastapi.testclient import TestClient

    with TestClient(gateway_app) as client:
        manifest = client.get("/ui/manifest.webmanifest")
        service_worker = client.get("/ui/sw.js")
        icon = client.get("/ui/assets/icon-192.png")

    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert "Universe Control Center" in manifest.text
    assert service_worker.status_code == 200
    assert service_worker.headers["content-type"].startswith("application/javascript")
    assert "CACHE" in service_worker.text
    assert icon.status_code == 200
