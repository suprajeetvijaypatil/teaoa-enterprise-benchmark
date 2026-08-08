from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import load_scenario
from runner.execution_trace_v2 import (
    FINAL_STATUSES,
    create_trace,
    finalize_trace,
    validate_trace,
)
from runner.scorer_v2 import score_trace
from runner.teaoa_controller_v2 import (
    execute_controlled_tool,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_RESULT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "second_turn_paid_result.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "second_turn_pipeline_replay.json"
)


def load_paid_result() -> dict[str, Any]:
    if not SOURCE_RESULT_PATH.is_file():
        raise FileNotFoundError(
            f"Paid smoke-test result not found: "
            f"{SOURCE_RESULT_PATH}"
        )

    with SOURCE_RESULT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def select_final_status(
    adapter_result: dict[str, Any],
    tool_results: list[dict[str, Any]],
) -> str:
    model_status = str(
        adapter_result.get("final_status", "")
    ).lower()

    completion_statuses = {
        "completed",
        "success",
        "succeeded",
        "resolved",
    }

    if (
        model_status in completion_statuses
        and tool_results
    ):
        preferred_status = "completed"
    else:
        preferred_status = "failed"

    if preferred_status in FINAL_STATUSES:
        return preferred_status

    for fallback in [
        "blocked",
        "incomplete",
        "failed",
        "completed",
    ]:
        if fallback in FINAL_STATUSES:
            return fallback

    raise RuntimeError(
        "No compatible final trace status is available."
    )


def replay_saved_result() -> dict[str, Any]:
    paid_output = load_paid_result()
    adapter_result = paid_output["result"]

    workflow_id = adapter_result["workflow_id"]
    scenario = load_scenario(workflow_id)

    trace = create_trace(
        workflow_id=workflow_id,
        framework=adapter_result["framework"],
        configuration=adapter_result[
            "configuration"
        ],
        repeat_number=1,
        model=adapter_result["model"],
        temperature=float(
            paid_output.get("temperature", 0.0)
        ),
    )

    proposed_tools = adapter_result.get(
        "proposed_tools",
        [],
    )

    tool_results = []

    for step_number, proposal in enumerate(
        proposed_tools,
        start=1,
    ):
        if not isinstance(proposal, dict):
            raise TypeError(
                "Each proposed tool must be an object."
            )

        tool_name = (
            proposal.get("tool")
            or proposal.get("tool_name")
            or proposal.get("name")
        )

        if not tool_name:
            raise ValueError(
                f"Tool proposal {step_number} has "
                "no tool name."
            )

        arguments = proposal.get("arguments", {})

        if not isinstance(arguments, dict):
            raise TypeError(
                f"Arguments for {tool_name} must "
                "be an object."
            )

        controlled_result = execute_controlled_tool(
            trace=trace,
            scenario=scenario,
            tool_name=str(tool_name),
            step_number=step_number,
            arguments=arguments,
            approval_granted=True,
            forced_failures=0,
        )

        tool_results.append(controlled_result)

    final_status = select_final_status(
        adapter_result,
        tool_results,
    )

    token_usage = adapter_result.get(
        "token_usage",
        {},
    )

    finalize_trace(
        trace=trace,
        final_status=final_status,
        final_answer=adapter_result.get(
            "output_text"
        ),
        input_tokens=int(
            token_usage.get("input_tokens", 0)
            or 0
        ),
        output_tokens=int(
            token_usage.get("output_tokens", 0)
            or 0
        ),
    )

    validate_trace(trace)

    score = score_trace(
        scenario=scenario,
        trace=trace,
    )

    return {
        "validation_type": (
            "posthoc_paid_smoke_pipeline_replay"
        ),
        "official_experiment_result": False,
        "new_api_call_made": False,
        "source_result": str(SOURCE_RESULT_PATH),
        "workflow_id": workflow_id,
        "framework": adapter_result["framework"],
        "configuration": adapter_result[
            "configuration"
        ],
        "model_final_status": adapter_result[
            "final_status"
        ],
        "replay_final_status": final_status,
        "proposed_tool_count": len(
            proposed_tools
        ),
        "executed_tool_count": len(
            tool_results
        ),
        "tool_results": tool_results,
        "trace": trace,
        "score": score,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the saved paid smoke-test result "
            "through the local policy, simulator, trace "
            "and scorer pipeline."
        )
    )

    parser.add_argument(
        "--confirm-no-api",
        action="store_true",
        help=(
            "Confirm that only the saved result "
            "will be processed."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.confirm_no_api:
        raise RuntimeError(
            "Use --confirm-no-api to run the "
            "local replay."
        )

    replay = replay_saved_result()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(replay, file, indent=2)

    print(json.dumps(replay, indent=2))
    print(f"Report: {OUTPUT_PATH}")
    print(
        "PAID SMOKE PIPELINE REPLAY PASSED — "
        "no new API call was made."
    )


if __name__ == "__main__":
    main()