from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import load_scenario
from runner.execution_trace_v2 import (
    create_trace,
    finalize_trace,
    validate_trace,
)
from runner.scorer_v2 import score_trace
from runner.teaoa_controller_v2 import (
    execute_controlled_tool,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results" / "benchmark_v2"

AUTOMATIC_PATH = (
    RESULTS_ROOT
    / "automatic_multi_turn_paid.json"
)

TURN_SEVEN_PATH = (
    RESULTS_ROOT
    / "finalization_turn_paid.json"
)

TURN_EIGHT_PATH = (
    RESULTS_ROOT
    / "completion_confirmation_paid.json"
)

OUTPUT_PATH = (
    RESULTS_ROOT
    / "cs001_native_completed_smoke.json"
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required result not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def get_tool_name(
    proposal: dict[str, Any],
) -> str:
    tool_name = (
        proposal.get("tool")
        or proposal.get("tool_name")
        or proposal.get("name")
    )

    if not tool_name:
        raise ValueError(
            "Tool proposal has no tool name."
        )

    return str(tool_name)


def collect_tool_proposals(
    automatic: dict[str, Any],
    turn_seven: dict[str, Any],
) -> list[dict[str, Any]]:
    proposals = []

    for item in automatic.get(
        "execution_history",
        [],
    ):
        proposals.append(
            {
                "tool_name": item["tool_name"],
                "arguments": item.get(
                    "arguments",
                    {},
                ),
                "source_turn": item.get(
                    "turn_number"
                ),
            }
        )

    seventh_proposals = (
        turn_seven["result"].get(
            "proposed_tools",
            [],
        )
    )

    if len(seventh_proposals) != 1:
        raise ValueError(
            "Expected exactly one tool proposal "
            "from turn seven."
        )

    seventh = seventh_proposals[0]

    proposals.append(
        {
            "tool_name": get_tool_name(seventh),
            "arguments": seventh.get(
                "arguments",
                {},
            ),
            "source_turn": 7,
        }
    )

    if len(proposals) != 7:
        raise ValueError(
            f"Expected seven tools, found "
            f"{len(proposals)}."
        )

    return proposals


def calculate_tokens(
    automatic: dict[str, Any],
    turn_seven: dict[str, Any],
    turn_eight: dict[str, Any],
) -> dict[str, int]:
    automatic_usage = automatic[
        "total_token_usage"
    ]

    turn_seven_usage = turn_seven[
        "result"
    ]["token_usage"]

    turn_eight_usage = turn_eight[
        "result"
    ]["token_usage"]

    input_tokens = sum(
        int(usage.get("input_tokens", 0) or 0)
        for usage in [
            automatic_usage,
            turn_seven_usage,
            turn_eight_usage,
        ]
    )

    output_tokens = sum(
        int(usage.get("output_tokens", 0) or 0)
        for usage in [
            automatic_usage,
            turn_seven_usage,
            turn_eight_usage,
        ]
    )

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": (
            input_tokens + output_tokens
        ),
    }


def finalize_smoke_test() -> dict[str, Any]:
    automatic = load_json(AUTOMATIC_PATH)
    turn_seven = load_json(TURN_SEVEN_PATH)
    turn_eight = load_json(TURN_EIGHT_PATH)

    final_result = turn_eight["result"]

    if (
        final_result["final_status"]
        .strip()
        .lower()
        != "completed"
    ):
        raise ValueError(
            "Turn eight did not report completion."
        )

    if final_result.get("proposed_tools"):
        raise ValueError(
            "Turn eight proposed another tool."
        )

    scenario = load_scenario("CS-001")

    trace = create_trace(
        workflow_id="CS-001",
        framework="openai_agents",
        configuration="native",
        repeat_number=1,
        model="gpt-5.6-luna",
        temperature=0.0,
    )

    proposals = collect_tool_proposals(
        automatic,
        turn_seven,
    )

    tool_results = []

    for step_number, proposal in enumerate(
        proposals,
        start=1,
    ):
        tool_result = execute_controlled_tool(
            trace=trace,
            scenario=scenario,
            tool_name=proposal["tool_name"],
            step_number=step_number,
            arguments=proposal["arguments"],
            approval_granted=True,
            forced_failures=0,
        )

        tool_results.append(tool_result)

    token_usage = calculate_tokens(
        automatic,
        turn_seven,
        turn_eight,
    )

    finalize_trace(
        trace=trace,
        final_status="completed",
        final_answer=final_result["output_text"],
        input_tokens=token_usage["input_tokens"],
        output_tokens=token_usage["output_tokens"],
    )

    validate_trace(trace)

    score = score_trace(
        scenario=scenario,
        trace=trace,
    )

    return {
        "result_type": (
            "completed_native_smoke_test"
        ),
        "official_experiment_result": False,
        "workflow_id": "CS-001",
        "framework": "openai_agents",
        "configuration": "native",
        "model": "gpt-5.6-luna",
        "model_turn_count": 8,
        "tool_execution_count": 7,
        "final_status": "completed",
        "final_answer": final_result[
            "output_text"
        ],
        "token_usage": token_usage,
        "api_calls_already_performed": 8,
        "new_api_call_made": False,
        "tool_proposals": proposals,
        "tool_results": tool_results,
        "trace": trace,
        "score": score,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate the completed CS-001 "
            "native smoke test."
        )
    )

    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Finalize without making an API call.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.finalize:
        raise RuntimeError(
            "Use --finalize. No API call is available."
        )

    output = finalize_smoke_test()

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(output, file, indent=2)

    print(json.dumps(output, indent=2))
    print(f"Report: {OUTPUT_PATH}")
    print(
        "CS-001 NATIVE SMOKE TEST FINALIZED — "
        "no new API call was made."
    )


if __name__ == "__main__":
    main()