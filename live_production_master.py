from __future__ import annotations


BLOCK_REASON = "kraken_spot_live_sidecar_unsupported_use_launch_gated_runtime"


def run_elite_bot() -> None:
    raise RuntimeError(BLOCK_REASON)


if __name__ == "__main__":
    raise SystemExit(BLOCK_REASON)
