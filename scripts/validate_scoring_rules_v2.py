from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)

from runner.model_context_v2 import (
    build_model_context,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "scoring_rule_validation.json"
)


REQUIRED_CORE_RULES = {
    "workflow_completion",
    "correct_tool_sequence",
    "correct_policy_decision",
    "forbidden_tool_avoidance",
    "trace_completeness",
}


def validate_rules(
    workflow_id: str,
) -> dict[str, Any]:
    scenario = load_scenario(workflow_id)

    workflow = scenario["workflow"]
    ground_truth = scenario["ground_truth"]

    scoring_rules = workflow.get("scoring_rules")

    errors = []

    if not isinstance(scoring_rules, dict):
        return {
            "workflow_id": workflow_id,
            "valid": False,
            "errors": [
                "Workflow scoring_rules is missing "
                "or is not a dictionary."
            ],
        }

    maximum_score = scoring_rules.get(
        "maximum_score"
    )

    ground_truth_maximum = ground_truth.get(
        "maximum_score"
    )

    weighted_rules = {
        name: weight
        for name, weight in scoring_rules.items()
        if name != "maximum_score"
    }

    invalid_weights = {
        name: weight
        for name, weight in weighted_rules.items()
        if not isinstance(weight, (int, float))
        or weight < 0
    }

    if invalid_weights:
        errors.append(
            "Invalid scoring weights: "
            + str(invalid_weights)
        )

    calculated_maximum = sum(
        weight
        for weight in weighted_rules.values()
        if isinstance(weight, (int, float))
    )

    if calculated_maximum != maximum_score:
        errors.append(
            "Scoring weights do not equal the "
            "workflow maximum score."
        )

    if maximum_score != ground_truth_maximum:
        errors.append(
            "Workflow and ground-truth maximum "
            "scores do not match."
        )

    missing_core_rules = sorted(
        REQUIRED_CORE_RULES
        - set(weighted_rules)
    )

    if missing_core_rules:
        errors.append(
            "Missing core scoring rules: "
            + ", ".join(missing_core_rules)
        )

    model_context = build_model_context(
        scenario
    )

    scoring_rules_leaked = (
        "scoring_rules" in model_context
        or "maximum_score" in model_context
        or "required_steps" in model_context
    )

    if scoring_rules_leaked:
        errors.append(
            "Scoring information leaked into "
            "the model context."
        )

    core_and_recovery = (
        REQUIRED_CORE_RULES
        | {
            "correct_recovery_or_escalation",
            "correct_recovery_or_rollback",
        }
    )

    domain_specific_rules = sorted(
        set(weighted_rules)
        - core_and_recovery
    )

    return {
        "workflow_id": workflow_id,
        "maximum_score": maximum_score,
        "calculated_maximum": calculated_maximum,
        "ground_truth_maximum": (
            ground_truth_maximum
        ),
        "weighted_rules": weighted_rules,
        "domain_specific_rules": (
            domain_specific_rules
        ),
        "model_context_leakage": (
            scoring_rules_leaked
        ),
        "valid": not errors,
        "errors": errors,
    }


def main() -> None:
    manifest_rows = load_manifest()

    workflow_ids = [
        row["workflow_id"]
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    results = []
    loading_errors = []

    for workflow_id in workflow_ids:
        try:
            results.append(
                validate_rules(workflow_id)
            )

        except Exception as error:
            loading_errors.append(
                {
                    "workflow_id": workflow_id,
                    "error": str(error),
                }
            )

    valid_count = sum(
        result["valid"]
        for result in results
    )

    invalid_results = [
        {
            "workflow_id": result["workflow_id"],
            "errors": result["errors"],
        }
        for result in results
        if not result["valid"]
    ]

    rule_patterns = Counter(
        " | ".join(
            sorted(result.get("weighted_rules", {}))
        )
        for result in results
    )

    domain_rules = Counter(
        " | ".join(
            result.get(
                "domain_specific_rules",
                [],
            )
        )
        for result in results
    )

    report = {
        "workflow_count": len(workflow_ids),
        "tested_count": len(results),
        "valid_count": valid_count,
        "invalid_count": len(invalid_results),
        "loading_error_count": len(
            loading_errors
        ),
        "rule_patterns": dict(rule_patterns),
        "domain_specific_rule_patterns": dict(
            domain_rules
        ),
        "invalid_results": invalid_results,
        "loading_errors": loading_errors,
        "results": results,
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    summary = {
        "workflow_count": report[
            "workflow_count"
        ],
        "tested_count": report["tested_count"],
        "valid_count": report["valid_count"],
        "invalid_count": report["invalid_count"],
        "loading_error_count": report[
            "loading_error_count"
        ],
        "rule_patterns": report["rule_patterns"],
        "domain_specific_rule_patterns": report[
            "domain_specific_rule_patterns"
        ],
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    if (
        report["invalid_count"] > 0
        or report["loading_error_count"] > 0
    ):
        raise SystemExit(
            "SCORING-RULE VALIDATION FAILED."
        )

    print(
        "ALL SCORING RULES PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()