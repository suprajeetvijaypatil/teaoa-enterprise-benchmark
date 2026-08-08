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
    / "tool_inventory.json"
)


def normalize_tool_names(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        tool_names = []

        for item in value:
            if isinstance(item, str):
                tool_names.append(item)

            elif isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("tool_name")
                    or item.get("id")
                )

                if name:
                    tool_names.append(str(name))

        return tool_names

    return []


def get_dataset_structure(dataset: Any) -> list[str]:
    if isinstance(dataset, dict):
        return sorted(dataset.keys())

    if isinstance(dataset, list):
        return ["<list>"]

    return [f"<{type(dataset).__name__}>"]


def inspect_scenarios() -> dict[str, Any]:
    manifest_rows = load_manifest()

    allowed_counter: Counter[str] = Counter()
    forbidden_counter: Counter[str] = Counter()
    dataset_pattern_counter: Counter[str] = Counter()

    scenario_summaries = []
    errors = []

    enabled_rows = [
        row
        for row in manifest_rows
        if row.get("enabled", "").lower() == "true"
    ]

    for row in enabled_rows:
        workflow_id = row.get("workflow_id", "<missing>")

        try:
            scenario = load_scenario(workflow_id)
            workflow = scenario["workflow"]
            dataset = scenario["dataset"]

            allowed_tools = normalize_tool_names(
                workflow.get("allowed_tools")
            )

            forbidden_tools = normalize_tool_names(
                workflow.get("forbidden_tools")
            )

            dataset_fields = get_dataset_structure(dataset)
            dataset_pattern = " | ".join(dataset_fields)

            allowed_counter.update(allowed_tools)
            forbidden_counter.update(forbidden_tools)
            dataset_pattern_counter.update([dataset_pattern])

            scenario_summaries.append(
                {
                    "workflow_id": workflow_id,
                    "domain": workflow.get("domain"),
                    "case_type": row.get("case_type"),
                    "allowed_tools": allowed_tools,
                    "forbidden_tools": forbidden_tools,
                    "dataset_fields": dataset_fields,
                    "human_approval_required": workflow.get(
                        "human_approval_required",
                        workflow.get("approval_required", False),
                    ),
                    "retry_limit": workflow.get("retry_limit"),
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
        "loaded_scenario_count": len(scenario_summaries),
        "error_count": len(errors),
        "unique_allowed_tools": sorted(allowed_counter),
        "allowed_tool_usage": dict(
            sorted(allowed_counter.items())
        ),
        "unique_forbidden_tools": sorted(forbidden_counter),
        "forbidden_tool_usage": dict(
            sorted(forbidden_counter.items())
        ),
        "dataset_structures": dict(
            sorted(dataset_pattern_counter.items())
        ),
        "scenarios": scenario_summaries,
        "errors": errors,
    }


def main() -> None:
    report = inspect_scenarios()

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
        "loaded_scenario_count": report[
            "loaded_scenario_count"
        ],
        "error_count": report["error_count"],
        "unique_allowed_tool_count": len(
            report["unique_allowed_tools"]
        ),
        "unique_forbidden_tool_count": len(
            report["unique_forbidden_tools"]
        ),
        "dataset_structure_count": len(
            report["dataset_structures"]
        ),
        "unique_allowed_tools": report[
            "unique_allowed_tools"
        ],
        "report_path": str(REPORT_PATH),
    }

    print(json.dumps(summary, indent=2))
    print("TOOL INVENTORY PASSED — no API call was made.")


if __name__ == "__main__":
    main()