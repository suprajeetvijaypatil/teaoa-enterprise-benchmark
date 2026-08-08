from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import load_scenario
from runner.scorer_v2 import score_trace


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
    }


def correct_terminal_status(
    result: dict[str, Any],
    scenario: dict[str, Any],
) -> str:
    trace = result["trace"]

    workflow = scenario["workflow"]

    workflow_requires_approval = as_bool(
        workflow.get(
            "human_approval_required",
            workflow.get(
                "approval_required",
                False,
            ),
        )
    )

    execution_history = result.get(
        "execution_history",
        [],
    )

    executed_tool_names = {
        str(item.get("tool_name", ""))
        for item in execution_history
    }

    approval_request_created = (
        "create_approval_request"
        in executed_tool_names
    )

    approval_decision_events = {
        event.get("event_type")
        for event in trace.get("events", [])
        if event.get("event_type")
        in {
            "approval_granted",
            "approval_denied",
        }
    }

    if (
        workflow_requires_approval
        and approval_request_created
        and not approval_decision_events
    ):
        return "approval_required"

    timeout_observed = any(
        event.get("event_type")
        == "tool_failed"
        and str(
            event.get(
                "details",
                {},
            ).get("reason", "")
        )
        == "tool_timeout"
        for event in trace.get("events", [])
    )

    recovery_validated = any(
        item.get("tool_name")
        == "validate_recovery"
        and str(
            item.get(
                "result",
                {},
            ).get("status", "")
        )
        in {
            "succeeded",
            "success",
        }
        for item in execution_history
    )

    if (
        timeout_observed
        and recovery_validated
    ):
        return "recovered"

    return str(
        trace.get(
            "final_status",
            "failed",
        )
    )


def resolve_input_path(
    input_value: str,
) -> Path:
    input_path = Path(input_value)

    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    input_path = input_path.resolve()

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Result file not found: {input_path}"
        )

    return input_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Correct and rescore an existing V2 "
            "paid result without an API call."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the original paid result.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = resolve_input_path(
        args.input
    )

    with input_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        original_result = json.load(file)

    corrected_result = deepcopy(
        original_result
    )

    workflow_id = str(
        corrected_result["workflow_id"]
    )

    scenario = load_scenario(
        workflow_id
    )

    old_status = corrected_result[
        "trace"
    ].get("final_status")

    corrected_status = (
        correct_terminal_status(
            result=corrected_result,
            scenario=scenario,
        )
    )

    corrected_result[
        "trace"
    ]["final_status"] = corrected_status

    corrected_result["score"] = score_trace(
        scenario=scenario,
        trace=corrected_result["trace"],
    )

    corrected_result["postprocessing"] = {
        "api_call_made": False,
        "original_result_preserved": True,
        "original_final_status": old_status,
        "corrected_final_status": (
            corrected_status
        ),
        "correction_reason": (
            "Pending human approval was "
            "canonicalized as approval_required."
        ),
    }

    output_path = input_path.with_name(
        input_path.stem
        + "_rescored.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            corrected_result,
            file,
            indent=2,
        )

    summary = {
        "workflow_id": workflow_id,
        "configuration": (
            corrected_result.get(
                "configuration"
            )
        ),
        "original_final_status": old_status,
        "corrected_final_status": (
            corrected_status
        ),
        "score": corrected_result[
            "score"
        ]["score"],
        "maximum_score": corrected_result[
            "score"
        ]["maximum_score"],
        "percentage": corrected_result[
            "score"
        ]["percentage"],
        "api_call_made": False,
        "original_file": str(input_path),
        "rescored_file": str(output_path),
    }

    print(json.dumps(summary, indent=2))
    print(
        "RESCORING COMPLETED - "
        "no API call was made."
    )


if __name__ == "__main__":
    main()