from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "shared_engine_integration_validation.json"
)


RUNNERS = {
    "langgraph": (
        "frameworks.langgraph.all_tasks_runner_v2"
    ),
    "crewai": (
        "frameworks.crewai.all_tasks_runner_v2"
    ),
    "autogen": (
        "frameworks.autogen.all_tasks_runner_v2"
    ),
    "semantic_kernel": (
        "frameworks.semantic_kernel."
        "all_tasks_runner_v2"
    ),
    "openai_agents": (
        "frameworks.openai_agents."
        "all_tasks_runner_v2"
    ),
    "google_adk": (
        "frameworks.google_adk."
        "all_tasks_runner_v2"
    ),
}


CONFIGURATIONS = [
    "native",
    "teaoa",
]


def build_command(
    module: str,
    configuration: str,
    dry_run: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        module,
        "--task",
        "benchmark_v2/workflows/CS-001.json",
        "--configuration",
        configuration,
        "--repeat",
        "1",
        "--model",
        "MODEL_NOT_CALLED",
        "--temperature",
        "0.0",
    ]

    if dry_run:
        command.append("--dry-run")

    return command


def run_process(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def validate_dry_run(
    framework: str,
    module: str,
    configuration: str,
) -> dict[str, Any]:
    process = run_process(
        build_command(
            module=module,
            configuration=configuration,
            dry_run=True,
        )
    )

    output = (
        process.stdout
        + process.stderr
    )

    required_fragments = [
        f'"framework": "{framework}"',
        '"workflow_id": "CS-001"',
        f'"configuration": "{configuration}"',
        '"dry_run": true',
        '"ground_truth_exposed_to_model": false',
        '"scoring_rules_exposed_to_model": false',
        '"api_call_made": false',
    ]

    missing_fragments = [
        fragment
        for fragment in required_fragments
        if fragment not in output
    ]

    passed = (
        process.returncode == 0
        and not missing_fragments
    )

    return {
        "framework": framework,
        "configuration": configuration,
        "return_code": process.returncode,
        "missing_fragments": missing_fragments,
        "passed": passed,
    }


def validate_execution_lock(
    framework: str,
    module: str,
) -> dict[str, Any]:
    process = run_process(
        build_command(
            module=module,
            configuration="teaoa",
            dry_run=False,
        )
    )

    output = (
        process.stdout
        + process.stderr
    )

    lock_message_found = (
        "REAL V2 EXECUTION IS DISABLED"
        in output
    )

    passed = (
        process.returncode != 0
        and lock_message_found
    )

    return {
        "framework": framework,
        "non_dry_run_blocked": (
            process.returncode != 0
        ),
        "lock_message_found": (
            lock_message_found
        ),
        "passed": passed,
    }


def main() -> None:
    dry_run_results = []
    lock_results = []

    for framework, module in RUNNERS.items():
        for configuration in CONFIGURATIONS:
            dry_run_results.append(
                validate_dry_run(
                    framework=framework,
                    module=module,
                    configuration=configuration,
                )
            )

        lock_results.append(
            validate_execution_lock(
                framework=framework,
                module=module,
            )
        )

    passed_dry_runs = sum(
        result["passed"]
        for result in dry_run_results
    )

    passed_locks = sum(
        result["passed"]
        for result in lock_results
    )

    failed_dry_runs = [
        result
        for result in dry_run_results
        if not result["passed"]
    ]

    failed_locks = [
        result
        for result in lock_results
        if not result["passed"]
    ]

    report = {
        "framework_count": len(RUNNERS),
        "dry_run_test_count": len(
            dry_run_results
        ),
        "passed_dry_run_count": (
            passed_dry_runs
        ),
        "execution_lock_test_count": len(
            lock_results
        ),
        "passed_execution_lock_count": (
            passed_locks
        ),
        "failed_dry_runs": failed_dry_runs,
        "failed_execution_locks": (
            failed_locks
        ),
        "api_call_made": False,
        "dry_run_results": dry_run_results,
        "execution_lock_results": lock_results,
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
        "framework_count": report[
            "framework_count"
        ],
        "dry_run_test_count": report[
            "dry_run_test_count"
        ],
        "passed_dry_run_count": report[
            "passed_dry_run_count"
        ],
        "execution_lock_test_count": report[
            "execution_lock_test_count"
        ],
        "passed_execution_lock_count": report[
            "passed_execution_lock_count"
        ],
        "failed_dry_run_count": len(
            failed_dry_runs
        ),
        "failed_execution_lock_count": len(
            failed_locks
        ),
        "api_call_made": False,
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))

    if failed_dry_runs or failed_locks:
        raise SystemExit(
            "SHARED-ENGINE INTEGRATION "
            "VALIDATION FAILED."
        )

    print(
        "ALL SIX FRAMEWORK INTEGRATIONS "
        "PASSED — no API call was made."
    )


if __name__ == "__main__":
    main()