from __future__ import annotations

import argparse
import json
from json_repair import repair_json
from time import perf_counter
from typing import Any
from uuid import uuid4

from crewai import (
    Agent,
    Crew,
    LLM,
    Process,
    Task,
)

from pydantic import BaseModel, Field

from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)


class CrewAIExecutionOutput(BaseModel):
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


def normalize_model_name(
    model: str,
) -> str:
    if "/" in model:
        return model

    return f"openai/{model}"


def build_task_description(
    request: AdapterRequest,
) -> str:
    configuration_instruction = (
        "Apply explicit policy, approval, "
        "recovery and audit controls."
        if request.configuration == "teaoa"
        else
        "Use CrewAI's native reasoning and "
        "tool-selection behaviour."
    )

    payload = json.dumps(
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

    return (
        "Complete the enterprise workflow below.\n"
        "Use only allowed tools and never use "
        "forbidden or unknown tools.\n"
        "Do not invent successful tool results.\n"
        "Preserve the completed-step order.\n"
        "Propose only the next necessary tool or "
        "tools using proposed_tools.\n"
        "Each proposed tool should contain "
        "tool_name and arguments.\n"
        f"{configuration_instruction}\n\n"
        f"WORKFLOW INPUT:\n{payload}"
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
            "CrewAI adapter dry-run "
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
            "sdk": "crewai",
            "sdk_version": "1.15.2",
            "process": "sequential",
            "real_execution_enabled": False,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def extract_usage(
    crew: Crew,
) -> dict[str, int]:
    usage = getattr(
        crew,
        "usage_metrics",
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
            "prompt_tokens",
            0,
        )
        or 0
    )

    output_tokens = int(
        getattr(
            usage,
            "completion_tokens",
            0,
        )
        or 0
    )

    total_tokens = int(
        getattr(
            usage,
            "total_tokens",
            0,
        )
        or 0
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


def extract_json_object(
    raw_output: Any,
) -> dict[str, Any]:
    raw_text = str(raw_output).strip()

    if raw_text.startswith("```"):
        lines = raw_text.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        raw_text = "\n".join(lines).strip()

    object_start = raw_text.find("{")
    object_end = raw_text.rfind("}")

    if (
        object_start == -1
        or object_end == -1
        or object_end < object_start
    ):
        raise ValueError(
            "CrewAI did not return a JSON object."
        )

    json_text = raw_text[
        object_start:object_end + 1
    ]

    json_repaired = False

    try:
        parsed_data = json.loads(json_text)

    except json.JSONDecodeError:
        parsed_data = repair_json(
            json_text,
            return_objects=True,
        )

        json_repaired = True

    if not isinstance(parsed_data, dict):
        raise TypeError(
            "CrewAI JSON output must be an object."
        )

    parsed_data[
        "__json_repaired__"
    ] = json_repaired

    return parsed_data


def normalize_proposed_tools(
    value: Any,
) -> list[dict[str, Any]]:
    if value is None:
        return []

    if isinstance(value, dict):
        value = [value]

    if not isinstance(value, list):
        return []

    normalized_tools = []

    for item in value:
        if isinstance(item, str):
            normalized_tools.append(
                {
                    "tool_name": item,
                    "arguments": {},
                }
            )

        elif isinstance(item, dict):
            tool_name = (
                item.get("tool_name")
                or item.get("tool")
                or item.get("name")
            )

            if not tool_name:
                continue

            arguments = item.get(
                "arguments",
                {},
            )

            if not isinstance(arguments, dict):
                arguments = {}

            normalized_tools.append(
                {
                    **item,
                    "tool_name": str(tool_name),
                    "arguments": arguments,
                }
            )

    return normalized_tools


def normalize_policy_decisions(
    value: Any,
) -> list[dict[str, Any]]:
    if value is None:
        return []

    if isinstance(value, (str, dict)):
        value = [value]

    if not isinstance(value, list):
        return []

    normalized_decisions = []

    for item in value:
        if isinstance(item, str):
            normalized_decisions.append(
                {
                    "decision": item,
                }
            )

        elif isinstance(item, dict):
            normalized_decisions.append(item)

    return normalized_decisions


def normalize_completed_steps(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (str, dict)):
        value = [value]

    if not isinstance(value, list):
        return []

    normalized_steps = []

    for item in value:
        if isinstance(item, str):
            normalized_steps.append(item)

        elif isinstance(item, dict):
            step_value = (
                item.get("completed_step")
                or item.get("step_name")
                or item.get("action")
                or item.get("tool_name")
                or item.get("tool")
                or item.get("name")
                or item.get("description")
            )

            if step_value is not None:
                normalized_steps.append(
                    str(step_value)
                )

    return normalized_steps


def normalize_execution_output(
    parsed_data: dict[str, Any],
) -> CrewAIExecutionOutput:
    normalized_data = dict(parsed_data)

    normalized_data["completed_steps"] = (
        normalize_completed_steps(
            normalized_data.get(
                "completed_steps",
                [],
            )
        )
    )

    normalized_data["proposed_tools"] = (
        normalize_proposed_tools(
            normalized_data.get(
                "proposed_tools",
                [],
            )
        )
    )

    normalized_data["policy_decisions"] = (
        normalize_policy_decisions(
            normalized_data.get(
                "policy_decisions",
                [],
            )
        )
    )

    final_status = normalized_data.get(
        "final_status",
        "in_progress",
    )

    if not isinstance(final_status, str):
        final_status = str(final_status)

    normalized_data["final_status"] = (
        final_status
    )

    final_answer = normalized_data.get(
        "final_answer",
        "",
    )

    if not isinstance(final_answer, str):
        final_answer = str(final_answer)

    normalized_data["final_answer"] = (
        final_answer
    )

    domain_validation = normalized_data.get(
        "domain_validation_passed",
        False,
    )

    if isinstance(domain_validation, str):
        domain_validation = (
            domain_validation
            .strip()
            .lower()
            in {
                "true",
                "yes",
                "passed",
                "success",
            }
        )

    normalized_data[
        "domain_validation_passed"
    ] = bool(domain_validation)

    return CrewAIExecutionOutput.model_validate(
        normalized_data
    )


def execute_crewai(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if request.framework != "crewai":
        raise ValueError(
            "This adapter only supports crewai."
        )

    if request.dry_run:
        return create_dry_run_result(request)

    if not allow_api_call:
        raise RuntimeError(
            "CREWAI API EXECUTION IS LOCKED. "
            "Set allow_api_call=True only after "
            "budget approval."
        )

    llm = LLM(
        model=normalize_model_name(
            request.model
        ),
    )

    enterprise_agent = Agent(
        role="Enterprise Workflow Agent",
        goal=(
            "Complete enterprise workflows "
            "accurately, safely and audibly."
        ),
        backstory=(
            "You are an enterprise operations "
            "specialist who follows tool, policy, "
            "approval and recovery constraints."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_retry_limit=0,
        max_iter=1,
    )

    workflow_task = Task(
        description=build_task_description(
            request
        ),
        expected_output=(
            "Return only one valid JSON object "
            "with these fields: completed_steps "
            "(array), proposed_tools (array), "
            "policy_decisions (array), "
            "final_status (string), final_answer "
            "(string), and "
            "domain_validation_passed (boolean). "
            "Do not use Markdown or code fences."
        ),
        agent=enterprise_agent,
    )

    crew = Crew(
        agents=[enterprise_agent],
        tasks=[workflow_task],
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
        tracing=False,
    )

    started = perf_counter()

    crew_output = crew.kickoff()

    latency_seconds = (
        perf_counter() - started
    )

    raw_output = getattr(
        crew_output,
        "raw",
        str(crew_output),
    )

    parsed_data = extract_json_object(
        raw_output
    )

    json_repaired = bool(
        parsed_data.pop(
            "__json_repaired__",
            False,
        )
    )

    structured_output = (
        normalize_execution_output(
            parsed_data
        )
    )

    token_usage = extract_usage(crew)

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
            "sdk": "crewai",
            "sdk_version": "1.15.2",
            "process": "sequential",
            "structured_output": True,
            "json_repaired": json_repaired,
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


def build_validation_request() -> AdapterRequest:
    request = AdapterRequest(
        run_id=str(uuid4()),
        framework="crewai",
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
            "Validate the CrewAI "
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

    result = execute_crewai(
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
        "CREWAI ADAPTER PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()