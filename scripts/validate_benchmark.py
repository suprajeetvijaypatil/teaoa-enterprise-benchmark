from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmark"
MANIFEST = BENCHMARK / "benchmark_manifest.csv"
CATALOG = BENCHMARK / "scenario_catalog.csv"

errors = []

required_workflow_fields = [
    "workflow_id",
    "version",
    "domain",
    "scenario",
    "task_instruction",
    "dataset",
    "prompt",
    "ground_truth",
    "steps",
    "allowed_tools",
    "forbidden_tools",
    "approval_required",
    "risk_class",
    "expected_outcome",
    "model",
    "temperature",
    "token_limit",
    "timeout_seconds",
    "retry_limit",
    "sla_seconds",
    "scoring_rules"
]


def load_csv(path):
    if not path.exists():
        errors.append(f"Missing file: {path}")
        return []

    try:
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            return list(csv.DictReader(file))
    except Exception as error:
        errors.append(f"Cannot read {path.name}: {error}")
        return []


def load_json(path):
    if not path.exists():
        errors.append(f"Missing file: {path}")
        return None

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        errors.append(f"Invalid JSON in {path.name}: {error}")
        return None


print("=" * 60)
print("TEAOA BENCHMARK VALIDATOR")
print("=" * 60)

manifest_rows = load_csv(MANIFEST)
catalog_rows = load_csv(CATALOG)

print(f"Scenario catalogue entries: {len(catalog_rows)}")
print(f"Manifest workflow entries: {len(manifest_rows)}")

if len(catalog_rows) != 10:
    errors.append(
        f"Scenario catalogue should contain 10 entries, "
        f"but contains {len(catalog_rows)}"
    )

if len(manifest_rows) != 10:
    errors.append(
        f"Manifest should contain 10 entries, "
        f"but contains {len(manifest_rows)}"
    )

catalog_ids = {
    row.get("workflow_id", "").strip()
    for row in catalog_rows
}

manifest_ids = {
    row.get("workflow_id", "").strip()
    for row in manifest_rows
}

if len(catalog_ids) != len(catalog_rows):
    errors.append("Duplicate workflow IDs found in scenario_catalog.csv")

if len(manifest_ids) != len(manifest_rows):
    errors.append("Duplicate workflow IDs found in benchmark_manifest.csv")

missing_from_manifest = catalog_ids - manifest_ids
missing_from_catalog = manifest_ids - catalog_ids

if missing_from_manifest:
    errors.append(
        "Missing from manifest: "
        + ", ".join(sorted(missing_from_manifest))
    )

if missing_from_catalog:
    errors.append(
        "Missing from catalogue: "
        + ", ".join(sorted(missing_from_catalog))
    )

for row in manifest_rows:
    workflow_id = row.get("workflow_id", "").strip()

    print(f"\nChecking {workflow_id}...")

    workflow_path = BENCHMARK / row.get("workflow_file", "")
    dataset_path = BENCHMARK / row.get("dataset_file", "")
    prompt_path = BENCHMARK / row.get("prompt_file", "")
    ground_truth_path = BENCHMARK / row.get("ground_truth_file", "")

    workflow = load_json(workflow_path)
    ground_truth = load_json(ground_truth_path)

    if not dataset_path.exists():
        errors.append(
            f"{workflow_id}: missing dataset {dataset_path.name}"
        )
    elif dataset_path.stat().st_size == 0:
        errors.append(
            f"{workflow_id}: dataset is empty"
        )

    if not prompt_path.exists():
        errors.append(
            f"{workflow_id}: missing prompt {prompt_path.name}"
        )
    elif prompt_path.stat().st_size == 0:
        errors.append(
            f"{workflow_id}: prompt is empty"
        )

    if workflow is not None:
        for field in required_workflow_fields:
            if field not in workflow:
                errors.append(
                    f"{workflow_id}: workflow missing field '{field}'"
                )

        if workflow.get("workflow_id") != workflow_id:
            errors.append(
                f"{workflow_id}: workflow ID does not match manifest"
            )

        if not isinstance(workflow.get("steps"), list):
            errors.append(
                f"{workflow_id}: steps must be a list"
            )

        if not isinstance(workflow.get("allowed_tools"), list):
            errors.append(
                f"{workflow_id}: allowed_tools must be a list"
            )

        if not isinstance(workflow.get("forbidden_tools"), list):
            errors.append(
                f"{workflow_id}: forbidden_tools must be a list"
            )

        overlapping_tools = (
            set(workflow.get("allowed_tools", []))
            & set(workflow.get("forbidden_tools", []))
        )

        if overlapping_tools:
            errors.append(
                f"{workflow_id}: tools cannot be both allowed and forbidden: "
                + ", ".join(overlapping_tools)
            )

    if ground_truth is not None:
        if ground_truth.get("workflow_id") != workflow_id:
            errors.append(
                f"{workflow_id}: ground-truth ID does not match manifest"
            )

        if "expected_status" not in ground_truth:
            errors.append(
                f"{workflow_id}: ground truth missing expected_status"
            )

    if (
        workflow is not None
        and ground_truth is not None
        and workflow.get("expected_outcome", {}).get("status")
        != ground_truth.get("expected_status")
    ):
        errors.append(
            f"{workflow_id}: workflow and ground-truth statuses differ"
        )

    print(f"Checked: {workflow_id}")

print("\n" + "=" * 60)

if errors:
    print("VALIDATION FAILED")
    print("=" * 60)

    for number, error in enumerate(errors, start=1):
        print(f"{number}. {error}")

    sys.exit(1)

print("VALIDATION PASSED")
print("All 10 benchmark scenario packages are valid.")
print("=" * 60)