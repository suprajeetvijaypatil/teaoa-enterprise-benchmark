from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ADAPTERS = {
    "langgraph": {
        "module": "frameworks.langgraph.adapter_v2",
        "success_message": "LANGGRAPH ADAPTER PASSED",
    },
    "crewai": {
        "module": "frameworks.crewai.adapter_v2",
        "success_message": "CREWAI ADAPTER PASSED",
    },
    "autogen": {
        "module": "frameworks.autogen.adapter_v2",
        "success_message": "AUTOGEN ADAPTER PASSED",
    },
    "semantic_kernel": {
        "module": "frameworks.semantic_kernel.adapter_v2",
        "success_message": "SEMANTIC KERNEL ADAPTER PASSED",
    },
    "openai_agents": {
        "module": "frameworks.openai_agents.adapter_v2",
        "success_message": "OPENAI AGENTS ADAPTER PASSED",
    },
    "google_adk": {
        "module": "frameworks.google_adk.adapter_v2",
        "success_message": "GOOGLE ADK ADAPTER PASSED",
    },
}


def validate_adapter(
    framework: str,
    configuration: dict[str, str],
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        configuration["module"],
        "--dry-run",
    ]

    process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = process.stdout + process.stderr

    exit_code_passed = process.returncode == 0

    success_message_found = (
        configuration["success_message"] in combined_output
    )

    no_api_call_confirmed = (
        '"api_call_made": false' in combined_output
        or '"api_call_made":false' in combined_output
    )

    execution_locked = (
        '"real_execution_enabled": false' in combined_output
        or '"real_execution_enabled":false' in combined_output
    )

    zero_tokens_confirmed = (
        '"total_tokens": 0' in combined_output
        or '"total_tokens":0' in combined_output
    )

    valid = all(
        [
            exit_code_passed,
            success_message_found,
            no_api_call_confirmed,
            execution_locked,
            zero_tokens_confirmed,
        ]
    )

    return {
        "framework": framework,
        "module": configuration["module"],
        "exit_code": process.returncode,
        "exit_code_passed": exit_code_passed,
        "success_message_found": success_message_found,
        "no_api_call_confirmed": no_api_call_confirmed,
        "execution_locked": execution_locked,
        "zero_tokens_confirmed": zero_tokens_confirmed,
        "valid": valid,
        "error_output": (
            process.stderr.strip()
            if process.returncode != 0
            else ""
        ),
    }


def main() -> None:
    results = [
        validate_adapter(framework, configuration)
        for framework, configuration in ADAPTERS.items()
    ]

    output_path = (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / "framework_adapter_validation.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "validation_type": "framework_adapter_dry_run",
        "api_calls_performed": False,
        "framework_count": len(results),
        "valid_count": sum(
            result["valid"] for result in results
        ),
        "all_valid": all(
            result["valid"] for result in results
        ),
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print("\nFRAMEWORK ADAPTER VALIDATION\n")

    for result in results:
        status = "VALID" if result["valid"] else "FAILED"

        print(
            f"{result['framework']}: {status} "
            f"| exit code: {result['exit_code']} "
            f"| API locked: {result['execution_locked']} "
            f"| zero tokens: {result['zero_tokens_confirmed']}"
        )

        if result["error_output"]:
            print(f"  Error: {result['error_output']}")

    print(
        f"\nValid adapters: "
        f"{report['valid_count']}/{report['framework_count']}"
    )

    print(f"Report: {output_path}")
    print("NO API CALLS WERE MADE.")

    if not report["all_valid"]:
        raise SystemExit(
            "One or more framework adapters failed validation."
        )


if __name__ == "__main__":
    main()