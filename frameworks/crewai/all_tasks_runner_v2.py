from __future__ import annotations

import argparse
import json

from runner.shared_experiment_v2 import (
    run_shared_experiment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a benchmark_v2 workflow "
            "with CrewAI."
        )
    )

    parser.add_argument(
        "--task",
        required=True,
        help=(
            "Path to a benchmark_v2 "
            "workflow JSON file."
        ),
    )

    parser.add_argument(
        "--configuration",
        choices=["native", "teaoa"],
        required=True,
    )

    parser.add_argument(
        "--repeat",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--model",
        required=True,
    )

    parser.add_argument(
        "--temperature",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate configuration without "
            "calling an API."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = run_shared_experiment(
        framework="crewai",
        task=args.task,
        configuration=args.configuration,
        repeat=args.repeat,
        model=args.model,
        temperature=args.temperature,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2))

    print(
        "CREWAI SHARED V2 RUNNER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()