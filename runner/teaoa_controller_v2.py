from __future__ import annotations

import argparse
import json
from typing import Any

from runner.benchmark_v2_loader import load_scenario

from runner.execution_trace_v2 import (
    add_event,
    create_trace,
    finalize_trace,
    validate_trace,
)

from runner.simulated_tool_executor_v2 import (
    classify_operation,
    execute_simulated_tool,
    normalize_tool_names,
)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() == "true"

    return bool(value)


def get_retry_limit(workflow: dict[str, Any]) -> int:
    value = workflow.get("retry_limit", 0)

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def get_policy_decision(
    scenario: dict[str, Any],
    tool_name: str,
) -> str:
    workflow = scenario["workflow"]

    allowed_tools = set(
        normalize_tool_names(
            workflow.get("allowed_tools")
        )
    )

    forbidden_tools = set(
        normalize_tool_names(
            workflow.get("forbidden_tools")
        )
    )

    if tool_name in forbidden_tools:
        return "forbidden_tool"

    if tool_name not in allowed_tools:
        return "tool_not_allowed"

    return "allowed"


def requires_approval(
    scenario: dict[str, Any],
    tool_name: str,
) -> bool:
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

    operation_kind = classify_operation(
        tool_name
    )

    approval_exempt_tools = {
        "create_approval_request",
        "record_audit_event",
    }

    return (
        workflow_requires_approval
        and operation_kind == "write"
        and tool_name not in approval_exempt_tools
    )


def execute_controlled_tool(
    trace: dict[str, Any],
    scenario: dict[str, Any],
    tool_name: str,
    step_number: int,
    arguments: dict[str, Any] | None = None,
    approval_granted: bool | None = None,
    forced_failures: int = 0,
    forced_failure_reason: str = (
    "forced_validation_failure"
),
) -> dict[str, Any]:
    arguments = arguments or {}

    add_event(
        trace=trace,
        event_type="tool_proposed",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )

    policy_decision = get_policy_decision(
        scenario=scenario,
        tool_name=tool_name,
    )

    add_event(
        trace=trace,
        event_type="policy_decision",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "decision": policy_decision,
        },
    )

    if policy_decision != "allowed":
        result = {
            "tool_name": tool_name,
            "status": "blocked",
            "policy_decision": policy_decision,
            "attempt_count": 0,
        }

        add_event(
            trace=trace,
            event_type="tool_failed",
            step_number=step_number,
            details=result,
        )

        return result

    approval_required = requires_approval(
        scenario=scenario,
        tool_name=tool_name,
    )

    if approval_required:
        add_event(
            trace=trace,
            event_type="approval_requested",
            step_number=step_number,
            details={
                "tool_name": tool_name,
                "operation_kind": classify_operation(
                    tool_name
                ),
            },
        )

        if approval_granted is True:
            add_event(
                trace=trace,
                event_type="approval_granted",
                step_number=step_number,
                details={"tool_name": tool_name},
            )

        elif approval_granted is False:
            add_event(
                trace=trace,
                event_type="approval_denied",
                step_number=step_number,
                details={"tool_name": tool_name},
            )

            return {
                "tool_name": tool_name,
                "status": "approval_denied",
                "policy_decision": "require_approval",
                "approval_required": True,
                "attempt_count": 0,
            }

        else:
            return {
                "tool_name": tool_name,
                "status": "approval_required",
                "policy_decision": "require_approval",
                "approval_required": True,
                "attempt_count": 0,
            }

    retry_limit = get_retry_limit(
        scenario["workflow"]
    )

    attempt_count = 0

    while True:
        attempt_count += 1

        add_event(
            trace=trace,
            event_type="tool_started",
            step_number=step_number,
            details={
                "tool_name": tool_name,
                "attempt": attempt_count,
            },
        )

        if attempt_count <= forced_failures:
            failure = {
                "tool_name": tool_name,
                "status": "failed",
                "reason": forced_failure_reason,
                "attempt": attempt_count,
            }

            add_event(
                trace=trace,
                event_type="tool_failed",
                step_number=step_number,
                details=failure,
            )

            retries_used = attempt_count

            if retries_used <= retry_limit:
                add_event(
                    trace=trace,
                    event_type="retry_started",
                    step_number=step_number,
                    details={
                        "tool_name": tool_name,
                        "next_attempt": attempt_count + 1,
                        "retry_limit": retry_limit,
                    },
                )

                add_event(
                    trace=trace,
                    event_type="recovery_action",
                    step_number=step_number,
                    details={
                        "tool_name": tool_name,
                        "action": (
                            "reset_simulated_tool_state"
                        ),
                    },
                )

                continue

            return {
                "tool_name": tool_name,
                "status": "failed",
                "policy_decision": "allowed",
                "reason": "retry_limit_exhausted",
                "attempt_count": attempt_count,
            }

        result = execute_simulated_tool(
            scenario=scenario,
            tool_name=tool_name,
            arguments=arguments,
        )

        result["approval_required"] = (
            approval_required
        )

        result["attempt_count"] = attempt_count

        add_event(
            trace=trace,
            event_type="tool_succeeded",
            step_number=step_number,
            details=result,
        )

        return result


