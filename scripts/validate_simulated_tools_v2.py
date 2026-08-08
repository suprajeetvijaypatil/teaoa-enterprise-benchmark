from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)

from runner.simulated_tool_executor_v2 import (
    execute_simulated_tool,
    normalize_tool_names,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "simulated_tool_validation.json"
)


def validate_scenario(
    workflow_id: str,
) -> dict[str, Any]:
    scenario = load_scenario(workflow_id)
    workflow = scenario["workflow"]

    allowed_tools = normalize_tool_names(
        workflow.get("allowed_tools")
    )

    forbidden_tools = normalize_tool_names(
        workflow.get("forbidden_tools")
    )

    conflicts = sorted(
        set(allowed_tools) & set(forbidden_tools)
    )

    errors = []
    allowed_tests = []
    forbidden_tests = []

    if conflicts:
        errors.append(
            "Tools appear in both allowed and forbidden lists: "
            + ", ".join(conflicts)
        )

    for tool_name in allowed_tools:
        result = execute_simulated_tool(
            scenario=scenario,
            tool_name=tool_name,
            arguments={"bulk_validation": True},
        )

        passed = (
            result["status"] == "succeeded"
            and result["policy_decision"] == "allowed"
        )

        allowed_tests.append(
            {
                "tool_name": tool_name,
                "status": result["status"],
                "passed": passed,
            }
        )

        if not passed:
            errors.append(
                f"Allowed tool did not succeed: {tool_name}"
            )

    for tool_name in forbidden_tools:
        result = execute_simulated_tool(
            scenario=scenario,
            tool_name=tool_name,
            arguments={"bulk_validation": True},
        )

        passed = (
            result["status"] == "blocked"
            and result["policy_decision"]
            == "forbidden_tool"
        )

        forbidden_tests.append(
            {
                "tool_name": tool_name,
                "status": result["status"],
                "passed": passed,
            }
        )

        if not passed:
            errors.append(
                f"Forbidden tool was not blocked: {tool_name}"
            )

    unknown_result = execute_simulated_tool(
        scenario=scenario,
        tool_name="__unknown_validation_tool__",
        arguments={"bulk_validation": True},
    )

    unknown_tool_blocked = (
        unknown_result["status"] == "blocked"
        and unknown_result["policy_decision"]
        == "tool_not_allowed"
    )

    if not unknown_tool_blocked:
        errors.append("Unknown tool was not blocked.")

    return {
        "workflow_id": workflow_id,
        "allowed_tool_count": len(allowed_tools),
        "forbidden_tool_count": len(forbidden_tools),
        "conflicts": conflicts,
        "allowed_tests": allowed_tests,
        "forbidden_tests": forbidden_tests,
        "unknown_tool_blocked": unknown_tool_blocked,
        "errors": errors,
        "valid": not errors,
    }


def main() -> None:
    manifest_rows = load_manifest()

    enabled_workflow_ids = [
        row["workflow_id"]
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    results = []
    loading_errors = []

    for workflow_id in enabled_workflow_ids:
        try:
            results.append(
                validate_scenario(workflow_id)
            )

        except Exception as error:
            loading_errors.append(
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
        {
            "workflow_id": result["workflow_id"],
            "errors": result["errors"],
        }
        for result in results
        if not result["valid"]
    ]

    total_allowed_tests = sum(
        result["allowed_tool_count"]
        for result in results
    )

    total_forbidden_tests = sum(
        result["forbidden_tool_count"]
        for result in results
    )

    report = {
        "enabled_scenario_count": len(
            enabled_workflow_ids
        ),
        "tested_scenario_count": len(results),
        "valid_scenario_count": valid_count,
        "invalid_scenario_count": len(
            invalid_results
        ),
        "loading_error_count": len(
            loading_errors
        ),
        "total_allowed_tool_tests": (
            total_allowed_tests
        ),
        "total_forbidden_tool_tests": (
            total_forbidden_tests
        ),
        "api_call_made": False,
        "invalid_results": invalid_results,
        "loading_errors": loading_errors,
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
        "enabled_scenario_count": report[
            "enabled_scenario_count"
        ],
        "tested_scenario_count": report[
            "tested_scenario_count"
        ],
        "valid_scenario_count": report[
            "valid_scenario_count"
        ],
        "invalid_scenario_count": report[
            "invalid_scenario_count"
        ],
        "loading_error_count": report[
            "loading_error_count"
        ],
        "total_allowed_tool_tests": report[
            "total_allowed_tool_tests"
        ],
        "total_forbidden_tool_tests": report[
            "total_forbidden_tool_tests"
        ],
        "api_call_made": False,
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    if (
        report["invalid_scenario_count"] > 0
        or report["loading_error_count"] > 0
    ):
        raise SystemExit(
            "SIMULATED TOOL VALIDATION FAILED — "
            "review the report."
        )

    print(
        "ALL SIMULATED TOOLS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()