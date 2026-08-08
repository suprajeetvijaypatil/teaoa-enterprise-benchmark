from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
)
from runner.framework_adapter_registry_v2 import (
    dispatch_adapter,
)
from runner.model_context_v2 import build_model_context
from runner.tool_feedback_v2 import sanitize_value


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results" / "benchmark_v2"

SIX_TURN_PATH = (
    RESULTS_ROOT
    / "automatic_multi_turn_paid.json"
)

TURN_SEVEN_PATH = (
    RESULTS_ROOT
    / "finalization_turn_paid.json"
)

FINAL_TOOL_PATH = (
    RESULTS_ROOT
    / "finalization_tool_replay.json"
)


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required result not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def build_complete_history() -> list[dict]:
    six_turn_result = load_json(SIX_TURN_PATH)
    seventh_turn = load_json(TURN_SEVEN_PATH)
    final_tool_replay = load_json(FINAL_TOOL_PATH)

    history = list(
        six_turn_result["execution_history"]
    )

    proposals = seventh_turn["result"].get(
        "proposed_tools",
        [],
    )

    tool_results = final_tool_replay.get(
        "tool_results",
        [],
    )

    if len(proposals) != 1:
        raise ValueError(
            "Expected exactly one seventh-turn "
            "tool proposal."
        )

    if len(tool_results) != 1:
        raise ValueError(
            "Expected exactly one final tool result."
        )

    proposal = proposals[0]

    tool_name = (
        proposal.get("tool")
        or proposal.get("tool_name")
        or proposal.get("name")
    )

    history.append(
        {
            "turn_number": 7,
            "step_number": 7,
            "tool_name": tool_name,
            "arguments": proposal.get(
                "arguments",
                {},
            ),
            "result": tool_results[0],
        }
    )

    return sanitize_value(history)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Confirm completion after all seven "
            "tools have executed."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-paid-api-call",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run and args.confirm_paid_api_call:
        raise ValueError(
            "Choose only one execution mode."
        )

    if not args.dry_run and not args.confirm_paid_api_call:
        raise RuntimeError(
            "Execution is locked. Use --dry-run first."
        )

    real_execution = args.confirm_paid_api_call
    history = build_complete_history()

    if len(history) != 7:
        raise ValueError(
            "Expected exactly seven completed "
            "tool executions."
        )

    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)

    context["turn_number"] = 8
    context["execution_history"] = history
    context["continuation_instruction"] = (
        "All seven required tool actions have now been "
        "executed, including resolve_ticket. Review their "
        "results. Do not propose or repeat any completed "
        "tool. If the workflow goal is satisfied, return "
        "a completed final answer with an empty proposed "
        "tools list."
    )

    request = AdapterRequest(
        run_id=(
            f"completion-confirmation-"
            f"{uuid4().hex[:8]}"
        ),
        framework="openai_agents",
        workflow_id="CS-001",
        configuration="native",
        model="gpt-5.6-luna",
        temperature=0.0,
        model_context=context,
        dry_run=not real_execution,
    )

    result = dispatch_adapter(
        request,
        allow_api_call=real_execution,
    )

    output = {
        "execution_type": (
            "paid_completion_confirmation"
            if real_execution
            else "completion_confirmation_dry"
        ),
        "executed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "turn_number": 8,
        "completed_tool_count": len(history),
        "real_execution": real_execution,
        "result": result.to_dict(),
    }

    output_path = RESULTS_ROOT / (
        "completion_confirmation_paid.json"
        if real_execution
        else "completion_confirmation_dry.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(output, file, indent=2)

    print(json.dumps(output, indent=2))
    print(f"Report: {output_path}")

    if real_execution:
        print(
            "COMPLETION CONFIRMATION CALL COMPLETED."
        )
    else:
        print(
            "COMPLETION CONFIRMATION CONFIGURATION "
            "PASSED — no API call was made."
        )


if __name__ == "__main__":
    main()