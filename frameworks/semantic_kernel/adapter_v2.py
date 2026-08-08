from __future__ import annotations

import argparse
import asyncio
import json
import inspect
from time import perf_counter
from typing import Any
from uuid import uuid4

import semantic_kernel
from pydantic import BaseModel, Field

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)
from runner.model_context_v2 import build_model_context


class SemanticKernelToolProposal(BaseModel):
    tool_name: str
    arguments_json: str


class SemanticKernelPolicyDecision(BaseModel):
    decision: str
    reason: str


class SemanticKernelExecutionOutput(BaseModel):
    completed_steps: list[str] = Field(
        default_factory=list
    )

    proposed_tools: list[
        SemanticKernelToolProposal
    ] = Field(default_factory=list)

    policy_decisions: list[
        SemanticKernelPolicyDecision
    ] = Field(default_factory=list)

    final_status: str
    final_answer: str
    domain_validation_passed: bool = False


def build_instructions() -> str:
    return (
        "You are an enterprise workflow agent "
        "participating in a controlled benchmark.\n"
        "Follow only the supplied task context.\n"
        "Use only allowed tools and never use "
        "forbidden tools.\n"
        "Do not invent successful tool results.\n"
        "Record proposed tools and policy "
        "decisions explicitly.\n"
        "For each proposed tool, place its name "
        "in tool_name and encode its arguments "
        "as a valid JSON object string in "
        "arguments_json.\n"
        "Example arguments_json: "
        "\"{\\\"ticket_id\\\": "
        "\\\"TICKET-1001\\\"}\".\n"
        "For every policy decision, provide both "
        "decision and reason.\n"
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
            "Semantic Kernel adapter dry-run validation only."
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
            "sdk": "semantic-kernel",
            "sdk_version": "1.44.0",
            "agent_type": "ChatCompletionAgent",
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def parse_structured_content(
    content: Any,
) -> SemanticKernelExecutionOutput:
    if isinstance(content, SemanticKernelExecutionOutput):
        return content

    if isinstance(content, dict):
        return SemanticKernelExecutionOutput.model_validate(content)

    if hasattr(content, "model_dump"):
        return SemanticKernelExecutionOutput.model_validate(
            content.model_dump()
        )

    return SemanticKernelExecutionOutput.model_validate_json(
        str(content)
    )


def extract_token_usage(
    response: Any,
) -> dict[str, int]:
    def read_value(
        source: Any,
        *names: str,
    ) -> int:
        for name in names:
            if isinstance(source, dict):
                value = source.get(name)
            else:
                value = getattr(
                    source,
                    name,
                    None,
                )

            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue

        return 0

    response_message = getattr(
        response,
        "message",
        None,
    )

    response_content = getattr(
        response,
        "content",
        None,
    )

    candidates = [
        response_message,
        response_content,
        response,
    ]

    for candidate in candidates:
        if candidate is None:
            continue

        metadata = getattr(
            candidate,
            "metadata",
            None,
        )

        if not isinstance(metadata, dict):
            continue

        usage = (
            metadata.get("usage")
            or metadata.get("token_usage")
            or metadata.get("usage_metadata")
        )

        if usage is None:
            continue

        input_tokens = read_value(
            usage,
            "prompt_tokens",
            "input_tokens",
        )

        output_tokens = read_value(
            usage,
            "completion_tokens",
            "output_tokens",
        )

        total_tokens = read_value(
            usage,
            "total_tokens",
        )

        if total_tokens == 0:
            total_tokens = (
                input_tokens + output_tokens
            )

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

def convert_proposed_tools(
    proposals: list[
        SemanticKernelToolProposal
    ],
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
    decisions: list[
        SemanticKernelPolicyDecision
    ],
) -> list[dict[str, Any]]:
    return [
        {
            "decision": item.decision,
            "reason": item.reason,
        }
        for item in decisions
    ]


async def execute_semantic_kernel_async(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "semantic_kernel":
        raise ValueError(
            "Semantic Kernel adapter received the wrong framework: "
            f"{request.framework}"
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "REAL API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after budget approval."
        )

    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai.open_ai import (
        OpenAIChatCompletion,
        OpenAIChatPromptExecutionSettings,
    )
    from semantic_kernel.functions import KernelArguments

    settings = OpenAIChatPromptExecutionSettings(
        response_format=SemanticKernelExecutionOutput,
    )

    service = OpenAIChatCompletion(
        ai_model_id=request.model,
    )

    agent = ChatCompletionAgent(
        service=service,
        name="TEAOAEnterpriseAgent",
        instructions=build_instructions(),
        arguments=KernelArguments(settings=settings),
    )

    started = perf_counter()

    try:
        response = await agent.get_response(
            messages=build_task_input(
                request
            )
        )

    finally:
        service_client = getattr(
            service,
            "client",
            None,
        )

        close_method = getattr(
            service_client,
            "close",
            None,
        )

        if callable(close_method):
            try:
                close_result = close_method()

                if inspect.isawaitable(
                    close_result
                ):
                    await close_result

            except Exception:
                pass

    latency_seconds = (
        perf_counter() - started
    )

    response_message = getattr(
        response,
        "message",
        response,
    )

    response_content = getattr(
        response_message,
        "content",
        response_message,
    )

    if not isinstance(
        response_content,
        (
            str,
            dict,
            SemanticKernelExecutionOutput,
        ),
    ):
        response_content = getattr(
            response_content,
            "content",
            response_content,
        )

    structured = parse_structured_content(
        response_content
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
        token_usage=extract_token_usage(response),
        metadata={
            "sdk": "semantic-kernel",
            "sdk_version": "1.44.0",
            "agent_type": "ChatCompletionAgent",
            "domain_validation_passed": (
                structured.domain_validation_passed
            ),
            "real_execution_enabled": True,
            "api_call_made": True,
        },
    )

    result.validate()
    return result


def execute_semantic_kernel(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    return asyncio.run(
        execute_semantic_kernel_async(
            request,
            allow_api_call=allow_api_call,
        )
    )


def build_validation_request() -> AdapterRequest:
    scenario = load_scenario("CS-001")
    model_context = build_model_context(scenario)

    return AdapterRequest(
        run_id=f"semantic-kernel-dry-{uuid4().hex[:8]}",
        framework="semantic_kernel",
        workflow_id="CS-001",
        configuration="native",
        model="MODEL_NOT_CALLED_IN_DRY_RUN",
        temperature=0.0,
        model_context=model_context,
        dry_run=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the locked Semantic Kernel V2 adapter."
        )
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
    result = execute_semantic_kernel(
        request,
        allow_api_call=False,
    )

    print(json.dumps(result.to_dict(), indent=2))
    print(
        "SEMANTIC KERNEL ADAPTER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()