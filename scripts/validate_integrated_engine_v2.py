from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runner.shared_experiment_v2 import run_shared_experiment


PROJECT_ROOT = Path(__file__).resolve().parents[1]

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


def validate_one_run(
    framework: str,
    configuration: str,
) -> dict[str, Any]:
    try:
        result = run_shared_experiment(
            framework=framework,
            task="benchmark_v2/workflows/CS-001.json",
            configuration=configuration,
            repeat=1,
            model="MODEL_NOT_CALLED_IN_DRY_RUN",
            temperature=0.0,
            dry_run=True,
        )

        traces = result.get("traces", [])

        adapter_validated = (
            len(traces) == 1
            and traces[0].get("adapter_validated") is True
        )

        no_api_call = (
            result.get("api_call_made") is False
            and traces
            and traces[0].get("api_call_made") is False
        )

        zero_tokens = (
            traces
            and traces[0]
            .get("token_usage", {})
            .get("total_tokens") == 0
        )

        no_ground_truth_leakage = (
            result.get(
                "ground_truth_exposed_to_model"
            )
            is False
        )

        no_scoring_leakage = (
            result.get(
                "scoring_rules_exposed_to_model"
            )
            is False
        )

        registry_connected = (
            result.get(
                "adapter_registry_connected"
            )
            is True
        )

        valid = all(
            [
                adapter_validated,
                no_api_call,
                zero_tokens,
                no_ground_truth_leakage,
                no_scoring_leakage,
                registry_connected,
            ]
        )

        return {
            "framework": framework,
            "configuration": configuration,
            "valid": valid,
            "adapter_validated": adapter_validated,
            "registry_connected": registry_connected,
            "no_api_call": no_api_call,
            "zero_tokens": zero_tokens,
            "no_ground_truth_leakage": (
                no_ground_truth_leakage
            ),
            "no_scoring_leakage": no_scoring_leakage,
            "error": "",
        }

    except Exception as error:
        return {
            "framework": framework,
            "configuration": configuration,
            "valid": False,
            "adapter_validated": False,
            "registry_connected": False,
            "no_api_call": False,
            "zero_tokens": False,
            "no_ground_truth_leakage": False,
            "no_scoring_leakage": False,
            "error": str(error),
        }


def main() -> None:
    results = []

    for framework in FRAMEWORKS:
        for configuration in CONFIGURATIONS:
            result = validate_one_run(
                framework,
                configuration,
            )

            results.append(result)

            status = (
                "VALID"
                if result["valid"]
                else "FAILED"
            )

            print(
                f"{framework} / "
                f"{configuration}: {status}"
            )

            if result["error"]:
                print(
                    f"  Error: {result['error']}"
                )

    valid_count = sum(
        result["valid"] for result in results
    )

    report = {
        "validation_type": (
            "integrated_engine_dry_run"
        ),
        "workflow_id": "CS-001",
        "expected_runs": len(results),
        "valid_runs": valid_count,
        "all_valid": valid_count == len(results),
        "api_calls_performed": False,
        "results": results,
    }

    output_path = (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / "integrated_engine_validation.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(report, file, indent=2)

    print(
        f"\nValid integrated runs: "
        f"{valid_count}/{len(results)}"
    )
    print(f"Report: {output_path}")
    print("NO API CALLS WERE MADE.")

    if not report["all_valid"]:
        raise SystemExit(
            "Integrated validation failed."
        )


if __name__ == "__main__":
    main()