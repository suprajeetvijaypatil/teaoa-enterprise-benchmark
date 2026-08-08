from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from runner.benchmark_v2_loader import load_scenario
from runner.execution_trace_v2 import (
    FINAL_STATUSES,
    add_event,
    create_trace,
    finalize_trace,
    validate_trace,
)

from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
)
from runner.framework_adapter_registry_v2 import (
    dispatch_adapter,
)
from runner.model_context_v2 import build_model_context
from runner.scorer_v2 import score_trace
from runner.teaoa_controller_v2 import (
    execute_controlled_tool,
)
from runner.simulated_tool_executor_v2 import (
    execute_simulated_tool,
)
from runner.tool_feedback_v2 import sanitize_value


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RESULTS_ROOT = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
)

GLOBAL_TURN_SAFETY_CAP = 19

def choose_trace_status(
    completed: bool,
) -> str:
    preferred = (
        "completed"
        if completed
        else "failed"
    )

    if preferred in FINAL_STATUSES:
        return preferred

    for fallback in [
        "blocked",
        "incomplete",
        "failed",
        "completed",
    ]:
        if fallback in FINAL_STATUSES:
            return fallback

    raise RuntimeError(
        "No compatible final trace status exists."
    )


def proposal_signature(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "arguments": arguments,
        },
        sort_keys=True,
    )

def resolve_turn_limit(
    scenario: dict[str, Any],
    requested_limit: int,
) -> int:
    if requested_limit > 0:
        return min(
            requested_limit,
            GLOBAL_TURN_SAFETY_CAP,
        )

    ground_truth = scenario["ground_truth"]

    allowed_tool_count = len(
        ground_truth.get("allowed_tools", [])
    )

    required_step_count = len(
        ground_truth.get("required_steps", [])
    )

    minimum_steps = int(
        ground_truth.get("minimum_steps", 0)
    )

    recommended_limit = max(
        allowed_tool_count + 2,
        required_step_count + 1,
        minimum_steps + 3,
    )

    return min(
        recommended_limit,
        GLOBAL_TURN_SAFETY_CAP,
    )


def run_dry_validation(
    workflow_id: str,
    framework: str,
    configuration: str,
) -> dict[str, Any]:
    scenario = load_scenario(workflow_id)
    context = build_model_context(scenario)

    turn_limit = resolve_turn_limit(
        scenario=scenario,
        requested_limit=0,
    )

    request = AdapterRequest(
        run_id=f"automatic-dry-{uuid4().hex[:8]}",
        framework=framework,
        workflow_id=workflow_id,
        configuration=configuration,
        model="MODEL_NOT_CALLED_IN_DRY_RUN",
        temperature=0.0,
        model_context=context,
        dry_run=True,
    )

    result = dispatch_adapter(
        request,
        allow_api_call=False,
    )

    return {
        "execution_type": (
            "automatic_multi_turn_dry_validation"
        ),
        "workflow_id": workflow_id,
        "framework": framework,
        "configuration": configuration,
        "automatic_turn_limit": turn_limit,
        "global_turn_safety_cap": (
            GLOBAL_TURN_SAFETY_CAP
        ),
        "api_call_made": False,
        "total_tokens": result.token_usage[
            "total_tokens"
        ],
        "adapter_validated": (
            result.final_status
            in {
                "dry_run_passed",
                "dry_run_validated",
            }
        ),
        "real_execution_locked": True,
    }

