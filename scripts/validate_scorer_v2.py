from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)

from runner.execution_trace_v2 import (
    add_event,
    create_trace,
    utc_now,
    validate_trace,
)

from runner.scorer_v2 import (
    build_perfect_validation_trace,
    score_trace,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "scorer_validation.json"
)


def build_incomplete_trace(
    scenario: dict[str, Any],
) -> dict[str, Any]:
    trace = create_trace(
        workflow_id=scenario["workflow_id"],
        framework="incomplete_trace_validation",
        configuration="teaoa",
        repeat_number=1,
        model="MODEL_NOT_CALLED",
        temperature=0.0,
    )

    add_event(
        trace=trace,
        event_type="run_started",
        step_number=0,
        details={"api_call_made": False},
    )

    forbidden_tools = scenario[
        "ground_truth"
    ].get("forbidden_tools", [])

    if forbidden_tools:
        add_event(
            trace=trace,
            event_type="tool_succeeded",
            step_number=1,
            details={
                "tool_name": forbidden_tools[0],
                "unsafe_action_executed": True,
            },
        )

    add_event(
        trace=trace,
        event_type="run_completed",
        step_number=2,
        details={
            "message": (
                "Deliberately incomplete validation."
            ),
            "api_call_made": False,
        },
    )

    trace["finished_at"] = utc_now()
    trace["final_status"] = (
        "__incorrect_validation_status__"
    )
    trace["final_answer"] = (
        "Incomplete synthetic validation."
    )

    validate_trace(trace)

    return trace


def validate_workflow(
    workflow_id: str,
) -> dict[str, Any]:
    scenario = load_scenario(workflow_id)

    perfect_trace = (
        build_perfect_validation_trace(
            scenario
        )
    )

    perfect_score = score_trace(
        scenario=scenario,
        trace=perfect_trace,
    )

    incomplete_trace = build_incomplete_trace(
        scenario
    )

    incomplete_score = score_trace(
        scenario=scenario,
        trace=incomplete_trace,
    )

    perfect_passed = (
        perfect_score["score"]
        == perfect_score["maximum_score"]
    )

    incomplete_passed = (
        incomplete_score["score"]
        < incomplete_score["maximum_score"]
    )

    return {
        "workflow_id": workflow_id,
        "maximum_score": perfect_score[
            "maximum_score"
        ],
        "perfect_score": perfect_score["score"],
        "perfect_percentage": perfect_score[
            "percentage"
        ],
        "incomplete_score": incomplete_score[
            "score"
        ],
        "incomplete_percentage": (
            incomplete_score["percentage"]
        ),
        "perfect_trace_passed": perfect_passed,
        "incomplete_trace_passed": (
            incomplete_passed
        ),
        "valid": (
            perfect_passed
            and incomplete_passed
        ),
    }


def main() -> None:
    manifest_rows = load_manifest()

    workflow_ids = [
        row["workflow_id"]
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    results = []
    errors = []

    for workflow_id in workflow_ids:
        try:
            results.append(
                validate_workflow(workflow_id)
            )

        except Exception as error:
            errors.append(
                {
                    "workflow_id": workflow_id,
                    "error": str(error),
                }
            )

    valid_count = sum(
        result["valid"]
        for result in results
    )

    invalid_results = [
        result
        for result in results
        if not result["valid"]
    ]

    report = {
        "workflow_count": len(workflow_ids),
        "tested_count": len(results),
        "valid_count": valid_count,
        "invalid_count": len(
            invalid_results
        ),
        "error_count": len(errors),
        "api_call_made": False,
        "invalid_results": invalid_results,
        "errors": errors,
        "results": results,
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    summary = {
        "workflow_count": report[
            "workflow_count"
        ],
        "tested_count": report["tested_count"],
        "valid_count": report["valid_count"],
        "invalid_count": report[
            "invalid_count"
        ],
        "error_count": report["error_count"],
        "api_call_made": False,
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    if (
        report["invalid_count"] > 0
        or report["error_count"] > 0
    ):
        raise SystemExit(
            "BULK SCORER VALIDATION FAILED."
        )

    print(
        "ALL 100 SCORER TESTS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()