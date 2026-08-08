from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_scenario,
)

from runner.execution_trace_v2 import (
    add_event,
    create_trace,
    finalize_trace,
    validate_trace,
)

from runner.model_context_v2 import (
    build_model_context,
)

from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
)
from runner.framework_adapter_registry_v2 import (
    dispatch_adapter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


SUPPORTED_FRAMEWORKS = {
    "langgraph",
    "crewai",
    "autogen",
    "semantic_kernel",
    "openai_agents",
    "google_adk",
}


def resolve_task_path(
    task_value: str,
) -> Path:
    task_path = Path(task_value)

    if not task_path.is_absolute():
        task_path = PROJECT_ROOT / task_path

    task_path = task_path.resolve()

    if not task_path.is_file():
        raise FileNotFoundError(
            f"Workflow file not found: {task_path}"
        )

    if task_path.suffix.lower() != ".json":
        raise ValueError(
            "The workflow file must be JSON."
        )

    return task_path


def validate_settings(
    framework: str,
    configuration: str,
    repeat: int,
    temperature: float,
) -> None:
    if framework not in SUPPORTED_FRAMEWORKS:
        raise ValueError(
            f"Unsupported framework: {framework}"
        )

    if configuration not in {
        "native",
        "teaoa",
    }:
        raise ValueError(
            "Configuration must be native or teaoa."
        )

    if repeat < 1:
        raise ValueError(
            "Repeat must be at least 1."
        )

    if not 0.0 <= temperature <= 2.0:
        raise ValueError(
            "Temperature must be between "
            "0.0 and 2.0."
        )


def validate_model_context(
    context: dict[str, Any],
) -> None:
    forbidden_fields = {
        "ground_truth",
        "required_steps",
        "scoring_rules",
        "expected_outcome",
        "maximum_score",
        "expected_final_status",
        "expected_policy_decision",
    }

    leaked_fields = sorted(
        forbidden_fields & set(context)
    )

    if leaked_fields:
        raise ValueError(
            "Evaluation data leaked into model "
            "context: "
            + ", ".join(leaked_fields)
        )


def create_dry_run_trace(
    scenario: dict[str, Any],
    framework: str,
    configuration: str,
    repeat_number: int,
    model: str,
    temperature: float,
    context: dict[str, Any],
) -> dict[str, Any]:
    trace = create_trace(
        workflow_id=scenario["workflow_id"],
        framework=framework,
        configuration=configuration,
        repeat_number=repeat_number,
        model=model,
        temperature=temperature,
    )

    add_event(
        trace=trace,
        event_type="run_started",
        step_number=0,
        details={
            "dry_run": True,
            "api_call_made": False,
            "context_fields": sorted(
                context.keys()
            ),
        },
    )

    add_event(
        trace=trace,
        event_type="run_completed",
        step_number=1,
        details={
            "dry_run": True,
            "api_call_made": False,
            "message": (
                "Configuration validation "
                "completed."
            ),
        },
    )

    finalize_trace(
        trace=trace,
        final_status="completed",
        final_answer=(
            "Dry-run validation only. "
            "No model was called."
        ),
    )

    validate_trace(trace)

    return trace


def run_shared_experiment(
    framework: str,
    task: str,
    configuration: str,
    repeat: int,
    model: str,
    temperature: float,
    dry_run: bool,
) -> dict[str, Any]:
    validate_settings(
        framework=framework,
        configuration=configuration,
        repeat=repeat,
        temperature=temperature,
    )

    if not dry_run:
        raise RuntimeError(
            "REAL V2 EXECUTION IS DISABLED. "
            "Use --dry-run."
        )

    task_path = resolve_task_path(task)
    workflow_id = task_path.stem

    scenario = load_scenario(workflow_id)
    context = build_model_context(scenario)

    validate_model_context(context)

    trace_summaries = []

    for repeat_number in range(
        1,
        repeat + 1,
    ):
        trace = create_dry_run_trace(
            scenario=scenario,
            framework=framework,
            configuration=configuration,
            repeat_number=repeat_number,
            model=model,
            temperature=temperature,
            context=context,
        )

        adapter_request = AdapterRequest(
            run_id=trace["trace_id"],
            framework=framework,
            workflow_id=workflow_id,
            configuration=configuration,
            model=model,
            temperature=temperature,
            model_context=context,
            dry_run=True,
        )

        adapter_result = dispatch_adapter(
            adapter_request,
            allow_api_call=False,
        )

        trace_summaries.append(
            {
                "trace_id": trace["trace_id"],
                "repeat_number": repeat_number,
                "event_count": len(trace["events"]),
                "final_status": trace["final_status"],
                "adapter_final_status": (
                    adapter_result.final_status
                ),
                "adapter_validated": True,
                "api_call_made": (
                    adapter_result.metadata.get(
                        "api_call_made"
                    )
                ),
                "token_usage": (
                    adapter_result.token_usage
                ),
                "adapter_result": (
                    adapter_result.to_dict()
                ),
            }
        )

    return {
        "framework": framework,
        "workflow_id": workflow_id,
        "task_path": str(task_path),
        "configuration": configuration,
        "repeat": repeat,
        "model": model,
        "temperature": temperature,
        "dry_run": True,
        "model_context_fields": sorted(
            context.keys()
        ),
        "ground_truth_exposed_to_model": False,
        "scoring_rules_exposed_to_model": False,
        "adapter_registry_connected": True,
        "api_call_made": False,
        "traces": trace_summaries,
    }
   

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the shared benchmark_v2 "
            "execution engine."
        )
    )

    parser.add_argument(
        "--framework",
        choices=sorted(SUPPORTED_FRAMEWORKS),
        required=True,
    )

    parser.add_argument(
        "--task",
        required=True,
    )

    parser.add_argument(
        "--configuration",
        choices=["native", "teaoa"],
        required=True,
    )

    parser.add_argument(
        "--repeat",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--model",
        required=True,
    )

    parser.add_argument(
        "--temperature",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = run_shared_experiment(
        framework=args.framework,
        task=args.task,
        configuration=args.configuration,
        repeat=args.repeat,
        model=args.model,
        temperature=args.temperature,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2))

    print(
        "SHARED V2 ENGINE PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()