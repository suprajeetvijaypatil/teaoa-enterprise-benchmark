from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
    load_scenario,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "ground_truth_inventory.json"
)


def structure_signature(value: Any) -> str:
    if isinstance(value, dict):
        fields = ", ".join(sorted(value.keys()))
        return f"dict({fields})"

    if isinstance(value, list):
        if not value:
            return "list[empty]"

        item_signatures = sorted(
            {
                structure_signature(item)
                for item in value
            }
        )

        return "list[" + " | ".join(
            item_signatures
        ) + "]"

    return type(value).__name__


def inspect_ground_truth() -> dict[str, Any]:
    manifest_rows = load_manifest()

    enabled_rows = [
        row
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    ground_truth_fields = Counter()
    required_step_structures = Counter()
    scoring_rule_structures = Counter()
    expected_outcome_structures = Counter()
    maximum_scores = Counter()

    structure_samples: dict[str, Any] = {}
    scenario_summaries = []
    errors = []

    for row in enabled_rows:
        workflow_id = row["workflow_id"]

        try:
            scenario = load_scenario(workflow_id)
            ground_truth = scenario["ground_truth"]

            field_signature = " | ".join(
                sorted(ground_truth.keys())
            )

            ground_truth_fields[field_signature] += 1

            required_steps = ground_truth.get(
                "required_steps"
            )

            scoring_rules = ground_truth.get(
                "scoring_rules"
            )

            expected_outcome = ground_truth.get(
                "expected_outcome"
            )

            maximum_score = ground_truth.get(
                "maximum_score"
            )

            required_signature = structure_signature(
                required_steps
            )

            scoring_signature = structure_signature(
                scoring_rules
            )

            outcome_signature = structure_signature(
                expected_outcome
            )

            required_step_structures[
                required_signature
            ] += 1

            scoring_rule_structures[
                scoring_signature
            ] += 1

            expected_outcome_structures[
                outcome_signature
            ] += 1

            maximum_scores[str(maximum_score)] += 1

            sample_key = (
                f"scoring_rules::{scoring_signature}"
            )

            if sample_key not in structure_samples:
                structure_samples[sample_key] = {
                    "workflow_id": workflow_id,
                    "value": scoring_rules,
                }

            required_sample_key = (
                f"required_steps::{required_signature}"
            )

            if (
                required_sample_key
                not in structure_samples
            ):
                structure_samples[
                    required_sample_key
                ] = {
                    "workflow_id": workflow_id,
                    "value": required_steps,
                }

            outcome_sample_key = (
                f"expected_outcome::{outcome_signature}"
            )

            if (
                outcome_sample_key
                not in structure_samples
            ):
                structure_samples[
                    outcome_sample_key
                ] = {
                    "workflow_id": workflow_id,
                    "value": expected_outcome,
                }

            scenario_summaries.append(
                {
                    "workflow_id": workflow_id,
                    "ground_truth_fields": sorted(
                        ground_truth.keys()
                    ),
                    "required_steps_structure": (
                        required_signature
                    ),
                    "scoring_rules_structure": (
                        scoring_signature
                    ),
                    "expected_outcome_structure": (
                        outcome_signature
                    ),
                    "maximum_score": maximum_score,
                }
            )

        except Exception as error:
            errors.append(
                {
                    "workflow_id": workflow_id,
                    "error": str(error),
                }
            )

    return {
        "enabled_scenario_count": len(enabled_rows),
        "loaded_ground_truth_count": len(
            scenario_summaries
        ),
        "error_count": len(errors),
        "ground_truth_field_patterns": dict(
            sorted(ground_truth_fields.items())
        ),
        "required_step_structures": dict(
            sorted(required_step_structures.items())
        ),
        "scoring_rule_structures": dict(
            sorted(scoring_rule_structures.items())
        ),
        "expected_outcome_structures": dict(
            sorted(
                expected_outcome_structures.items()
            )
        ),
        "maximum_scores": dict(
            sorted(maximum_scores.items())
        ),
        "structure_samples": structure_samples,
        "scenarios": scenario_summaries,
        "errors": errors,
    }


def main() -> None:
    report = inspect_ground_truth()

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
        "enabled_scenario_count": report[
            "enabled_scenario_count"
        ],
        "loaded_ground_truth_count": report[
            "loaded_ground_truth_count"
        ],
        "error_count": report["error_count"],
        "ground_truth_field_patterns": report[
            "ground_truth_field_patterns"
        ],
        "required_step_structures": report[
            "required_step_structures"
        ],
        "scoring_rule_structures": report[
            "scoring_rule_structures"
        ],
        "expected_outcome_structures": report[
            "expected_outcome_structures"
        ],
        "maximum_scores": report[
            "maximum_scores"
        ],
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))
    print(
        "GROUND-TRUTH INVENTORY PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()