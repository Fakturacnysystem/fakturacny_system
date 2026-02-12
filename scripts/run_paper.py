#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from autonomous_investment_robot.main import run_with_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.paper.yaml")
    args = parser.parse_args()
    result = run_with_config(args.config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