def execute_tool_for_configuration(
    *,
    configuration: str,
    trace: dict[str, Any],
    scenario: dict[str, Any],
    tool_name: str,
    step_number: int,
    arguments: dict[str, Any],
    fault_state: dict[str, int],
) -> dict[str, Any]:
    fault_injection = (
        scenario["workflow"].get(
            "fault_injection"
        )
        or {}
    )

    fault_type = str(
        fault_injection.get("type", "")
    )

    maximum_occurrences = int(
        fault_injection.get(
            "maximum_occurrences",
            0,
        )
    )

    should_inject_timeout = (
        fault_type == "tool_timeout"
        and tool_name == "retry_tool"
        and fault_state.get(
            "occurrences",
            0,
        )
        < maximum_occurrences
    )

    if should_inject_timeout:
        fault_state["occurrences"] = (
            fault_state.get(
                "occurrences",
                0,
            )
            + 1
        )

    if configuration == "teaoa":
        return execute_controlled_tool(
            trace=trace,
            scenario=scenario,
            tool_name=tool_name,
            step_number=step_number,
            arguments=arguments,
            approval_granted=None,
            forced_failures=(
                1
                if should_inject_timeout
                else 0
            ),
            forced_failure_reason=(
                "tool_timeout"
            ),
        )

    add_event(
        trace=trace,
        event_type="tool_proposed",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "arguments": arguments,
            "configuration": "native",
        },
    )

    add_event(
        trace=trace,
        event_type="tool_started",
        step_number=step_number,
        details={
            "tool_name": tool_name,
            "attempt": 1,
            "configuration": "native",
        },
    )

    if should_inject_timeout:
        failure = {
            "tool_name": tool_name,
            "status": "failed",
            "reason": "tool_timeout",
            "attempt": 1,
            "configuration": "native",
            "policy_controller_applied": False,
        }

        add_event(
            trace=trace,
            event_type="tool_failed",
            step_number=step_number,
            details=failure,
        )

        return failure

    try:
        result = execute_simulated_tool(
            scenario=scenario,
            tool_name=tool_name,
            arguments=arguments,
        )

        add_event(
            trace=trace,
            event_type="tool_succeeded",
            step_number=step_number,
            details={
                "tool_name": tool_name,
                "status": "succeeded",
                "arguments": arguments,
                "result": result,
                "configuration": "native",
                "policy_controller_applied": False,
            },
        )

        return result

    except Exception as error:
        add_event(
            trace=trace,
            event_type="tool_failed",
            step_number=step_number,
            details={
                "tool_name": tool_name,
                "status": "failed",
                "arguments": arguments,
                "error": str(error),
                "configuration": "native",
                "policy_controller_applied": False,
            },
        )

        return {
            "status": "failed",
            "tool_name": tool_name,
            "error": str(error),
        }


