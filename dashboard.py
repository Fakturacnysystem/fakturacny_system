from __future__ import annotations

from flask import Flask, Response, render_template_string

try:
    from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotConnectorError
except ModuleNotFoundError:  # pragma: no cover - legacy root-script fallback
    from src.autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotConnectorError

app = Flask(__name__)

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


@app.route("/")
def index() -> Response | str:
    try:
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
    app.run(port=5001, host="0.0.0.0")
