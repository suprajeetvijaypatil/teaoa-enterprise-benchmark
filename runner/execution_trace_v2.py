from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from runner.benchmark_v2_loader import load_scenario


ALLOWED_EVENT_TYPES = {
    "run_started",
    "model_response",
    "tool_proposed",
    "policy_decision",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "tool_started",
    "tool_succeeded",
    "tool_failed",
    "retry_started",
    "recovery_action",
    "final_answer",
    "run_completed",
    "run_failed",
}


FINAL_STATUSES = {
    "completed",
    "recovered",
    "failed",
    "blocked",
    "approval_required",
    "approval_denied",
    "timeout",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_trace(
    workflow_id: str,
    framework: str,
    configuration: str,
    repeat_number: int,
    model: str,
    temperature: float,
) -> dict[str, Any]:
    if configuration not in {"native", "teaoa"}:
        raise ValueError(
            "Configuration must be either 'native' or 'teaoa'."
        )

    if repeat_number < 1:
        raise ValueError("Repeat number must be at least 1.")

    if not 0.0 <= temperature <= 2.0:
        raise ValueError(
            "Temperature must be between 0.0 and 2.0."
        )

    return {
        "trace_id": str(uuid4()),
        "workflow_id": workflow_id,
        "framework": framework,
        "configuration": configuration,
        "repeat_number": repeat_number,
        "model": model,
        "temperature": temperature,
        "started_at": utc_now(),
        "finished_at": None,
        "final_status": None,
        "final_answer": None,
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        "events": [],
    }


def add_event(
    trace: dict[str, Any],
    event_type: str,
    step_number: int,
    details: dict[str, Any] | None = None,
) -> None:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"Unsupported trace event type: {event_type}"
        )

    if step_number < 0:
        raise ValueError("Step number cannot be negative.")

    event = {
        "event_id": len(trace["events"]) + 1,
        "timestamp": utc_now(),
        "step_number": step_number,
        "event_type": event_type,
        "details": details or {},
    }

    trace["events"].append(event)


def finalize_trace(
    trace: dict[str, Any],
    final_status: str,
    final_answer: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    if final_status not in FINAL_STATUSES:
        raise ValueError(
            f"Unsupported final status: {final_status}"
        )

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative.")

    trace["finished_at"] = utc_now()
    trace["final_status"] = final_status
    trace["final_answer"] = final_answer
    trace["token_usage"] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def validate_trace(trace: dict[str, Any]) -> None:
    required_fields = {
        "trace_id",
        "workflow_id",
        "framework",
        "configuration",
        "repeat_number",
        "model",
        "temperature",
        "started_at",
        "finished_at",
        "final_status",
        "final_answer",
        "token_usage",
        "events",
    }

    missing_fields = sorted(required_fields - trace.keys())

    if missing_fields:
        raise ValueError(
            "Trace is missing required fields: "
            + ", ".join(missing_fields)
        )

    event_ids = [
        event["event_id"]
        for event in trace["events"]
    ]

    expected_ids = list(range(1, len(event_ids) + 1))

    if event_ids != expected_ids:
        raise ValueError(
            "Trace event IDs are not sequential."
        )


def summarize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": trace["trace_id"],
        "workflow_id": trace["workflow_id"],
        "framework": trace["framework"],
        "configuration": trace["configuration"],
        "event_count": len(trace["events"]),
        "event_types": [
            event["event_type"]
            for event in trace["events"]
        ],
        "final_status": trace["final_status"],
        "total_tokens": trace["token_usage"]["total_tokens"],
        "trace_validation_passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and validate a benchmark_v2 trace."
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

    trace = create_trace(
        workflow_id=scenario["workflow_id"],
        framework="validation_only",
        configuration="native",
        repeat_number=1,
        model="MODEL_NOT_CALLED",
        temperature=0.0,
    )

    add_event(
        trace=trace,
        event_type="run_started",
        step_number=0,
        details={
            "message": "Trace validation started.",
            "api_call_made": False,
        },
    )

    add_event(
        trace=trace,
        event_type="run_completed",
        step_number=1,
        details={
            "message": "Trace validation completed.",
            "api_call_made": False,
        },
    )

    finalize_trace(
        trace=trace,
        final_status="completed",
        final_answer="Validation only.",
    )

    validate_trace(trace)

    print(json.dumps(summarize_trace(trace), indent=2))
    print("TRACE VALIDATION PASSED — no API call was made.")


if __name__ == "__main__":
    main()