def choose_validation_tool(
    scenario: dict[str, Any],
) -> str:
    allowed_tools = normalize_tool_names(
        scenario["workflow"].get("allowed_tools")
    )

    if not allowed_tools:
        raise ValueError(
            "The scenario does not define allowed tools."
        )

    write_tools = [
        tool_name
        for tool_name in allowed_tools
        if classify_operation(tool_name) == "write"
    ]

    if write_tools:
        return write_tools[0]

    return allowed_tools[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate TEAOA policy, approval, retry "
            "and recovery controls."
        )
    )

    parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow ID such as CS-001.",
    )

    parser.add_argument(
        "--approval",
        choices=["granted", "denied"],
        default="granted",
        help="Simulated human approval decision.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario = load_scenario(args.workflow)

    selected_tool = choose_validation_tool(
        scenario
    )

    retry_limit = get_retry_limit(
        scenario["workflow"]
    )

    forced_failures = 1 if retry_limit >= 1 else 0

    trace = create_trace(
        workflow_id=scenario["workflow_id"],
        framework="teaoa_controller_validation",
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

    result = execute_controlled_tool(
        trace=trace,
        scenario=scenario,
        tool_name=selected_tool,
        step_number=1,
        arguments={"validation_test": True},
        approval_granted=(
            args.approval == "granted"
        ),
        forced_failures=forced_failures,
    )

    if result["status"] == "succeeded":
        final_status = "completed"

    elif result["status"] == "approval_denied":
        final_status = "approval_denied"

    elif result["status"] == "blocked":
        final_status = "blocked"

    else:
        final_status = "failed"

    add_event(
        trace=trace,
        event_type=(
            "run_completed"
            if final_status == "completed"
            else "run_failed"
        ),
        step_number=2,
        details={
            "result_status": result["status"],
            "api_call_made": False,
        },
    )

    finalize_trace(
        trace=trace,
        final_status=final_status,
        final_answer=(
            "TEAOA controller validation completed."
        ),
    )

    validate_trace(trace)

    summary = {
        "workflow_id": scenario["workflow_id"],
        "selected_tool": selected_tool,
        "operation_kind": classify_operation(
            selected_tool
        ),
        "approval_required": requires_approval(
            scenario,
            selected_tool,
        ),
        "approval_decision": args.approval,
        "retry_limit": retry_limit,
        "forced_failures": forced_failures,
        "attempt_count": result["attempt_count"],
        "tool_status": result["status"],
        "final_status": trace["final_status"],
        "trace_event_types": [
            event["event_type"]
            for event in trace["events"]
        ],
        "api_call_made": False,
    }

    print(json.dumps(summary, indent=2))

    print(
        "TEAOA CONTROLLER VALIDATION PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()