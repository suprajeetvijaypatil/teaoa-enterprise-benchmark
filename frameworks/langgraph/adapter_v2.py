from __future__ import annotations

import argparse
import importlib.util
import json
from time import perf_counter
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from pydantic import BaseModel, Field

from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)


class LangGraphExecutionOutput(BaseModel):
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


class GraphState(TypedDict):
    request: AdapterRequest

    structured_response: NotRequired[
        dict[str, Any]
    ]


def provider_available() -> bool:
    return (
        importlib.util.find_spec(
            "langchain_openai"
        )
        is not None
    )


def build_system_instruction(
    request: AdapterRequest,
) -> str:
    configuration_instruction = (
        "Apply explicit policy checks, approval "
        "controls, recovery and audit reasoning."
        if request.configuration == "teaoa"
        else
        "Use native LangGraph reasoning and "
        "tool-selection behaviour."
    )

    return (
        "You are an enterprise workflow agent. "
        "Use only allowed tools. Never use a "
        "forbidden or unknown tool. Do not invent "
        "successful tool results. Preserve the "
        "completed-step order. "
        f"{configuration_instruction} "
        "Return completed steps, proposed tools, "
        "policy decisions, final status, final "
        "answer and domain-validation status."
    )


def build_user_input(
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
            "LangGraph adapter dry-run "
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
            "sdk": "langgraph",
            "sdk_version": "1.2.9",
            "provider": "langchain-openai",
            "provider_available": (
                provider_available()
            ),
            "graph_compiled": False,
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def extract_usage(
    raw_message: Any,
) -> dict[str, int]:
    usage_metadata = getattr(
        raw_message,
        "usage_metadata",
        None,
    )

    if isinstance(usage_metadata, dict):
        input_tokens = int(
            usage_metadata.get(
                "input_tokens",
                0,
            )
            or 0
        )

        output_tokens = int(
            usage_metadata.get(
                "output_tokens",
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

    response_metadata = getattr(
        raw_message,
        "response_metadata",
        {},
    )

    token_usage = response_metadata.get(
        "token_usage",
        {},
    )

    input_tokens = int(
        token_usage.get(
            "prompt_tokens",
            0,
        )
        or 0
    )

    output_tokens = int(
        token_usage.get(
            "completion_tokens",
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


def execute_langgraph(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "langgraph":
        raise ValueError(
            "This adapter only supports "
            "langgraph."
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "LANGGRAPH API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after "
            "budget approval."
        )

    if not provider_available():
        raise RuntimeError(
            "Real LangGraph execution requires "
            "the langchain-openai package."
        )

    from langchain_core.messages import (
        HumanMessage,
        SystemMessage,
    )

    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=request.model,
        reasoning_effort="none",
    )

    structured_model = (
        model.with_structured_output(
            LangGraphExecutionOutput,
            method="function_calling",
            include_raw=True,
        )
    )

    def agent_node(
        state: GraphState,
    ) -> dict[str, Any]:
        active_request = state["request"]

        response = structured_model.invoke(
            [
                SystemMessage(
                    content=(
                        build_system_instruction(
                            active_request
                        )
                    )
                ),
                HumanMessage(
                    content=build_user_input(
                        active_request
                    )
                ),
            ]
        )

        return {
            "structured_response": response
        }

    builder = StateGraph(GraphState)

    builder.add_node(
        "enterprise_agent",
        agent_node,
    )

    builder.add_edge(
        START,
        "enterprise_agent",
    )

    builder.add_edge(
        "enterprise_agent",
        END,
    )

    graph = builder.compile()

    started = perf_counter()

    final_state = graph.invoke(
        {"request": request}
    )

    latency_seconds = (
        perf_counter() - started
    )

    response = final_state[
        "structured_response"
    ]

    parsed = response.get("parsed")

    if not isinstance(
        parsed,
        LangGraphExecutionOutput,
    ):
        parsed = (
            LangGraphExecutionOutput
            .model_validate(parsed)
        )

    raw_message = response.get("raw")
    token_usage = extract_usage(raw_message)

    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=parsed.final_answer,
        completed_steps=parsed.completed_steps,
        proposed_tools=parsed.proposed_tools,
        policy_decisions=(
            parsed.policy_decisions
        ),
        final_status=parsed.final_status,
        latency_seconds=latency_seconds,
        token_usage=token_usage,
        metadata={
            "sdk": "langgraph",
            "sdk_version": "1.2.9",
            "provider": "langchain-openai",
            "structured_output": True,
            "domain_validation_passed": (
                parsed.domain_validation_passed
            ),
            "graph_compiled": True,
            "real_execution_enabled": True,
            "api_call_made": True,
        },
    )

    result.validate()
    return result


def build_validation_request() -> AdapterRequest:
    request = AdapterRequest(
        run_id=str(uuid4()),
        framework="langgraph",
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
            "Validate the LangGraph "
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

    result = execute_langgraph(
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
        "LANGGRAPH ADAPTER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()