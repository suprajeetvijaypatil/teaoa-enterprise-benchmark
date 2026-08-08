from pathlib import Path
from collections import Counter
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmark_v2"

PLAN_FILE = BENCHMARK / "workflow_plan.csv"
MANIFEST_FILE = BENCHMARK / "benchmark_manifest.csv"

WORKFLOWS = BENCHMARK / "workflows"
DATASETS = BENCHMARK / "datasets"
PROMPTS = BENCHMARK / "prompts"
GROUND_TRUTH = BENCHMARK / "ground_truth"

RESULTS = ROOT / "results"
REPORT_FILE = RESULTS / "benchmark_v2_validation.json"

RESULTS.mkdir(parents=True, exist_ok=True)

errors = []
warnings = []

expected_domains = {
    "customer_support": 15,
    "finance_invoices": 15,
    "erp_procurement": 15,
    "software_engineering": 15,
    "healthcare": 10,
    "supply_chain": 15,
    "it_operations_security": 15
}

security_cases = {
    "prompt_injection",
    "privilege_escalation",
    "memory_poisoning",
    "hallucinated_tool"
}

recovery_cases = {
    "tool_timeout",
    "malformed_response"
}

required_workflow_fields = {
    "task_id",
    "workflow_id",
    "version",
    "domain",
    "scenario",
    "case_type",
    "goal",
    "task_instruction",
    "dataset",
    "prompt",
    "ground_truth",
    "steps",
    "minimum_steps",
    "allowed_tools",
    "forbidden_tools",
    "risk_class",
    "human_approval_required",
    "approval_required",
    "sla_seconds",
    "retry_limit",
    "fault_injection",
    "data_source_type",
    "is_case_study",
    "expected_outcome",
    "scoring_rules"
}

required_ground_truth_fields = {
    "task_id",
    "workflow_id",
    "expected_final_status",
    "expected_policy_decision",
    "expected_security_decision",
    "required_steps",
    "minimum_steps",
    "allowed_tools",
    "forbidden_tools",
    "approval_required",
    "fault_injection",
    "expected_recovery",
    "unsafe_action_executed",
    "governance_violation",
    "maximum_score"
}


def read_csv(path):
    if not path.exists():
        errors.append(f"Missing CSV file: {path}")
        return []

    try:
        with path.open(
            "r",
            newline="",
            encoding="utf-8-sig"
        ) as file:
            return list(csv.DictReader(file))
    except Exception as error:
        errors.append(
            f"Could not read {path.name}: {error}"
        )
        return []


def read_json(path, label):
    if not path.exists():
        errors.append(f"Missing {label}: {path}")
        return None

    try:
        with path.open(
            "r",
            encoding="utf-8-sig"
        ) as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        errors.append(
            f"Invalid JSON in {path.name}: {error}"
        )
        return None
    except Exception as error:
        errors.append(
            f"Could not read {path.name}: {error}"
        )
        return None


def to_bool(value):
    return str(value).strip().lower() == "true"


def add_error(workflow_id, message):
    errors.append(f"{workflow_id}: {message}")


print("=" * 72)
print("TEAOA BENCHMARK V2 VALIDATOR")
print("=" * 72)

plan_rows = read_csv(PLAN_FILE)
manifest_rows = read_csv(MANIFEST_FILE)

print(f"Plan entries: {len(plan_rows)}")
print(f"Manifest entries: {len(manifest_rows)}")

if len(plan_rows) != 100:
    errors.append(
        f"workflow_plan.csv must contain 100 entries; "
        f"found {len(plan_rows)}"
    )

if len(manifest_rows) != 100:
    errors.append(
        f"benchmark_manifest.csv must contain 100 entries; "
        f"found {len(manifest_rows)}"
    )


plan_ids = [
    row.get("workflow_id", "").strip()
    for row in plan_rows
]

manifest_ids = [
    row.get("workflow_id", "").strip()
    for row in manifest_rows
]

if len(plan_ids) != len(set(plan_ids)):
    errors.append(
        "Duplicate workflow IDs found in workflow_plan.csv"
    )

if len(manifest_ids) != len(set(manifest_ids)):
    errors.append(
        "Duplicate workflow IDs found in benchmark_manifest.csv"
    )

plan_id_set = set(plan_ids)
manifest_id_set = set(manifest_ids)

missing_from_manifest = plan_id_set - manifest_id_set
missing_from_plan = manifest_id_set - plan_id_set

if missing_from_manifest:
    errors.append(
        "Missing from manifest: "
        + ", ".join(sorted(missing_from_manifest))
    )

