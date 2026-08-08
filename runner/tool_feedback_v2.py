from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPLAY_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "paid_smoke_pipeline_replay.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "paid_smoke_tool_feedback.json"
)

FORBIDDEN_FEEDBACK_FIELDS = {
    "ground_truth",
    "required_steps",
    "expected_outcome",
    "expected_final_status",
    "expected_policy_decision",
    "expected_security_decision",
    "scoring_rules",
    "maximum_score",
    "score",
}


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_value(item)
            for key, item in value.items()
            if key not in FORBIDDEN_FEEDBACK_FIELDS
        }

    if isinstance(value, list):
        return [
            sanitize_value(item)
            for item in value
        ]

    return value


def find_forbidden_fields(
    value: Any,
    path: str = "feedback",
) -> list[str]:
    found = []

    if isinstance(value, dict):
        for key, item in value.items():
            current_path = f"{path}.{key}"

            if key in FORBIDDEN_FEEDBACK_FIELDS:
                found.append(current_path)

            found.extend(
                find_forbidden_fields(
                    item,
                    current_path,
                )
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(
                find_forbidden_fields(
                    item,
                    f"{path}[{index}]",
                )
            )

    return found


def build_tool_feedback(
    replay: dict[str, Any],
) -> dict[str, Any]:
    raw_tool_results = replay.get(
        "tool_results",
        [],
    )

    sanitized_results = sanitize_value(
        raw_tool_results
    )

    feedback = {
        "workflow_id": replay["workflow_id"],
        "source": "simulated_enterprise_tools",
        "tool_execution_count": len(
            sanitized_results
        ),
        "tool_results": sanitized_results,
        "instruction": (
            "Continue the workflow using these simulated "
            "tool results. Do not claim that any other tool "
            "was executed. Propose the next required tool, "
            "or return a completed final answer only if the "
            "workflow is genuinely complete."
        ),
    }

    leaked_fields = find_forbidden_fields(feedback)

    if leaked_fields:
        raise ValueError(
            "Forbidden benchmark fields found in tool "
            "feedback: "
            + ", ".join(leaked_fields)
        )

    return feedback


def load_replay() -> dict[str, Any]:
    if not REPLAY_PATH.is_file():
        raise FileNotFoundError(
            f"Replay result not found: {REPLAY_PATH}"
        )

    with REPLAY_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build leakage-safe model feedback from "
            "simulated tool results."
        )
    )

    parser.add_argument(
        "--build",
        action="store_true",
        help="Build feedback without calling a model.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.build:
        raise RuntimeError(
            "Use --build. No API execution is available."
        )

    replay = load_replay()
    feedback = build_tool_feedback(replay)

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
        "TOOL FEEDBACK PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()