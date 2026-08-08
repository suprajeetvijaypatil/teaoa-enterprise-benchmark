from __future__ import annotations

import argparse
import asyncio
import json
import os
from time import perf_counter
from typing import Any
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import (
    InMemorySessionService,
)
from google.genai import types
from pydantic import BaseModel, Field

from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)


class ADKExecutionOutput(BaseModel):
    completed_steps: list[str] = Field(
        default_factory=list
    )

    proposed_tools: list[
        dict[str, Any]
    ] = Field(default_factory=list)

    policy_decisions: list[
        dict[str, Any]
    ] = Field(default_factory=list)

    final_status: str

    final_answer: str

    domain_validation_passed: bool = False


def build_agent_instruction(
    request: AdapterRequest,
) -> str:
    configuration_instruction = (
        "Apply explicit policy checks, approval "
        "controls, recovery and audit reasoning."
        if request.configuration == "teaoa"
        else
        "Use the framework's native reasoning "
        "and tool-selection behaviour."
    )

    return (
        "You are an enterprise workflow agent. "
        "Use only allowed tools and never use "
        "forbidden or unknown tools. "
        "Do not invent successful tool results. "
        "Preserve the completed-step order. "
        f"{configuration_instruction} "
        "Return JSON containing completed_steps, "
        "proposed_tools, policy_decisions, "
        "final_status, final_answer and "
        "domain_validation_passed."
    )


def build_agent_input(
    request: AdapterRequest,
) -> str:
    return json.dumps(
        {
            "workflow_id": request.workflow_id,
            "configuration": (
                request.configuration
            ),
            "model_context": (
                request.model_context
            ),
        },
        indent=2,
        ensure_ascii=False,
    )


def create_dry_run_result(
    request: AdapterRequest,
) -> AdapterResult:
    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=(
            "Google ADK adapter dry-run "
            "validation only."
        ),
        completed_steps=[],
        proposed_tools=[],
        policy_decisions=[],
        final_status="dry_run_validated",
        latency_seconds=0.0,
        token_usage={
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        metadata={
            "sdk": "google-adk",
            "sdk_version": "2.6.2",
            "structured_output": True,
            "google_key_configured": bool(
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
            ),
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def extract_event_text(event: Any) -> str:
    content = getattr(event, "content", None)

    if content is None:
        return ""

    parts = getattr(content, "parts", None)

    if not parts:
        return ""

    text_parts = []

    for part in parts:
        text = getattr(part, "text", None)

        if text:
            text_parts.append(text)

    return "".join(text_parts)


def extract_usage(
    event: Any,
) -> dict[str, int]:
    usage = getattr(
        event,
        "usage_metadata",
        None,
    )

    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    input_tokens = int(
        getattr(
            usage,
            "prompt_token_count",
            0,
        )
        or 0
    )

    output_tokens = int(
        getattr(
            usage,
            "candidates_token_count",
            0,
        )
        or 0
    )

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": (
            input_tokens + output_tokens
        ),
    }


async def execute_google_adk_async(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "google_adk":
        raise ValueError(
            "This adapter only supports "
            "google_adk."
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "GOOGLE ADK API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after "
            "access and budget approval."
        )

    google_key_available = bool(
        os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )

    if not google_key_available:
        raise RuntimeError(
            "Google ADK execution requires "
            "GOOGLE_API_KEY or GEMINI_API_KEY."
        )

    app_name = "teaoa_benchmark_v2"
    user_id = "benchmark_user"
    session_id = request.run_id

    agent = Agent(
        name="teaoa_enterprise_agent",
        model=request.model,
        instruction=build_agent_instruction(
            request
        ),
        output_schema=ADKExecutionOutput,
        generate_content_config=(
            types.GenerateContentConfig(
                temperature=request.temperature,
            )
        ),
    )

    session_service = InMemorySessionService()

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        app_name=app_name,
        agent=agent,
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=build_agent_input(request)
            )
        ],
    )

    started = perf_counter()
    final_text = ""
    token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        event_text = extract_event_text(event)

        if event_text:
            final_text = event_text

        event_usage = extract_usage(event)

        if event_usage["total_tokens"] > 0:
            token_usage = event_usage

    latency_seconds = (
        perf_counter() - started
    )

    structured_output = (
        ADKExecutionOutput.model_validate_json(
            final_text
        )
    )

    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=(
            structured_output.final_answer
        ),
        completed_steps=(
            structured_output.completed_steps
        ),
        proposed_tools=(
            structured_output.proposed_tools
        ),
        policy_decisions=(
            structured_output.policy_decisions
        ),
        final_status=(
            structured_output.final_status
        ),
        latency_seconds=latency_seconds,
        token_usage=token_usage,
        metadata={
            "sdk": "google-adk",
            "sdk_version": "2.6.2",
            "structured_output": True,
            "domain_validation_passed": (
                structured_output
                .domain_validation_passed
            ),
            "real_execution_enabled": True,
            "api_call_made": True,
        },
    )

    result.validate()
    return result


def execute_google_adk(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    return asyncio.run(
        execute_google_adk_async(
            request=request,
            allow_api_call=allow_api_call,
        )
    )


def build_validation_request() -> AdapterRequest:
    request = AdapterRequest(
        run_id=str(uuid4()),
        framework="google_adk",
        workflow_id="CS-001",
        configuration="teaoa",
        model="MODEL_NOT_CALLED",
        temperature=0.0,
        model_context={
            "workflow_id": "CS-001",
            "domain": "customer_support",
            "scenario": "Validation only.",
            "goal": "Validate the adapter.",
            "task_instruction": (
                "Do not call a model."
            ),
            "prompt": "Validation only.",
            "dataset": {
                "dataset_id": "validation",
            },
            "allowed_tools": [],
            "forbidden_tools": [],
            "risk_class": "validation",
            "human_approval_required": False,
            "sla_seconds": 0,
            "retry_limit": 0,
        },
        dry_run=True,
    )

    request.validate()
    return request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the Google ADK "
            "benchmark_v2 adapter."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="Validate without calling an API.",
    )

    return parser.parse_args()


def main() -> None:
    parse_args()

    request = build_validation_request()

    result = execute_google_adk(
        request=request,
        allow_api_call=False,
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        "GOOGLE ADK ADAPTER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()