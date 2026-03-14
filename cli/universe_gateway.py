from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=str(os.getenv("AUTONOMOUS_UNIVERSE_RUN_DIR", "runs/latest") or "runs/latest"))
    p.add_argument("--host", default=str(os.getenv("AUTONOMOUS_UNIVERSE_GATEWAY_HOST", "0.0.0.0") or "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(float(os.getenv("AUTONOMOUS_UNIVERSE_GATEWAY_PORT", "8081") or "8081")))
    p.add_argument("--redis-url", default=str(os.getenv("AUTONOMOUS_REDIS_URL", "") or ""))
    p.add_argument("--postgres-dsn", default=str(os.getenv("AUTONOMOUS_UNIVERSE_POSTGRES_DSN", os.getenv("AUTONOMOUS_POSTGRES_DSN", "")) or ""))
    p.add_argument("--jwt-secret", default=str(os.getenv("AUTONOMOUS_JWT_SECRET", "unsafe-dev-secret") or "unsafe-dev-secret"))
    args = p.parse_args()

    try:
        import uvicorn  # type: ignore
    except Exception as exc:
        print(f"uvicorn_missing:{exc}", file=sys.stderr)
        return 2

    try:
        from autonomous_investment_robot.universe_gateway.app import create_universe_gateway_app

        app = create_universe_gateway_app(
            run_dir=str(args.run_dir),
            redis_url=str(args.redis_url),
            postgres_dsn=str(args.postgres_dsn),
            jwt_secret=str(args.jwt_secret),
        )
    except Exception as exc:
        print(f"gateway_app_init_failed:{exc}", file=sys.stderr)
        return 2

    uvicorn.run(app, host=str(args.host), port=max(1, int(args.port)), log_level=str(os.getenv("AUTONOMOUS_LOG_LEVEL", "info")).lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