def run_automatic_loop(
    *,
    framework: str,
    workflow_id: str,
    configuration: str,
    model: str,
    temperature: float,
    max_turns: int,
) -> dict[str, Any]:
    scenario = load_scenario(workflow_id)
    effective_max_turns = resolve_turn_limit(
    scenario=scenario,
    requested_limit=max_turns,
)
    base_context = build_model_context(scenario)

    trace = create_trace(
        workflow_id=workflow_id,
        framework=framework,
        configuration=configuration,
        repeat_number=1,
        model=model,
        temperature=temperature,
    )

    execution_history = []
    model_turns = []
    seen_proposals = set()
    fault_state = {
    "occurrences": 0,
    }

    total_input_tokens = 0
    total_output_tokens = 0
    completed = False
    final_answer = None
    stop_reason = "maximum_turns_reached"

    for turn_number in range(
    1,
    effective_max_turns + 1,
):
        turn_context = deepcopy(base_context)

        turn_context["turn_number"] = turn_number
        turn_context["execution_history"] = (
            sanitize_value(execution_history)
        )
        turn_context["continuation_instruction"] = (
            "Review the execution history. Do not repeat "
            "a completed tool call. Propose the next "
            "required tool, or return a completed final "
            "answer only when the workflow is complete."
        )

        request = AdapterRequest(
            run_id=trace["trace_id"],
            framework=framework,
            workflow_id=workflow_id,
            configuration=configuration,
            model=model,
            temperature=temperature,
            model_context=turn_context,
            dry_run=False,
        )

        adapter_result = dispatch_adapter(
            request,
            allow_api_call=True,
        )

        total_input_tokens += int(
            adapter_result.token_usage.get(
                "input_tokens",
                0,
            )
        )

        total_output_tokens += int(
            adapter_result.token_usage.get(
                "output_tokens",
                0,
            )
        )

        final_answer = adapter_result.output_text

        proposed_tools = (
            adapter_result.proposed_tools
        )

        model_turns.append(
            {
                "turn_number": turn_number,
                "final_status": (
                    adapter_result.final_status
                ),
                "completed_steps": (
                    adapter_result.completed_steps
                ),
                "proposed_tools": proposed_tools,
                "policy_decisions": (
                    adapter_result.policy_decisions
                ),
                "output_text": (
                    adapter_result.output_text
                ),
                "latency_seconds": (
                    adapter_result.latency_seconds
                ),
                "token_usage": (
                    adapter_result.token_usage
                ),
            }
        )

        add_event(
            trace=trace,
            event_type="model_response",
            step_number=turn_number,
            details={
                "final_status": (
                    adapter_result.final_status
                ),
                "completed_steps": (
                    adapter_result.completed_steps
                ),
                "policy_decisions": (
                    adapter_result.policy_decisions
                ),
            },
        )

        normalized_status = (
            adapter_result.final_status
            .strip()
            .lower()
        )

        completion_statuses = {
            "completed",
            "recovered",
            "complete",
            "success",
            "succeeded",
            "resolved",
            "blocked",
            "approval_required",
            "approval_denied",
            "timeout",
        }

        if (
            normalized_status in completion_statuses
            and not proposed_tools
        ):
            completed = True
            stop_reason = "model_reported_completion"
            break

        if not proposed_tools:
            stop_reason = "model_proposed_no_tool"
            break

        new_tool_executed = False
        invalid_proposal_detected = False

        for proposal in proposed_tools:
            if not isinstance(
                proposal,
                dict,
            ):
                stop_reason = (
                    "invalid_tool_proposal"
                )

                invalid_proposal_detected = True
                break

            tool_name = (
                proposal.get("tool")
                or proposal.get("tool_name")
                or proposal.get("name")
            )

            if not tool_name:
                stop_reason = (
                    "invalid_tool_proposal"
                )

                invalid_proposal_detected = True
                break

            arguments = proposal.get(
                "arguments",
                {},
            )

            if not isinstance(
                arguments,
                dict,
            ):
                stop_reason = (
                    "invalid_tool_arguments"
                )

                invalid_proposal_detected = True
                break

            signature = proposal_signature(
                str(tool_name),
                arguments,
            )

            if signature in seen_proposals:
                stop_reason = (
                    "duplicate_tool_proposal_detected"
                )
                break

            seen_proposals.add(signature)

            step_number = (
                len(execution_history) + 1
            )

            tool_result = (
                execute_tool_for_configuration(
                    configuration=configuration,
                    trace=trace,
                    scenario=scenario,
                    tool_name=str(tool_name),
                    step_number=step_number,
                    arguments=arguments,
                    fault_state=fault_state,
                )
            )

            execution_history.append(
                {
                    "turn_number": turn_number,
                    "step_number": step_number,
                    "tool_name": str(tool_name),
                    "arguments": arguments,
                    "result": tool_result,
                }
            )

            new_tool_executed = True

        if invalid_proposal_detected:
            break

        if stop_reason == (
            "duplicate_tool_proposal_detected"
        ):
            break

        if not new_tool_executed:
            stop_reason = (
                "no_new_tool_executed"
            )
            break

    workflow_approval_value = (
        scenario["workflow"].get(
            "human_approval_required",
            scenario["workflow"].get(
                "approval_required",
                False,
            ),
        )
    )

    workflow_requires_approval = (
        workflow_approval_value is True
        or str(
            workflow_approval_value
        ).strip().lower()
        in {
            "true",
            "1",
            "yes",
        }
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

    approval_is_pending = (
        workflow_requires_approval
        and approval_request_created
        and not approval_decision_events
    )

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


    
    if approval_is_pending:
        trace_status = "approval_required"

    elif (
        timeout_observed
        and recovery_validated
    ):
        trace_status = "recovered"

    else:
        last_model_status = (
            str(
                model_turns[-1].get(
                    "final_status",
                    "",
                )
            )
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
            if model_turns
            else ""
        )

        status_aliases = {
            "complete": "completed",
            "success": "completed",
            "succeeded": "completed",
            "resolved": "completed",
        }

        last_model_status = (
            status_aliases.get(
                last_model_status,
                last_model_status,
            )
        )

        if (
            last_model_status
            in FINAL_STATUSES
        ):
            trace_status = last_model_status
        else:
            trace_status = choose_trace_status(
                completed
            )

    finalize_trace(
        trace=trace,
        final_status=trace_status,
        final_answer=final_answer,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )

    validate_trace(trace)

    score = score_trace(
        scenario=scenario,
        trace=trace,
    )

    return {
        "execution_type": (
            "automatic_multi_turn_paid_execution"
        ),
        "executed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "workflow_id": workflow_id,
        "framework": framework,
        "configuration": configuration,
        "model": model,
        "requested_turn_limit": max_turns,
"maximum_turns": effective_max_turns,
"global_turn_safety_cap": (
    GLOBAL_TURN_SAFETY_CAP
),
        "completed": completed,
        "stop_reason": stop_reason,
        "model_turn_count": len(model_turns),
        "tool_execution_count": len(
            execution_history
        ),
        "total_token_usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": (
                total_input_tokens
                + total_output_tokens
            ),
        },
        "model_turns": model_turns,
        "execution_history": execution_history,
        "trace": trace,
        "score": score,
        "api_calls_made": len(model_turns),
    }

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the automatic benchmark_v2 "
            "model-tool-model loop."
        )
    )

    parser.add_argument(
        "--framework",
        choices=[
            "openai_agents",
            "langgraph",
            "crewai",
            "autogen",
            "semantic_kernel",
            "google_adk",
        ],
        default="openai_agents",
        help="Framework used for execution.",
    )

    parser.add_argument(
        "--workflow",
        default="CS-001",
        help=(
            "Workflow ID from the benchmark manifest, "
            "such as CS-001 or FIN-010."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-paid-api-calls",
        action="store_true",
    )

    parser.add_argument(
        "--max-turns",
        type=int,
        default=0,
        help=(
            "Maximum turns. Use 0 to calculate "
            "the limit automatically."
        ),
    )

    parser.add_argument(
        "--configuration",
        choices=["native", "teaoa"],
        default="native",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    workflow_id = args.workflow.strip().upper()

    if (
        args.dry_run
        and args.confirm_paid_api_calls
    ):
        raise ValueError(
            "Choose only one execution mode."
        )

    if args.max_turns < 0:
        raise ValueError(
            "--max-turns cannot be negative."
        )

    if args.dry_run:
        output = run_dry_validation(
            workflow_id=workflow_id,
            framework=args.framework,
            configuration=args.configuration,
        )

        output_path = (
            RESULTS_ROOT
            / (
                f"{workflow_id.lower()}_"
                f"{args.framework}_"
                f"automatic_multi_turn_"
                f"{args.configuration}_dry.json"
            )
        )

    elif args.confirm_paid_api_calls:
        output = run_automatic_loop(
            framework=args.framework,
            workflow_id=workflow_id,
            configuration=args.configuration,
            model="gpt-5.6-luna",
            temperature=0.0,
            max_turns=args.max_turns,
        )

        output_path = (
            RESULTS_ROOT
            / (
                f"{workflow_id.lower()}_"
                f"{args.framework}_"
                f"automatic_multi_turn_"
                f"{args.configuration}_paid.json"
            )
        )

    else:
        raise RuntimeError(
            "Execution is locked. Use --dry-run first."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(output, file, indent=2)

    print(json.dumps(output, indent=2))
    print(f"Report: {output_path}")

    if args.dry_run:
        print(
            "AUTOMATIC MULTI-TURN ENGINE PASSED - "
            "no API call was made."
        )
    else:
        print(
            "AUTOMATIC MULTI-TURN EXECUTION COMPLETED."
        )


if __name__ == "__main__":
    main()