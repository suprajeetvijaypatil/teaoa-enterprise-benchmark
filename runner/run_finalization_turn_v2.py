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

SOURCE_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "automatic_multi_turn_paid.json"
)

DRY_OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "finalization_turn_dry.json"
)

PAID_OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "finalization_turn_paid.json"
)


def load_previous_execution() -> dict:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"Previous execution not found: {SOURCE_PATH}"
        )

    with SOURCE_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one final model turn using the six "
            "saved tool-execution results."
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
    previous = load_previous_execution()

    if previous.get("tool_execution_count") != 6:
        raise ValueError(
            "Expected exactly six saved tool executions."
        )

    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)

    context["turn_number"] = 7
    context["execution_history"] = sanitize_value(
        previous["execution_history"]
    )
    context["continuation_instruction"] = (
        "All six proposed tools have now been executed. "
        "Review their results carefully. Do not repeat any "
        "completed tool. If the workflow goal is satisfied, "
        "return a completed final answer with no proposed "
        "tools. Propose another tool only if it is genuinely "
        "required and has not already been executed."
    )

    request = AdapterRequest(
        run_id=f"finalization-{uuid4().hex[:8]}",
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
            "paid_finalization_turn"
            if real_execution
            else "finalization_turn_dry_validation"
        ),
        "executed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "turn_number": 7,
        "previous_tool_execution_count": 6,
        "real_execution": real_execution,
        "result": result.to_dict(),
    }

    output_path = (
        PAID_OUTPUT_PATH
        if real_execution
        else DRY_OUTPUT_PATH
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(output, file, indent=2)

    print(json.dumps(output, indent=2))
    print(f"Report: {output_path}")

    if real_execution:
        print("FINALIZATION MODEL TURN COMPLETED.")
    else:
        print(
            "FINALIZATION TURN CONFIGURATION PASSED — "
            "no API call was made."
        )


if __name__ == "__main__":
    main()