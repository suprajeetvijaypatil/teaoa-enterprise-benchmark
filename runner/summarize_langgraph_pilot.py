from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_RESULTS_DIRECTORY = (
    PROJECT_ROOT
    / "results"
    / "raw"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "results"
    / "processed"
    / "langgraph_task01_pilot.csv"
)


def load_result(path: Path) -> dict[str, Any]:
    """Load one experiment result JSON file."""

    text = path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not text:
        raise ValueError(
            f"Result file is empty: {path.name}"
        )

    result = json.loads(text)

    if not isinstance(result, dict):
        raise ValueError(
            f"Result must be a JSON object: {path.name}"
        )

    return result


def main() -> None:
    """Combine and summarize the four pilot runs."""

    result_files = sorted(
        RAW_RESULTS_DIRECTORY.glob(
            "langgraph_*_task_01_repeat_*.json"
        )
    )

    if len(result_files) != 4:
        raise RuntimeError(
            "Expected exactly four LangGraph pilot files, "
            f"but found {len(result_files)}."
        )

    rows: list[dict[str, Any]] = []

    for path in result_files:
        print(f"Loading: {path.name}")

        result = load_result(path)

        execution = result.get(
            "execution_result",
            {},
        )

        rows.append(
            {
                "filename": path.name,
                "framework": result.get(
                    "framework"
                ),
                "configuration": result.get(
                    "configuration"
                ),
                "repeat_number": result.get(
                    "repeat_number"
                ),
                "task_id": result.get(
                    "task_id"
                ),
                "scenario": result.get(
                    "scenario"
                ),
                "proposed_tool": result.get(
                    "proposed_tool"
                ),
                "execution_status": execution.get(
                    "status"
                ),
                "policy_decision": result.get(
                    "policy_decision"
                ),
                "step_success": result.get(
                    "step_success"
                ),
                "unsafe_action_attempts": result.get(
                    "unsafe_action_attempts",
                    0,
                ),
                "unsafe_actions_executed": result.get(
                    "unsafe_actions_executed",
                    0,
                ),
                "governance_violations": result.get(
                    "governance_violations",
                    0,
                ),
                "input_tokens": result.get(
                    "input_tokens",
                    0,
                ),
                "output_tokens": result.get(
                    "output_tokens",
                    0,
                ),
                "estimated_cost_usd": result.get(
                    "estimated_cost_usd",
                    0.0,
                ),
                "model_latency_seconds": result.get(
                    "model_latency_seconds",
                    0.0,
                ),
                "total_latency_seconds": result.get(
                    "total_latency_seconds",
                    0.0,
                ),
            }
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(rows[0].keys())

    with OUTPUT_FILE.open(
        mode="w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("LANGGRAPH PILOT SUMMARY")
    print("-----------------------")
    print(f"Completed runs: {len(rows)}")

    total_input_tokens = sum(
        int(row["input_tokens"])
        for row in rows
    )

    total_output_tokens = sum(
        int(row["output_tokens"])
        for row in rows
    )

    total_estimated_cost = sum(
        float(row["estimated_cost_usd"])
        for row in rows
    )

    print(
        f"Total input tokens: "
        f"{total_input_tokens}"
    )

    print(
        f"Total output tokens: "
        f"{total_output_tokens}"
    )

    print(
        f"Estimated pilot cost: "
        f"${total_estimated_cost:.8f}"
    )

    for configuration in [
        "native",
        "teaoa",
    ]:
        configuration_rows = [
            row
            for row in rows
            if row["configuration"]
            == configuration
        ]

        successful_runs = sum(
            bool(row["step_success"])
            for row in configuration_rows
        )

        unsafe_attempts = sum(
            int(row["unsafe_action_attempts"])
            for row in configuration_rows
        )

        unsafe_executions = sum(
            int(row["unsafe_actions_executed"])
            for row in configuration_rows
        )

        average_latency = (
            sum(
                float(
                    row["total_latency_seconds"]
                )
                for row in configuration_rows
            )
            / len(configuration_rows)
        )

        print()
        print(
            f"{configuration.upper()} RESULTS"
        )

        print(
            f"Successful runs: "
            f"{successful_runs}/"
            f"{len(configuration_rows)}"
        )

        print(
            f"Unsafe attempts: "
            f"{unsafe_attempts}"
        )

        print(
            f"Unsafe executions: "
            f"{unsafe_executions}"
        )

        print(
            f"Average latency: "
            f"{average_latency:.4f} seconds"
        )

    print()
    print(
        f"CSV saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()