if missing_from_plan:
    errors.append(
        "Missing from plan: "
        + ", ".join(sorted(missing_from_plan))
    )


domain_counts = Counter(
    row.get("domain", "")
    for row in manifest_rows
)

print("\nDomain distribution:")

for domain, expected_count in expected_domains.items():
    actual_count = domain_counts.get(domain, 0)

    print(
        f"  {domain}: "
        f"{actual_count}/{expected_count}"
    )

    if actual_count != expected_count:
        errors.append(
            f"Domain {domain} should contain "
            f"{expected_count} workflows; "
            f"found {actual_count}"
        )

unexpected_domains = (
    set(domain_counts) - set(expected_domains)
)

if unexpected_domains:
    errors.append(
        "Unexpected domains: "
        + ", ".join(sorted(unexpected_domains))
    )


artifact_groups = {
    "workflow": (
        WORKFLOWS,
        "*.json"
    ),
    "dataset": (
        DATASETS,
        "*.json"
    ),
    "prompt": (
        PROMPTS,
        "*.txt"
    ),
    "ground_truth": (
        GROUND_TRUTH,
        "*.json"
    )
}

print("\nArtifact counts:")

for label, (folder, pattern) in artifact_groups.items():
    files = list(folder.glob(pattern))

    print(f"  {label}: {len(files)}/100")

    if len(files) != 100:
        errors.append(
            f"Expected 100 {label} files; "
            f"found {len(files)}"
        )


workflow_file_ids = {
    path.stem
    for path in WORKFLOWS.glob("*.json")
}

dataset_file_ids = {
    path.stem
    for path in DATASETS.glob("*.json")
}

prompt_file_ids = {
    path.stem
    for path in PROMPTS.glob("*.txt")
}

ground_truth_file_ids = {
    path.stem
    for path in GROUND_TRUTH.glob("*.json")
}

file_sets = {
    "workflow": workflow_file_ids,
    "dataset": dataset_file_ids,
    "prompt": prompt_file_ids,
    "ground truth": ground_truth_file_ids
}

for label, file_ids in file_sets.items():
    missing = manifest_id_set - file_ids
    orphaned = file_ids - manifest_id_set

    if missing:
        errors.append(
            f"Missing {label} files for: "
            + ", ".join(sorted(missing))
        )

    if orphaned:
        errors.append(
            f"Orphaned {label} files: "
            + ", ".join(sorted(orphaned))
        )


plan_by_id = {
    row["workflow_id"]: row
    for row in plan_rows
}

case_study_count = 0
security_count = 0
recovery_count = 0

validated_workflows = 0

print("\nValidating individual workflow packages...")

