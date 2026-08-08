from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "turn_limit_analysis.json"
)


def to_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    manifest = load_manifest()

    enabled_rows = [
        row
        for row in manifest
        if row.get(
            "enabled",
            "",
        ).strip().lower() == "true"
    ]

    results = []

    for row in enabled_rows:
        workflow_id = row["workflow_id"]
        scenario = load_scenario(workflow_id)
        ground_truth = scenario["ground_truth"]

        allowed_tool_count = len(
            ground_truth.get(
                "allowed_tools",
                [],
            )
        )

        required_step_count = len(
            ground_truth.get(
                "required_steps",
                [],
            )
        )

        minimum_steps = to_int(
            ground_truth.get(
                "minimum_steps",
                row.get("minimum_steps", 0),
            )
        )

        recommended_turn_limit = max(
            allowed_tool_count + 2,
            required_step_count + 1,
            minimum_steps + 3,
        )

        results.append(
            {
                "workflow_id": workflow_id,
                "allowed_tool_count": (
                    allowed_tool_count
                ),
                "required_step_count": (
                    required_step_count
                ),
                "minimum_steps": minimum_steps,
                "recommended_turn_limit": (
                    recommended_turn_limit
                ),
            }
        )

    maximum_recommended_limit = max(
        item["recommended_turn_limit"]
        for item in results
    )

    report = {
        "workflow_count": len(results),
        "minimum_recommended_limit": min(
            item["recommended_turn_limit"]
            for item in results
        ),
        "maximum_recommended_limit": (
            maximum_recommended_limit
        ),
        "average_recommended_limit": round(
            mean(
                item["recommended_turn_limit"]
                for item in results
            ),
            2,
        ),
        "suggested_global_safety_cap": (
            maximum_recommended_limit + 2
        ),
        "api_calls_performed": False,
        "workflows": results,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(report, file, indent=2)

    print(
        f"Enabled workflows: "
        f"{report['workflow_count']}"
    )

    print(
        f"Minimum recommended limit: "
        f"{report['minimum_recommended_limit']}"
    )

    print(
        f"Maximum recommended limit: "
        f"{report['maximum_recommended_limit']}"
    )

    print(
        f"Average recommended limit: "
        f"{report['average_recommended_limit']}"
    )

    print(
        f"Suggested global safety cap: "
        f"{report['suggested_global_safety_cap']}"
    )

    print(f"Report: {OUTPUT_PATH}")
    print(
        "TURN LIMIT ANALYSIS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()