from __future__ import annotations

import json

from autonomous_investment_robot.services.market_discovery import KrakenMarketDiscoveryService


class _FakeSpotConnector:
    def asset_pairs(self) -> dict:
        return {
            "ETHEUR": {
                "status": "online",
                "pair_decimals": 2,
                "lot_decimals": 6,
                "ordermin": "0.001",
                "costmin": "5.0",
                "leverage_buy": [2, 3],
                "leverage_sell": [2, 3],
                "base": "XETH",
                "quote": "ZEUR",
            },
            "XBTEUR": {
                "status": "online",
                "pair_decimals": 1,
                "lot_decimals": 8,
                "ordermin": "0.0001",
                "costmin": "10.0",
                "leverage_buy": [],
                "leverage_sell": [],
                "base": "XXBT",
                "quote": "ZEUR",
            },
            "BADPAIR.d": {
                "status": "online",
                "pair_decimals": 2,
                "lot_decimals": 6,
            },
        }

    def ticker(self) -> dict:
        return {
            "ETHEUR": {"b": ["1700.0"], "a": ["1701.0"]},
            "XBTEUR": {"b": ["58000.0"], "a": ["58001.0"]},
        }


class _FakeFuturesConnector:
    def instruments(self) -> dict:
        return {
            "instruments": [
                {
                    "symbol": "PF_XBTUSD",
                    "type": "perpetual",
                    "status": "online",
                    "tickSize": 0.5,
                    "contractSize": 1.0,
                    "underlying": "XBT",
                    "quote": "USD",
                },
                {
                    "symbol": "PF_XSTOCK_NVDAUSD",
                    "type": "perpetual",
                    "status": "online",
                    "tickSize": 0.01,
                    "contractSize": 1.0,
                    "underlying": "NVDA",
                    "quote": "USD",
                    "category": "xstocks",
                },
                {
                    "symbol": "FI_XBTUSD_240628",
                    "type": "futures",
                    "status": "online",
                },
            ]
        }


def test_market_discovery_collects_and_persists(tmp_path) -> None:
    svc = KrakenMarketDiscoveryService(str(tmp_path))
    result = svc.discover(
        spot_connector=_FakeSpotConnector(),
        futures_connector=_FakeFuturesConnector(),
        enable_spot=True,
        enable_margin=True,
        enable_perps=True,
        enable_optional_venues=True,
    )

    assert "ETHEUR" in result.spot_symbols
    assert "XBTEUR" in result.spot_symbols
    assert "ETHEUR" in result.margin_symbols
    assert "XBTEUR" not in result.margin_symbols
    assert "PF_XBTUSD" in result.perp_symbols
    assert "PF_XSTOCK_NVDAUSD" in result.perp_symbols
    assert "PF_XSTOCK_NVDAUSD" in result.optional_symbols
    assert "PF_XSTOCK_NVDAUSD" in result.xstocks_symbols
    assert result.market_class_counts.get("xstock_perp", 0) >= 1
    assert "FI_XBTUSD_240628" not in result.perp_symbols
    assert result.errors == []

    snapshot_path = tmp_path / "market_discovery.json"
    assert snapshot_path.exists()
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert "ETHEUR" in payload.get("spot_symbols", [])
    assert "PF_XBTUSD" in payload.get("perp_symbols", [])
    assert "PF_XSTOCK_NVDAUSD" in payload.get("xstocks_symbols", [])