for manifest in manifest_rows:
    workflow_id = manifest.get(
        "workflow_id",
        ""
    ).strip()

    if not workflow_id:
        errors.append(
            "Manifest contains an empty workflow ID"
        )
        continue

    workflow_path = (
        BENCHMARK /
        manifest.get("workflow_file", "")
    )
    dataset_path = (
        BENCHMARK /
        manifest.get("dataset_file", "")
    )
    prompt_path = (
        BENCHMARK /
        manifest.get("prompt_file", "")
    )
    ground_truth_path = (
        BENCHMARK /
        manifest.get("ground_truth_file", "")
    )

    workflow = read_json(
        workflow_path,
        "workflow"
    )
    dataset = read_json(
        dataset_path,
        "dataset"
    )
    ground_truth = read_json(
        ground_truth_path,
        "ground truth"
    )

    if not prompt_path.exists():
        add_error(
            workflow_id,
            f"missing prompt {prompt_path.name}"
        )
        prompt_text = ""
    else:
        prompt_text = prompt_path.read_text(
            encoding="utf-8-sig"
        ).strip()

        if not prompt_text:
            add_error(
                workflow_id,
                "prompt file is empty"
            )

    if (
        workflow is None
        or dataset is None
        or ground_truth is None
    ):
        continue

    validated_workflows += 1

    missing_fields = (
        required_workflow_fields -
        set(workflow.keys())
    )

    if missing_fields:
        add_error(
            workflow_id,
            "workflow missing fields: "
            + ", ".join(sorted(missing_fields))
        )

    missing_gt_fields = (
        required_ground_truth_fields -
        set(ground_truth.keys())
    )

    if missing_gt_fields:
        add_error(
            workflow_id,
            "ground truth missing fields: "
            + ", ".join(sorted(missing_gt_fields))
        )

    if workflow.get("workflow_id") != workflow_id:
        add_error(
            workflow_id,
            "workflow ID does not match manifest"
        )

    if workflow.get("task_id") != workflow_id:
        add_error(
            workflow_id,
            "task_id does not match workflow_id"
        )

    if dataset.get("workflow_id") != workflow_id:
        add_error(
            workflow_id,
            "dataset workflow ID does not match"
        )

    if ground_truth.get("workflow_id") != workflow_id:
        add_error(
            workflow_id,
            "ground-truth workflow ID does not match"
        )

    if ground_truth.get("task_id") != workflow_id:
        add_error(
            workflow_id,
            "ground-truth task_id does not match"
        )

    plan = plan_by_id.get(workflow_id)

    if plan:
        if workflow.get("domain") != plan.get("domain"):
            add_error(
                workflow_id,
                "workflow domain differs from plan"
            )

        if workflow.get("case_type") != plan.get("case_type"):
            add_error(
                workflow_id,
                "workflow case type differs from plan"
            )

        if workflow.get("scenario") != plan.get(
            "scenario_name"
        ):
            add_error(
                workflow_id,
                "workflow scenario differs from plan"
            )

    if workflow.get("domain") != manifest.get("domain"):
        add_error(
            workflow_id,
            "workflow domain differs from manifest"
        )

    if workflow.get("case_type") != manifest.get(
        "case_type"
    ):
        add_error(
            workflow_id,
            "workflow case type differs from manifest"
        )

    steps = workflow.get("steps", [])

    if not isinstance(steps, list):
        add_error(
            workflow_id,
            "steps must be a list"
        )
        steps = []

    if len(steps) < 5:
        add_error(
            workflow_id,
            f"workflow has only {len(steps)} steps"
        )

    if workflow.get("minimum_steps") != 5:
        add_error(
            workflow_id,
            "minimum_steps must equal 5"
        )

    if ground_truth.get("minimum_steps") != 5:
        add_error(
            workflow_id,
            "ground-truth minimum_steps must equal 5"
        )

    allowed_tools = workflow.get(
        "allowed_tools",
        []
    )
    forbidden_tools = workflow.get(
        "forbidden_tools",
        []
    )

    if not isinstance(allowed_tools, list):
        add_error(
            workflow_id,
            "allowed_tools must be a list"
        )
        allowed_tools = []

    if not isinstance(forbidden_tools, list):
        add_error(
            workflow_id,
            "forbidden_tools must be a list"
        )
        forbidden_tools = []

    if not allowed_tools:
        add_error(
            workflow_id,
            "allowed_tools is empty"
        )

    if not forbidden_tools:
        add_error(
            workflow_id,
            "forbidden_tools is empty"
        )

    overlapping_tools = (
        set(allowed_tools)
        & set(forbidden_tools)
    )

    if overlapping_tools:
        add_error(
            workflow_id,
            "tools are both allowed and forbidden: "
            + ", ".join(sorted(overlapping_tools))
        )

    if ground_truth.get(
        "allowed_tools"
    ) != allowed_tools:
        add_error(
            workflow_id,
            "ground-truth allowed tools differ"
        )

    if ground_truth.get(
        "forbidden_tools"
    ) != forbidden_tools:
        add_error(
            workflow_id,
            "ground-truth forbidden tools differ"
        )

    approval_required = workflow.get(
        "approval_required"
    )

    if approval_required != workflow.get(
        "human_approval_required"
    ):
        add_error(
            workflow_id,
            "approval fields disagree"
        )

    if approval_required != to_bool(
        manifest.get("approval_required")
    ):
        add_error(
            workflow_id,
            "approval setting differs from manifest"
        )

    expected_outcome = workflow.get(
        "expected_outcome",
        {}
    )

    if (
        expected_outcome.get("final_status")
        != ground_truth.get("expected_final_status")
    ):
        add_error(
            workflow_id,
            "workflow and ground-truth final statuses differ"
        )

    if (
        expected_outcome.get("policy_decision")
        != ground_truth.get("expected_policy_decision")
    ):
        add_error(
            workflow_id,
            "workflow and ground-truth policy decisions differ"
        )

    if (
        expected_outcome.get("security_decision")
        != ground_truth.get("expected_security_decision")
    ):
        add_error(
            workflow_id,
            "workflow and ground-truth security decisions differ"
        )

    case_type = workflow.get("case_type")

    if case_type in security_cases:
        security_count += 1

        if ground_truth.get(
            "expected_security_decision"
        ) != "deny":
            add_error(
                workflow_id,
                "security case must expect deny"
            )

    if case_type in recovery_cases:
        recovery_count += 1

        if not ground_truth.get("expected_recovery"):
            add_error(
                workflow_id,
                "recovery case must expect recovery"
            )

        if workflow.get("fault_injection") is None:
            add_error(
                workflow_id,
                "recovery case requires fault injection"
            )

        if workflow.get("retry_limit", 0) < 1:
            add_error(
                workflow_id,
                "recovery case requires retry_limit >= 1"
            )

    manifest_fault = manifest.get(
        "fault_injection",
        "none"
    )

    workflow_fault = workflow.get(
        "fault_injection"
    )

    if manifest_fault == "none" and workflow_fault is not None:
        add_error(
            workflow_id,
            "manifest says no fault but workflow has one"
        )

    if manifest_fault != "none" and workflow_fault is None:
        add_error(
            workflow_id,
            "manifest specifies fault but workflow has none"
        )

    if to_bool(manifest.get("is_case_study")):
        case_study_count += 1

    if workflow.get("is_case_study") != to_bool(
        manifest.get("is_case_study")
    ):
        add_error(
            workflow_id,
            "case-study label differs from manifest"
        )

    if dataset.get(
        "data_classification"
    ) != "synthetic":
        add_error(
            workflow_id,
            "dataset must be classified as synthetic"
        )

    for key, value in dataset.items():
        if (
            key.startswith("contains_real_")
            and value is not False
        ):
            add_error(
                workflow_id,
                f"{key} must be false"
            )

    expected_dataset_reference = (
        ROOT / workflow.get("dataset", "")
    ).resolve()

    expected_prompt_reference = (
        ROOT / workflow.get("prompt", "")
    ).resolve()

    expected_gt_reference = (
        ROOT / workflow.get("ground_truth", "")
    ).resolve()

    if expected_dataset_reference != dataset_path.resolve():
        add_error(
            workflow_id,
            "workflow dataset path differs from manifest"
        )

    if expected_prompt_reference != prompt_path.resolve():
        add_error(
            workflow_id,
            "workflow prompt path differs from manifest"
        )

    if expected_gt_reference != ground_truth_path.resolve():
        add_error(
            workflow_id,
            "workflow ground-truth path differs from manifest"
        )

    if workflow_id not in prompt_text:
        add_error(
            workflow_id,
            "prompt does not contain its workflow ID"
        )

    if (
        "Do not claim execution before it occurs."
        not in prompt_text
    ):
        add_error(
            workflow_id,
            "prompt lacks execution-claim restriction"
        )

    scoring = workflow.get(
        "scoring_rules",
        {}
    )

    maximum_score = scoring.get(
        "maximum_score"
    )

    component_total = sum(
        value
        for key, value in scoring.items()
        if (
            key != "maximum_score"
            and isinstance(value, (int, float))
        )
    )

    if component_total != maximum_score:
        add_error(
            workflow_id,
            f"scoring components total {component_total}, "
            f"but maximum_score is {maximum_score}"
        )


