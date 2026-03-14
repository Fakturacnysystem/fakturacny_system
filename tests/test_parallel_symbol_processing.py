from __future__ import annotations

from autonomous_investment_robot.services.distributed.compute_bridge import LocalComputeBridge


def test_local_compute_bridge_parallel_workers(monkeypatch: object) -> None:
    monkeypatch.setenv("AUTONOMOUS_PARALLEL_SYMBOL_WORKERS", "3")
    bridge = LocalComputeBridge()
    symbols = ["XXBTZUSD", "XETHZUSD", "SOLUSD", "ADAUSD", "TSLAxUSD", "NVDAxUSD"]
    response = bridge.request_rankings(
        run_id="run-parallel",
        symbols=symbols,
        market_class_by_symbol={
            "XXBTZUSD": "crypto_spot",
            "XETHZUSD": "crypto_spot",
            "SOLUSD": "crypto_spot",
            "ADAUSD": "crypto_spot",
            "TSLAxUSD": "xstock",
            "NVDAxUSD": "xstock",
        },
        top_n=4,
        timeout_s=0.5,
    )
    assert response.ok is True
    assert int(response.diagnostics.get("parallel_workers_used", 1)) == 3
    assert set(response.rankings.keys()) == set(symbols)
