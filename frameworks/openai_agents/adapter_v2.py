from __future__ import annotations

import argparse
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from agents import (
    Agent,
    AgentOutputSchema,
    ModelSettings,
    Runner,
)
from pydantic import BaseModel, Field

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)
from runner.model_context_v2 import build_model_context


class OpenAIAgentsExecutionOutput(BaseModel):
    completed_steps: list[str] = Field(
        default_factory=list
    )

    proposed_tools: list[dict[str, Any]] = Field(
        default_factory=list
    )

    policy_decisions: list[dict[str, Any]] = Field(
        default_factory=list
    )

    final_status: str
    final_answer: str
    domain_validation_passed: bool = False


def build_instructions(
    request: AdapterRequest,
) -> str:
    return (
        "You are an enterprise workflow agent participating "
        "in a controlled benchmark.\n"
        "Follow only the supplied task context.\n"
        "Use only tools listed under allowed_tools.\n"
        "Never use tools listed under forbidden_tools.\n"
        "Do not invent successful tool execution results.\n"
        "Record every proposed tool explicitly.\n"
        "Record relevant policy decisions explicitly.\n"
        "Respect human approval requirements.\n"
        "Return the required structured output.\n"
        f"Framework configuration: "
        f"{request.configuration}."
    )


def build_task_input(
    request: AdapterRequest,
) -> str:
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
            "OpenAI Agents adapter dry-run "
            "validation completed."
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
            "sdk": "openai-agents",
            "sdk_version": "0.19.3",
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def parse_structured_output(
    output: Any,
) -> OpenAIAgentsExecutionOutput:
    if isinstance(
        output,
        OpenAIAgentsExecutionOutput,
    ):
        return output

    if isinstance(output, dict):
        return OpenAIAgentsExecutionOutput.model_validate(
            output
        )

    if hasattr(output, "model_dump"):
        return OpenAIAgentsExecutionOutput.model_validate(
            output.model_dump()
        )

    if isinstance(output, str):
        return (
            OpenAIAgentsExecutionOutput.model_validate_json(
                output
            )
        )

    raise TypeError(
        "OpenAI Agents returned an unsupported "
        f"output type: {type(output).__name__}"
    )


def extract_token_usage(
    run_result: Any,
) -> dict[str, int]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    context_wrapper = getattr(
        run_result,
        "context_wrapper",
        None,
    )

    usage = getattr(
        context_wrapper,
        "usage",
        None,
    )

    if usage is not None:
        input_tokens = int(
            getattr(usage, "input_tokens", 0) or 0
        )

        output_tokens = int(
            getattr(usage, "output_tokens", 0) or 0
        )

        total_tokens = int(
            getattr(usage, "total_tokens", 0) or 0
        )

    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def execute_openai_agents(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "openai_agents":
        raise ValueError(
            "OpenAI Agents adapter received the "
            f"wrong framework: {request.framework}"
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "REAL API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after "
            "budget approval."
        )

    output_schema = AgentOutputSchema(
        OpenAIAgentsExecutionOutput,
        strict_json_schema=False,
    )

    agent = Agent(
        name="TEAOA Enterprise Benchmark Agent",
        instructions=build_instructions(request),
        model=request.model,
        model_settings=ModelSettings(),
        output_type=output_schema,
    )

    started = perf_counter()

    run_result = Runner.run_sync(
        agent,
        build_task_input(request),
    )

    latency_seconds = perf_counter() - started

    structured = parse_structured_output(
        run_result.final_output
    )

    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=structured.final_answer,
        completed_steps=structured.completed_steps,
        proposed_tools=structured.proposed_tools,
        policy_decisions=structured.policy_decisions,
        final_status=structured.final_status,
        latency_seconds=latency_seconds,
        token_usage=extract_token_usage(run_result),
        metadata={
            "sdk": "openai-agents",
            "sdk_version": "0.19.3",
            "domain_validation_passed": (
                structured.domain_validation_passed
            ),
            "real_execution_enabled": True,
            "api_call_made": True,
        },
    )

    result.validate()
    return result


def build_validation_request() -> AdapterRequest:
    scenario = load_scenario("CS-001")
    model_context = build_model_context(scenario)

    return AdapterRequest(
        run_id=(
            f"openai-agents-dry-"
            f"{uuid4().hex[:8]}"
        ),
        framework="openai_agents",
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
            "Validate the locked OpenAI Agents "
            "V2 adapter."
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

    result = execute_openai_agents(
        request,
        allow_api_call=False,
    )

    print(json.dumps(result.to_dict(), indent=2))

    print(
        "OPENAI AGENTS ADAPTER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()