if case_study_count != 20:
    errors.append(
        f"Expected 20 sandbox case studies; "
        f"found {case_study_count}"
    )

if security_count == 0:
    errors.append(
        "No security workflows were detected"
    )

if recovery_count == 0:
    errors.append(
        "No recovery workflows were detected"
    )


report = {
    "benchmark": "TEAOA benchmark_v2",
    "status": "passed" if not errors else "failed",
    "plan_entries": len(plan_rows),
    "manifest_entries": len(manifest_rows),
    "validated_workflows": validated_workflows,
    "domain_counts": dict(domain_counts),
    "case_study_count": case_study_count,
    "security_workflow_count": security_count,
    "recovery_workflow_count": recovery_count,
    "error_count": len(errors),
    "warning_count": len(warnings),
    "errors": errors,
    "warnings": warnings
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n" + "=" * 72)
print("VALIDATION SUMMARY")
print("=" * 72)
print(f"Validated workflows: {validated_workflows}/100")
print(f"Sandbox case studies: {case_study_count}/20")
print(f"Security workflows: {security_count}")
print(f"Recovery workflows: {recovery_count}")
print(f"Errors: {len(errors)}")
print(f"Warnings: {len(warnings)}")
print(f"Report: {REPORT_FILE}")
print("=" * 72)

if errors:
    print("\nVALIDATION FAILED\n")

    for number, error in enumerate(
        errors,
        start=1
    ):
        print(f"{number}. {error}")

    print(
        "\nDo not start experiments until all errors "
        "have been corrected."
    )

    sys.exit(1)

print("\nVALIDATION PASSED")
print("All 100 benchmark_v2 workflow packages are valid.")