from __future__ import annotations

import argparse
import json
from typing import Any

from runner.benchmark_v2_loader import load_scenario


FORBIDDEN_MODEL_FIELDS = {
    "ground_truth",
    "required_steps",
    "expected_outcome",
    "scoring_rules",
    "expected_final_status",
    "expected_policy_decision",
    "expected_security_decision",
    "maximum_score",
}


def build_model_context(
    scenario: dict[str, Any],
) -> dict[str, Any]:
    workflow = scenario["workflow"]

    context = {
        "workflow_id": workflow["workflow_id"],
        "domain": workflow["domain"],
        "scenario": workflow["scenario"],
        "goal": workflow["goal"],
        "task_instruction": workflow[
            "task_instruction"
        ],
        "prompt": scenario["prompt"],
        "dataset": scenario["dataset"],
        "allowed_tools": workflow[
            "allowed_tools"
        ],
        "forbidden_tools": workflow[
            "forbidden_tools"
        ],
        "risk_class": workflow["risk_class"],
        "human_approval_required": workflow.get(
            "human_approval_required",
            workflow.get(
                "approval_required",
                False,
            ),
        ),
        "sla_seconds": workflow["sla_seconds"],
        "retry_limit": workflow["retry_limit"],
    }

    validate_no_leakage(context)

    return context


def validate_no_leakage(
    context: dict[str, Any],
) -> None:
    leaked_fields = sorted(
        field
        for field in FORBIDDEN_MODEL_FIELDS
        if field in context
    )

    if leaked_fields:
        raise ValueError(
            "Ground-truth leakage detected: "
            + ", ".join(leaked_fields)
        )


def summarize_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workflow_id": context["workflow_id"],
        "domain": context["domain"],
        "context_fields": sorted(context.keys()),
        "allowed_tool_count": len(
            context["allowed_tools"]
        ),
        "forbidden_tool_count": len(
            context["forbidden_tools"]
        ),
        "dataset_fields": sorted(
            context["dataset"].keys()
        ),
        "ground_truth_included": (
            "ground_truth" in context
        ),
        "scoring_rules_included": (
            "scoring_rules" in context
        ),
        "leakage_check_passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a leakage-safe benchmark_v2 "
            "model context."
        )
    )

    parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow ID such as CS-001.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scenario = load_scenario(args.workflow)
    context = build_model_context(scenario)
    summary = summarize_context(context)

    print(json.dumps(summary, indent=2))
    print(
        "MODEL CONTEXT PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()