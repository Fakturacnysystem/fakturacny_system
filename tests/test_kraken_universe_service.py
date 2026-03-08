from __future__ import annotations

from autonomous_investment_robot.services.universe import KrakenUniverseConfig, KrakenUniverseService


class _FakeConnector:
    def asset_pairs(self):
        return {
            "XBTEUR": {"altname": "XBTEUR", "base": "XXBT", "quote": "ZEUR", "status": "online"},
            "ETHEUR": {"altname": "ETHEUR", "base": "XETH", "quote": "ZEUR", "status": "online"},
            "SOLEUR": {"altname": "SOLEUR", "base": "SOL", "quote": "ZEUR", "status": "online"},
            "XBTUSDT": {"altname": "XBTUSDT", "base": "XXBT", "quote": "USDT", "status": "online"},
            "TSLAXUSD": {"altname": "TSLAXUSD", "wsname": "TSLAx/USD", "base": "TSLAx", "quote": "USD", "status": "online"},
        }

    def ticker(self, pair=None):  # noqa: ARG002
        return {
            "XBTEUR": {"a": ["60010.0"], "b": ["60000.0"], "v": ["0", "50"]},
            "ETHEUR": {"a": ["2000.2"], "b": ["2000.0"], "v": ["0", "600"]},
            "SOLEUR": {"a": ["150.05"], "b": ["150.0"], "v": ["0", "9000"]},
            "XBTUSDT": {"a": ["60010.0"], "b": ["60000.0"], "v": ["0", "999"]},
            "TSLAXUSD": {"a": ["180.10"], "b": ["180.0"], "v": ["0", "15000"]},
        }


def test_auto_top_filters_quote_and_denylist_and_rotates(tmp_path):
    cfg = KrakenUniverseConfig(
        mode="kraken_spot_auto_top",
        max_pairs=2,
        rotate_every_s=60.0,
        quote_allowlist=["EUR", "ZEUR", "USD", "ZUSD"],
        denylist_tokens=["USDT", "USDC", "DAI"],
        min_24h_vol_quote=100_000.0,
        max_spread_bps=50.0,
        cache_ttl_s=1800.0,
    )
    svc = KrakenUniverseService(run_dir=str(tmp_path), connector=_FakeConnector(), config=cfg)
    svc.refresh_if_needed(now_ts=0.0, force=True)

    first = svc.select_active(now_ts=0.0)
    second = svc.select_active(now_ts=61.0)
    assert "XBTUSDT" not in first
    assert "XBTUSDT" not in second
    assert len(first) == 2
    assert len(second) == 2
    assert first != second


def test_auto_all_returns_all_filtered_symbols(tmp_path):
    cfg = KrakenUniverseConfig(
        mode="kraken_spot_auto_all",
        max_pairs=10,
        rotate_every_s=60.0,
        quote_allowlist=["EUR", "ZEUR"],
        denylist_tokens=["USDT"],
        min_24h_vol_quote=0.0,
        max_spread_bps=200.0,
        cache_ttl_s=1800.0,
    )
    svc = KrakenUniverseService(run_dir=str(tmp_path), connector=_FakeConnector(), config=cfg)
    symbols = svc.select_active(now_ts=0.0)
    assert "XBTEUR" in symbols
    assert "ETHEUR" in symbols
    assert "SOLEUR" in symbols
    assert "XBTUSDT" not in symbols


def test_universe_xstocks_allowlist_and_classification(tmp_path):
    cfg = KrakenUniverseConfig(
        mode="kraken_spot_auto_all",
        max_pairs=20,
        rotate_every_s=60.0,
        quote_allowlist=["USD", "EUR", "ZEUR"],
        denylist_tokens=["USDT"],
        min_24h_vol_quote=0.0,
        max_spread_bps=200.0,
        cache_ttl_s=1800.0,
        enable_crypto_spot=True,
        enable_xstocks=True,
        enable_xstocks_etf=False,
        xstocks_allowlist=["TSLAXUSD"],
        xstocks_denylist=[],
        mixed_universe_mode=True,
    )
    svc = KrakenUniverseService(run_dir=str(tmp_path), connector=_FakeConnector(), config=cfg)
    symbols = svc.select_active(now_ts=0.0)
    assert "TSLAXUSD" in symbols
    diag = svc.diagnostics_snapshot()
    assert diag.get("eligible_market_class_counts", {}).get("xstock", 0) >= 1
