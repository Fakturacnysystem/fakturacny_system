from __future__ import annotations

try:
    from flask import Flask, Response, render_template_string
except Exception:  # pragma: no cover - optional sidecar dependency
    class Response:  # type: ignore[override]
        def __init__(self, body: str, status: int = 200, mimetype: str = "text/plain") -> None:
            self.data = body.encode("utf-8")
            self.status_code = status
            self.mimetype = mimetype

    def render_template_string(template: str, **kwargs) -> str:  # type: ignore[override]
        return template.format(**kwargs)

    class _FallbackTestClient:
        def __init__(self, routes: dict[str, object]) -> None:
            self._routes = routes

        def get(self, path: str) -> Response:
            handler = self._routes[path]
            result = handler()
            if isinstance(result, Response):
                return result
            return Response(str(result), status=200, mimetype="text/html")

    class Flask:  # type: ignore[override]
        def __init__(self, name: str) -> None:  # noqa: ARG002
            self._routes: dict[str, object] = {}

        def route(self, path: str):
            def _decorator(fn):
                self._routes[path] = fn
                return fn

            return _decorator

        def test_client(self) -> _FallbackTestClient:
            return _FallbackTestClient(self._routes)

try:
    from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotConnectorError
except ModuleNotFoundError:  # pragma: no cover - legacy root-script fallback
    from src.autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotConnectorError

app = Flask(__name__) if Flask is not None else None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Kraken HFT Terminal</title>
    <meta http-equiv="refresh" content="15">
    <style>
        body { background: #050505; color: #00ff41; font-family: 'Courier New', monospace; text-align: center; padding: 20px; }
        .box { border: 2px solid #00ff41; padding: 20px; border-radius: 15px; background: #0a0a0a; box-shadow: 0 0 15px #00ff41; margin-bottom: 20px;}
        .stat { font-size: 2.5em; margin: 10px 0; color: #fff; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .small-box { border: 1px solid #333; padding: 10px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Kraken Monitor</h1>
        <p style="color: #888;">TOTAL PORTFOLIO VALUE (ESTIMATED)</p>
        <div class="stat">{{ total_equity }} EUR</div>
        <p>AVAILABLE CASH: {{ cash }} EUR</p>
        <hr color="#222">
        <div class="grid">
            <div class="small-box">BTC: {{ btc }}</div>
            <div class="small-box">ETH: {{ eth }}</div>
            <div class="small-box">SOL: {{ sol }}</div>
            <div class="small-box">ATOM: {{ atom }}</div>
        </div>
    </div>
</body>
</html>
"""


def _build_connector() -> KrakenSpotConnector:
    return KrakenSpotConnector()


def index() -> Response | str:
    try:
        if app is None:
            return "Kraken API unavailable: dashboard_dependency_missing"
        kraken = _build_connector()
        rows = kraken.balances()
        totals = {str(row.get("asset", "")): float(row.get("balance", 0.0) or 0.0) for row in rows}
        cash = totals.get("EUR", totals.get("ZEUR", 0))
        btc = totals.get("BTC", totals.get("XXBT", 0))
        eth = totals.get("ETH", totals.get("XETH", 0))
        sol = totals.get("SOL", 0)
        atom = totals.get("ATOM", 0)
        return render_template_string(
            HTML_TEMPLATE,
            total_equity=round(cash + (sol * 110) + (eth * 2200) + (btc * 70000), 2),
            cash=round(cash, 2),
            btc=btc,
            eth=eth,
            sol=sol,
            atom=atom,
        )
    except KrakenSpotConnectorError as exc:
        return Response(f"Kraken API unavailable: {exc}", status=503, mimetype="text/plain")
    except Exception:
        return Response("Kraken API unavailable: balance_fetch_failed", status=503, mimetype="text/plain")


if __name__ == "__main__":
    if app is None:
        raise SystemExit("flask_dependency_missing")
    app.run(port=5001, host="0.0.0.0")


if app is not None:
    app.route("/")(index)
