from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from runner.benchmark_v2_loader import (
    load_manifest,
)

from runner.shared_experiment_v2 import (
    run_shared_experiment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "full_dry_run_matrix_validation.json"
)


FRAMEWORKS = [
    "langgraph",
    "crewai",
    "autogen",
    "semantic_kernel",
    "openai_agents",
    "google_adk",
]


CONFIGURATIONS = [
    "native",
    "teaoa",
]


def validate_result(
    result: dict[str, Any],
    framework: str,
    workflow_id: str,
    configuration: str,
) -> list[str]:
    errors = []

    expected_values = {
        "framework": framework,
        "workflow_id": workflow_id,
        "configuration": configuration,
        "dry_run": True,
        "ground_truth_exposed_to_model": False,
        "scoring_rules_exposed_to_model": False,
        "api_call_made": False,
    }

    for field, expected in expected_values.items():
        actual = result.get(field)

        if actual != expected:
            errors.append(
                f"{field}: expected {expected!r}, "
                f"received {actual!r}"
            )

    traces = result.get("traces", [])

    if len(traces) != 1:
        errors.append(
            "Expected exactly one dry-run trace."
        )

    elif traces[0].get("api_call_made") is not False:
        errors.append(
            "Trace did not confirm api_call_made=False."
        )

    return errors


def main() -> None:
    manifest_rows = load_manifest()

    enabled_rows = [
        row
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    expected_test_count = (
        len(enabled_rows)
        * len(FRAMEWORKS)
        * len(CONFIGURATIONS)
    )

    completed_test_count = 0
    passed_test_count = 0
    failures = []

    group_counts = defaultdict(
        lambda: {
            "tested": 0,
            "passed": 0,
            "failed": 0,
        }
    )

    for row in enabled_rows:
        workflow_id = row["workflow_id"]

        task_path = str(
            Path("benchmark_v2")
            / row["workflow_file"]
        )

        for framework in FRAMEWORKS:
            for configuration in CONFIGURATIONS:
                group_key = (
                    f"{framework}:{configuration}"
                )

                completed_test_count += 1
                group_counts[group_key]["tested"] += 1

                try:
                    result = run_shared_experiment(
                        framework=framework,
                        task=task_path,
                        configuration=configuration,
                        repeat=1,
                        model="MODEL_NOT_CALLED",
                        temperature=0.0,
                        dry_run=True,
                    )

                    validation_errors = validate_result(
                        result=result,
                        framework=framework,
                        workflow_id=workflow_id,
                        configuration=configuration,
                    )

                    if validation_errors:
                        group_counts[
                            group_key
                        ]["failed"] += 1

                        failures.append(
                            {
                                "workflow_id": workflow_id,
                                "framework": framework,
                                "configuration": (
                                    configuration
                                ),
                                "errors": (
                                    validation_errors
                                ),
                            }
                        )

                    else:
                        passed_test_count += 1
                        group_counts[
                            group_key
                        ]["passed"] += 1

                except Exception as error:
                    group_counts[
                        group_key
                    ]["failed"] += 1

                    failures.append(
                        {
                            "workflow_id": workflow_id,
                            "framework": framework,
                            "configuration": (
                                configuration
                            ),
                            "errors": [str(error)],
                        }
                    )

                if completed_test_count % 100 == 0:
                    print(
                        "Progress: "
                        f"{completed_test_count}/"
                        f"{expected_test_count}"
                    )

    report = {
        "workflow_count": len(enabled_rows),
        "framework_count": len(FRAMEWORKS),
        "configuration_count": len(
            CONFIGURATIONS
        ),
        "expected_test_count": (
            expected_test_count
        ),
        "completed_test_count": (
            completed_test_count
        ),
        "passed_test_count": passed_test_count,
        "failed_test_count": len(failures),
        "api_call_made": False,
        "group_counts": dict(group_counts),
        "failures": failures,
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
        "framework_count": report[
            "framework_count"
        ],
        "configuration_count": report[
            "configuration_count"
        ],
        "expected_test_count": report[
            "expected_test_count"
        ],
        "completed_test_count": report[
            "completed_test_count"
        ],
        "passed_test_count": report[
            "passed_test_count"
        ],
        "failed_test_count": report[
            "failed_test_count"
        ],
        "api_call_made": False,
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    if (
        completed_test_count
        != expected_test_count
        or failures
    ):
        raise SystemExit(
            "FULL DRY-RUN MATRIX VALIDATION FAILED."
        )

    print(
        "ALL 1,200 DRY-RUN TESTS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()