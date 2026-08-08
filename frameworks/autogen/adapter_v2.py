from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel, Field

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)
from runner.model_context_v2 import build_model_context


class AutoGenToolProposal(BaseModel):
    tool_name: str
    arguments_json: str


class AutoGenPolicyDecision(BaseModel):
    decision: str
    reason: str


class AutoGenExecutionOutput(BaseModel):
    completed_steps: list[str] = Field(
        default_factory=list
    )

    proposed_tools: list[
        AutoGenToolProposal
    ] = Field(default_factory=list)

    policy_decisions: list[
        AutoGenPolicyDecision
    ] = Field(default_factory=list)

    final_status: str
    final_answer: str
    domain_validation_passed: bool = False


def build_system_message(
    request: AdapterRequest,
) -> str:
    return (
        "You are an enterprise workflow agent "
        "participating in a controlled benchmark.\n"
        "Follow only the supplied task context.\n"
        "Use only allowed tools and never use "
        "forbidden tools.\n"
        "Do not invent successful tool results.\n"
        "Record proposed tools and policy "
        "decisions explicitly.\n"
        "For each proposed tool, put its name in "
        "tool_name and encode its arguments as a "
        "valid JSON object string in "
        "arguments_json.\n"
        "Example arguments_json: "
        "\"{\\\"ticket_id\\\": "
        "\\\"TICKET-1001\\\"}\".\n"
        "For every policy decision, always provide "
        "both decision and reason.\n"
        "Return the required structured output."
    )


def build_task_input(request: AdapterRequest) -> str:
    payload = {
        "workflow_id": request.workflow_id,
        "configuration": request.configuration,
        "model_context": request.model_context,
    }

    return json.dumps(payload, indent=2)


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
            "AutoGen adapter dry-run validation completed."
        ),
        completed_steps=[],
        proposed_tools=[],
        policy_decisions=[],
        final_status="dry_run_passed",
        latency_seconds=0.0,
        token_usage={
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        metadata={
            "sdk": "autogen-agentchat",
            "sdk_version": "0.7.5",
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def extract_token_usage(task_result: Any) -> dict[str, int]:
    input_tokens = 0
    output_tokens = 0

    for message in task_result.messages:
        usage = getattr(message, "models_usage", None)

        if usage is None:
            continue

        input_tokens += int(
            getattr(usage, "prompt_tokens", 0) or 0
        )
        output_tokens += int(
            getattr(usage, "completion_tokens", 0) or 0
        )

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def parse_structured_content(
    content: Any,
) -> AutoGenExecutionOutput:
    if isinstance(content, AutoGenExecutionOutput):
        return content

    if isinstance(content, dict):
        return AutoGenExecutionOutput.model_validate(content)

    if hasattr(content, "model_dump"):
        return AutoGenExecutionOutput.model_validate(
            content.model_dump()
        )

    if isinstance(content, str):
        return AutoGenExecutionOutput.model_validate_json(content)

    raise TypeError(
        "AutoGen returned an unsupported final content type: "
        f"{type(content).__name__}"
    )

def convert_proposed_tools(
    proposals: list[AutoGenToolProposal],
) -> list[dict[str, Any]]:
    converted = []

    for proposal in proposals:
        try:
            arguments = json.loads(
                proposal.arguments_json
            )
        except json.JSONDecodeError:
            arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        converted.append(
            {
                "tool_name": proposal.tool_name,
                "arguments": arguments,
            }
        )

    return converted


def convert_policy_decisions(
    decisions: list[AutoGenPolicyDecision],
) -> list[dict[str, Any]]:
    return [
        {
            "decision": item.decision,
            "reason": item.reason,
        }
        for item in decisions
    ]


async def execute_autogen_async(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "autogen":
        raise ValueError(
            "AutoGen adapter received the wrong framework: "
            f"{request.framework}"
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "REAL API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after budget approval."
        )

    model_client = OpenAIChatCompletionClient(
        model=request.model,
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": True,
        },
        max_retries=0,
    )

    agent = AssistantAgent(
        name="teaoa_enterprise_agent",
        model_client=model_client,
        system_message=build_system_message(request),
        output_content_type=AutoGenExecutionOutput,
    )

    started = perf_counter()

    try:
        task_result = await agent.run(
            task=build_task_input(request)
        )
    finally:
        await model_client.close()

    latency_seconds = perf_counter() - started

    if not task_result.messages:
        raise RuntimeError(
            "AutoGen returned no messages."
        )

    final_message = task_result.messages[-1]
    structured = parse_structured_content(
        getattr(final_message, "content", None)
    )

    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=structured.final_answer,
        completed_steps=structured.completed_steps,
        proposed_tools=convert_proposed_tools(
            structured.proposed_tools
        ),
        policy_decisions=convert_policy_decisions(
            structured.policy_decisions
        ),
        final_status=structured.final_status,
        latency_seconds=latency_seconds,
        token_usage=extract_token_usage(task_result),
        metadata={
            "sdk": "autogen-agentchat",
            "sdk_version": "0.7.5",
            "domain_validation_passed": (
                structured.domain_validation_passed
            ),
            "real_execution_enabled": True,
            "api_call_made": True,
        },
    )

    result.validate()
    return result


def execute_autogen(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    return asyncio.run(
        execute_autogen_async(
            request,
            allow_api_call=allow_api_call,
        )
    )


def build_validation_request() -> AdapterRequest:
    scenario = load_scenario("CS-001")
    model_context = build_model_context(scenario)

    return AdapterRequest(
        run_id=f"autogen-dry-{uuid4().hex[:8]}",
        framework="autogen",
        workflow_id="CS-001",
        configuration="native",
        model="MODEL_NOT_CALLED_IN_DRY_RUN",
        temperature=0.0,
        model_context=model_context,
        dry_run=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the locked AutoGen V2 adapter."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without making an API call.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.dry_run:
        raise RuntimeError(
            "Only --dry-run is currently permitted."
        )

    request = build_validation_request()
    result = execute_autogen(
        request,
        allow_api_call=False,
    )

    print(json.dumps(result.to_dict(), indent=2))
    print("AUTOGEN ADAPTER PASSED — no API call was made.")


if __name__ == "__main__":
    main()