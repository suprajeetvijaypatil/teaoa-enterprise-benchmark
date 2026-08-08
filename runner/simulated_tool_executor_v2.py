from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any

from runner.benchmark_v2_loader import load_scenario
from runner.execution_trace_v2 import (
    add_event,
    create_trace,
    finalize_trace,
    validate_trace,
)


READ_PREFIXES = (
    "get_",
    "read_",
    "search_",
    "check_",
    "compare_",
    "calculate_",
    "classify_",
    "confirm_",
    "detect_",
    "validate_",
    "verify_",
)

WRITE_PREFIXES = (
    "create_",
    "edit_",
    "execute_",
    "flag_",
    "mark_",
    "pause_",
    "quarantine_",
    "record_",
    "release_",
    "request_",
    "resolve_",
    "retry_",
    "revoke_",
    "rollback_",
    "route_",
    "run_",
    "schedule_",
    "use_",
    "deny_",
)


def normalize_tool_names(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        names = []

        for item in value:
            if isinstance(item, str):
                names.append(item)

            elif isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("tool_name")
                    or item.get("id")
                )

                if name:
                    names.append(str(name))

        return names

    return []


def classify_operation(tool_name: str) -> str:
    if tool_name.startswith(READ_PREFIXES):
        return "read"

    if tool_name.startswith(WRITE_PREFIXES):
        return "write"

    return "other"


def build_dataset_view(dataset: Any) -> Any:
    if not isinstance(dataset, dict):
        return deepcopy(dataset)

    preferred_fields = [
        "workflow_id",
        "dataset_id",
        "integration_status",
        "ticket",
        "customer_record",
        "finance_record",
        "healthcare_record",
        "it_security_record",
        "procurement_record",
        "repository_record",
        "supply_chain_record",
    ]

    selected = {
        field: deepcopy(dataset[field])
        for field in preferred_fields
        if field in dataset
    }

    if selected:
        return selected

    return deepcopy(dataset)


def execute_simulated_tool(
    scenario: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow = scenario["workflow"]

    allowed_tools = set(
        normalize_tool_names(workflow.get("allowed_tools"))
    )

    forbidden_tools = set(
        normalize_tool_names(workflow.get("forbidden_tools"))
    )

    arguments = arguments or {}

    if tool_name in forbidden_tools:
        return {
            "tool_name": tool_name,
            "status": "blocked",
            "policy_decision": "forbidden_tool",
            "operation_kind": classify_operation(tool_name),
            "arguments": arguments,
            "result": None,
        }

    if tool_name not in allowed_tools:
        return {
            "tool_name": tool_name,
            "status": "blocked",
            "policy_decision": "tool_not_allowed",
            "operation_kind": classify_operation(tool_name),
            "arguments": arguments,
            "result": None,
        }

    operation_kind = classify_operation(tool_name)

    return {
        "tool_name": tool_name,
        "status": "succeeded",
        "policy_decision": "allowed",
        "operation_kind": operation_kind,
        "arguments": arguments,
        "result": {
            "simulated": True,
            "workflow_id": scenario["workflow_id"],
            "dataset_view": build_dataset_view(
                scenario["dataset"]
            ),
            "message": (
                f"Simulated tool '{tool_name}' completed "
                "without contacting an external service."
            ),
        },
    }


def record_tool_execution(
    trace: dict[str, Any],
    scenario: dict[str, Any],
    tool_name: str,
    step_number: int,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    add_event(
        trace=trace,
        event_type="tool_proposed",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "arguments": arguments or {},
        },
    )

    result = execute_simulated_tool(
        scenario=scenario,
        tool_name=tool_name,
        arguments=arguments,
    )

    add_event(
        trace=trace,
        event_type="policy_decision",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "decision": result["policy_decision"],
        },
    )

    if result["status"] == "blocked":
        add_event(
            trace=trace,
            event_type="tool_failed",
            step_number=step_number,
            details=result,
        )

        return result

    add_event(
        trace=trace,
        event_type="tool_started",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "operation_kind": result["operation_kind"],
        },
    )

    add_event(
        trace=trace,
        event_type="tool_succeeded",
        step_number=step_number,
        details=result,
    )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test deterministic benchmark_v2 tool execution."
        )
    )

    parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow ID such as CS-001.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario = load_scenario(args.workflow)

    allowed_tools = normalize_tool_names(
        scenario["workflow"].get("allowed_tools")
    )

    forbidden_tools = normalize_tool_names(
        scenario["workflow"].get("forbidden_tools")
    )

    if not allowed_tools:
        raise ValueError(
            f"No allowed tools found for {args.workflow}."
        )

    trace = create_trace(
        workflow_id=scenario["workflow_id"],
        framework="simulator_validation",
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

    allowed_result = record_tool_execution(
        trace=trace,
        scenario=scenario,
        tool_name=allowed_tools[0],
        step_number=1,
        arguments={"validation_test": True},
    )

    forbidden_result = None

    if forbidden_tools:
        forbidden_result = record_tool_execution(
            trace=trace,
            scenario=scenario,
            tool_name=forbidden_tools[0],
            step_number=2,
            arguments={"validation_test": True},
        )

    add_event(
        trace=trace,
        event_type="run_completed",
        step_number=3,
        details={"api_call_made": False},
    )

    finalize_trace(
        trace=trace,
        final_status="completed",
        final_answer="Simulator validation completed.",
    )

    validate_trace(trace)

    summary = {
        "workflow_id": scenario["workflow_id"],
        "allowed_tool_test": {
            "tool_name": allowed_result["tool_name"],
            "status": allowed_result["status"],
            "policy_decision": allowed_result[
                "policy_decision"
            ],
        },
        "forbidden_tool_test": (
            {
                "tool_name": forbidden_result["tool_name"],
                "status": forbidden_result["status"],
                "policy_decision": forbidden_result[
                    "policy_decision"
                ],
            }
            if forbidden_result
            else "No forbidden tool defined."
        ),
        "trace_event_count": len(trace["events"]),
        "api_call_made": False,
    }

    print(json.dumps(summary, indent=2))
    print(
        "SIMULATED TOOL VALIDATION PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()