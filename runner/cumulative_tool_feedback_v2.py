from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runner.tool_feedback_v2 import (
    find_forbidden_fields,
    sanitize_value,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPLAY_PATHS = [
    (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / "paid_smoke_pipeline_replay.json"
    ),
    (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / "second_turn_pipeline_replay.json"
    ),
]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "cumulative_tool_feedback.json"
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required replay not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def build_cumulative_feedback() -> dict[str, Any]:
    combined_results = []

    for turn_number, replay_path in enumerate(
        REPLAY_PATHS,
        start=1,
    ):
        replay = load_json(replay_path)

        for result in replay.get(
            "tool_results",
            [],
        ):
            combined_results.append(
                {
                    "turn_number": turn_number,
                    "execution_result": result,
                }
            )

    sanitized_results = sanitize_value(
        combined_results
    )

    feedback = {
        "workflow_id": "CS-001",
        "source": "simulated_enterprise_tools",
        "completed_model_turns": len(REPLAY_PATHS),
        "tool_execution_count": len(
            sanitized_results
        ),
        "execution_history": sanitized_results,
        "instruction": (
            "Continue from this cumulative execution "
            "history. Do not repeat completed tool calls. "
            "Propose only the next required tool. Return "
            "a completed final answer only when the entire "
            "workflow is genuinely complete."
        ),
    }

    leaked_fields = find_forbidden_fields(
        feedback
    )

    if leaked_fields:
        raise ValueError(
            "Ground-truth leakage detected: "
            + ", ".join(leaked_fields)
        )

    return feedback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build cumulative leakage-safe feedback "
            "from two local tool executions."
        )
    )

    parser.add_argument(
        "--build",
        action="store_true",
        help="Build feedback without an API call.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.build:
        raise RuntimeError(
            "Use --build. API execution is unavailable."
        )

    feedback = build_cumulative_feedback()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(feedback, file, indent=2)

    print(json.dumps(feedback, indent=2))
    print(f"Report: {OUTPUT_PATH}")
    print(
        "CUMULATIVE TOOL FEEDBACK PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()