from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUNNERS = {
    "langgraph": "frameworks.langgraph.all_tasks_runner_v2",
    "crewai": "frameworks.crewai.all_tasks_runner_v2",
    "autogen": "frameworks.autogen.all_tasks_runner_v2",
    "semantic_kernel": "frameworks.semantic_kernel.all_tasks_runner_v2",
    "openai_agents": "frameworks.openai_agents.all_tasks_runner_v2",
    "google_adk": "frameworks.google_adk.all_tasks_runner_v2",
}

REQUIRED_ARGUMENTS = [
    "--task",
    "--configuration",
    "--repeat",
    "--model",
    "--temperature",
    "--dry-run",
]


def validate_runner(framework: str, module: str) -> dict:
    process = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = process.stdout + process.stderr

    missing_arguments = [
        argument
        for argument in REQUIRED_ARGUMENTS
        if argument not in combined_output
    ]

    return {
        "framework": framework,
        "module": module,
        "help_exit_code": process.returncode,
        "missing_arguments": missing_arguments,
        "valid": process.returncode == 0 and not missing_arguments,
    }


def main() -> None:
    results = [
        validate_runner(framework, module)
        for framework, module in RUNNERS.items()
    ]

    output_path = (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / "runner_contract_validation.json"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)

    print("\nV2 RUNNER CONTRACT VALIDATION\n")

    for result in results:
        status = "VALID" if result["valid"] else "NEEDS UPDATE"
        missing = ", ".join(result["missing_arguments"]) or "none"

        print(
            f"{result['framework']}: {status} "
            f"| missing arguments: {missing}"
        )

    valid_count = sum(result["valid"] for result in results)

    print(f"\nValid runners: {valid_count}/{len(results)}")
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()