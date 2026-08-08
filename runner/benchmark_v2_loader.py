from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark_v2"
MANIFEST_PATH = BENCHMARK_ROOT / "benchmark_manifest.csv"


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required JSON file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_text_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Required text file not found: {path}")

    return path.read_text(encoding="utf-8")


def load_manifest() -> list[dict[str, str]]:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(
            f"Benchmark manifest not found: {MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def load_scenario(workflow_id: str) -> dict[str, Any]:
    manifest_rows = load_manifest()

    manifest_row = next(
        (
            row
            for row in manifest_rows
            if row.get("workflow_id") == workflow_id
        ),
        None,
    )

    if manifest_row is None:
        raise ValueError(
            f"Workflow ID is not present in the manifest: {workflow_id}"
        )

    if manifest_row.get("enabled", "").lower() != "true":
        raise ValueError(f"Workflow is disabled: {workflow_id}")

    workflow_path = BENCHMARK_ROOT / manifest_row["workflow_file"]
    dataset_path = BENCHMARK_ROOT / manifest_row["dataset_file"]
    prompt_path = BENCHMARK_ROOT / manifest_row["prompt_file"]
    ground_truth_path = (
        BENCHMARK_ROOT / manifest_row["ground_truth_file"]
    )

    return {
        "workflow_id": workflow_id,
        "manifest": manifest_row,
        "workflow": load_json_file(workflow_path),
        "dataset": load_json_file(dataset_path),
        "prompt": load_text_file(prompt_path),
        "ground_truth": load_json_file(ground_truth_path),
        "paths": {
            "workflow": str(workflow_path),
            "dataset": str(dataset_path),
            "prompt": str(prompt_path),
            "ground_truth": str(ground_truth_path),
        },
    }


def summarize_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    workflow = scenario["workflow"]
    dataset = scenario["dataset"]
    ground_truth = scenario["ground_truth"]

    return {
        "workflow_id": scenario["workflow_id"],
        "domain": scenario["manifest"].get("domain"),
        "case_type": scenario["manifest"].get("case_type"),
        "minimum_steps": scenario["manifest"].get("minimum_steps"),
        "workflow_fields": sorted(workflow.keys()),
        "dataset_fields": sorted(dataset.keys()),
        "ground_truth_fields": sorted(ground_truth.keys()),
        "prompt_characters": len(scenario["prompt"]),
        "all_files_loaded": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load and validate one benchmark_v2 scenario."
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
    summary = summarize_scenario(scenario)

    print(json.dumps(summary, indent=2))
    print("SCENARIO LOAD PASSED — no API call was made.")


if __name__ == "__main__":
    main()