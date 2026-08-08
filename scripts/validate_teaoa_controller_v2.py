from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)

from runner.execution_trace_v2 import (
    create_trace,
    validate_trace,
)

from runner.simulated_tool_executor_v2 import (
    classify_operation,
    normalize_tool_names,
)

from runner.teaoa_controller_v2 import (
    as_bool,
    execute_controlled_tool,
    get_retry_limit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "teaoa_controller_validation.json"
)


def create_test_trace(
    workflow_id: str,
) -> dict[str, Any]:
    return create_trace(
        workflow_id=workflow_id,
        framework="controller_validation",
        configuration="teaoa",
        repeat_number=1,
        model="MODEL_NOT_CALLED",
        temperature=0.0,
    )


def find_test_scenarios() -> dict[str, Any]:
    manifest_rows = load_manifest()

    selected = {
        "basic": None,
        "forbidden": None,
        "approval": None,
        "retry": None,
    }

    for row in manifest_rows:
        if row.get("enabled", "").lower() != "true":
            continue

        scenario = load_scenario(
            row["workflow_id"]
        )

        workflow = scenario["workflow"]

        allowed_tools = normalize_tool_names(
            workflow.get("allowed_tools")
        )

        forbidden_tools = normalize_tool_names(
            workflow.get("forbidden_tools")
        )

        write_tools = [
            tool
            for tool in allowed_tools
            if classify_operation(tool) == "write"
        ]

        approval_required = as_bool(
            workflow.get(
                "human_approval_required",
                workflow.get(
                    "approval_required",
                    False,
                ),
            )
        )

        retry_limit = get_retry_limit(workflow)

        if selected["basic"] is None and allowed_tools:
            selected["basic"] = (
                scenario,
                allowed_tools[0],
            )

        if (
            selected["forbidden"] is None
            and forbidden_tools
        ):
            selected["forbidden"] = (
                scenario,
                forbidden_tools[0],
            )

        if (
            selected["approval"] is None
            and approval_required
            and write_tools
        ):
            selected["approval"] = (
                scenario,
                write_tools[0],
            )

        if (
            selected["retry"] is None
            and retry_limit >= 1
            and allowed_tools
        ):
            selected["retry"] = (
                scenario,
                allowed_tools[0],
            )

        if all(selected.values()):
            break

    missing = [
        name
        for name, value in selected.items()
        if value is None
    ]

    if missing:
        raise ValueError(
            "Could not find scenarios for: "
            + ", ".join(missing)
        )

    return selected


def run_validation_case(
    name: str,
    scenario: dict[str, Any],
    tool_name: str,
    expected_status: str,
    approval_granted: bool = True,
    forced_failures: int = 0,
) -> dict[str, Any]:
    trace = create_test_trace(
        scenario["workflow_id"]
    )

    result = execute_controlled_tool(
        trace=trace,
        scenario=scenario,
        tool_name=tool_name,
        step_number=1,
        arguments={
            "controller_validation": name,
        },
        approval_granted=approval_granted,
        forced_failures=forced_failures,
    )

    validate_trace(trace)

    passed = result["status"] == expected_status

    return {
        "case": name,
        "workflow_id": scenario["workflow_id"],
        "tool_name": tool_name,
        "expected_status": expected_status,
        "actual_status": result["status"],
        "attempt_count": result["attempt_count"],
        "trace_event_types": [
            event["event_type"]
            for event in trace["events"]
        ],
        "passed": passed,
    }


def main() -> None:
    selected = find_test_scenarios()
    results = []

    basic_scenario, basic_tool = selected["basic"]

    results.append(
        run_validation_case(
            name="allowed_tool",
            scenario=basic_scenario,
            tool_name=basic_tool,
            expected_status="succeeded",
        )
    )

    results.append(
        run_validation_case(
            name="unknown_tool",
            scenario=basic_scenario,
            tool_name="__unknown_controller_tool__",
            expected_status="blocked",
        )
    )

    forbidden_scenario, forbidden_tool = (
        selected["forbidden"]
    )

    results.append(
        run_validation_case(
            name="forbidden_tool",
            scenario=forbidden_scenario,
            tool_name=forbidden_tool,
            expected_status="blocked",
        )
    )

    approval_scenario, approval_tool = (
        selected["approval"]
    )

    results.append(
        run_validation_case(
            name="approval_denied",
            scenario=approval_scenario,
            tool_name=approval_tool,
            expected_status="approval_denied",
            approval_granted=False,
        )
    )

    retry_scenario, retry_tool = selected["retry"]

    retry_limit = get_retry_limit(
        retry_scenario["workflow"]
    )

    results.append(
        run_validation_case(
            name="retry_recovery",
            scenario=retry_scenario,
            tool_name=retry_tool,
            expected_status="succeeded",
            forced_failures=1,
        )
    )

    results.append(
        run_validation_case(
            name="retry_exhausted",
            scenario=retry_scenario,
            tool_name=retry_tool,
            expected_status="failed",
            forced_failures=retry_limit + 1,
        )
    )

    passed_count = sum(
        result["passed"]
        for result in results
    )

    failed_cases = [
        result["case"]
        for result in results
        if not result["passed"]
    ]

    report = {
        "test_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(failed_cases),
        "failed_cases": failed_cases,
        "api_call_made": False,
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
        "test_count": report["test_count"],
        "passed_count": report["passed_count"],
        "failed_count": report["failed_count"],
        "failed_cases": report["failed_cases"],
        "api_call_made": False,
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    for result in results:
        status = (
            "PASSED"
            if result["passed"]
            else "FAILED"
        )

        print(
            f"{result['case']}: {status} "
            f"| expected={result['expected_status']} "
            f"| actual={result['actual_status']}"
        )

    if failed_cases:
        raise SystemExit(
            "TEAOA CONTROLLER VALIDATION FAILED."
        )

    print(
        "ALL TEAOA CONTROL PATHS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()