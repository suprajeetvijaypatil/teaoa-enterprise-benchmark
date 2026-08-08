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


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FEEDBACK_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "paid_smoke_tool_feedback.json"
)

DRY_OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "second_turn_dry_validation.json"
)

REAL_OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "second_turn_paid_result.json"
)


def load_feedback() -> dict:
    if not FEEDBACK_PATH.is_file():
        raise FileNotFoundError(
            f"Tool feedback not found: {FEEDBACK_PATH}"
        )

    with FEEDBACK_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the second controlled model turn."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without calling the API.",
    )

    parser.add_argument(
        "--confirm-paid-api-call",
        action="store_true",
        help="Authorize one paid second-turn call.",
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

    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)
    feedback = load_feedback()

    context["previous_tool_feedback"] = feedback
    context["turn_number"] = 2
    context["continuation_instruction"] = (
        "Continue from the supplied simulated tool result. "
        "Propose only the next necessary tool. If the "
        "workflow is complete, return the final outcome. "
        "Do not repeat completed tool calls unless needed."
    )

    request = AdapterRequest(
        run_id=(
            f"second-turn-{uuid4().hex[:8]}"
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
            "second_turn_paid"
            if real_execution
            else "second_turn_dry_validation"
        ),
        "executed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "turn_number": 2,
        "feedback_included": True,
        "real_execution": real_execution,
        "result": result.to_dict(),
    }

    output_path = (
        REAL_OUTPUT_PATH
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
        print("SECOND PAID MODEL TURN COMPLETED.")
    else:
        print(
            "SECOND TURN CONFIGURATION PASSED — "
            "no API call was made."
        )


if __name__ == "__main__":
    main()