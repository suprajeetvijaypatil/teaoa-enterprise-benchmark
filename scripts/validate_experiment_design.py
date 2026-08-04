from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

DESIGN_FILE = (
    ROOT / "experiment" / "experiment_design.json"
)

errors = []
warnings = []


def add_error(message):
    errors.append(message)


if not DESIGN_FILE.exists():
    add_error(
        f"Missing experiment design: {DESIGN_FILE}"
    )
    design = {}
else:
    try:
        design = json.loads(
            DESIGN_FILE.read_text(
                encoding="utf-8-sig"
            )
        )
    except json.JSONDecodeError as error:
        add_error(
            f"Invalid experiment-design JSON: {error}"
        )
        design = {}


manifest_path = ROOT / design.get(
    "benchmark_manifest",
    ""
)

if not manifest_path.exists():
    add_error(
        f"Missing benchmark manifest: {manifest_path}"
    )
    manifest_rows = []
else:
    with manifest_path.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        manifest_rows = list(csv.DictReader(file))


if len(manifest_rows) != 100:
    add_error(
        f"Expected 100 workflows; "
        f"found {len(manifest_rows)}"
    )


frameworks = design.get("frameworks", [])
framework_names = [
    framework.get("name")
    for framework in frameworks
]

if len(framework_names) != 8:
    add_error(
        f"Expected 8 frameworks; "
        f"found {len(framework_names)}"
    )

if len(framework_names) != len(set(framework_names)):
    add_error("Duplicate framework names found")


conditions = design.get("conditions", [])

if set(conditions) != {"native", "teaoa"}:
    add_error(
        "Conditions must be native and teaoa"
    )


models = design.get("models", [])

if len(models) < 2:
    add_error(
        "At least two models are required"
    )

for model in models:
    if model.get("enabled"):
        provider = model.get("provider", "")
        model_id = model.get("model_id", "")

        if "REPLACE_WITH" in provider:
            warnings.append(
                f"{model.get('alias')}: provider "
                f"has not been configured"
            )

        if "REPLACE_WITH" in model_id:
            warnings.append(
                f"{model.get('alias')}: model ID "
                f"has not been configured"
            )


temperatures = design.get("temperatures", [])

if len(temperatures) < 2:
    add_error(
        "At least two temperatures are required"
    )

if design.get("repetitions", 0) < 10:
    add_error(
        "Confirmatory design requires at least "
        "10 repetitions"
    )


stages = design.get("stages", {})

enabled_stages = [
    name
    for name, settings in stages.items()
    if settings.get("enabled")
]

if enabled_stages != ["smoke_test"]:
    add_error(
        "Only smoke_test should be enabled initially"
    )


smoke = stages.get("smoke_test", {})

calculated_smoke_runs = (
    smoke.get("workflow_count", 0)
    * len(smoke.get("frameworks", []))
    * len(smoke.get("conditions", []))
    * len(smoke.get("models", []))
    * len(smoke.get("temperatures", []))
    * smoke.get("repetitions", 0)
)

if calculated_smoke_runs != smoke.get(
    "maximum_runs"
):
    add_error(
        "Smoke-test run calculation does not match "
        f"maximum_runs: calculated "
        f"{calculated_smoke_runs}"
    )

if calculated_smoke_runs > 56:
    add_error(
        "Smoke test exceeds the approved safety cap "
        "of 56 runs"
    )


for stage_name, settings in stages.items():
    for framework_name in settings.get(
        "frameworks",
        []
    ):
        if framework_name not in framework_names:
            add_error(
                f"{stage_name}: unknown framework "
                f"{framework_name}"
            )


stopping_rules = design.get(
    "stopping_rules",
    {}
)

required_stopping_rules = [
    "stop_on_invalid_benchmark",
    "stop_on_missing_adapter",
    "stop_on_missing_model_id",
    "stop_on_authentication_failure",
    "stop_on_unexpected_paid_run_count",
    "stop_on_unsafe_execution",
    "stop_on_result_schema_failure"
]

for rule in required_stopping_rules:
    if stopping_rules.get(rule) is not True:
        add_error(
            f"Stopping rule must be enabled: {rule}"
        )


print("=" * 65)
print("TEAOA EXPERIMENT DESIGN VALIDATION")
print("=" * 65)
print(f"Benchmark workflows: {len(manifest_rows)}")
print(f"Frameworks: {len(framework_names)}")
print(f"Models: {len(models)}")
print(f"Temperatures: {temperatures}")
print(f"Repetitions: {design.get('repetitions')}")
print(f"Enabled stages: {enabled_stages}")
print(f"Smoke-test runs: {calculated_smoke_runs}")
print(f"Errors: {len(errors)}")
print(f"Warnings: {len(warnings)}")
print("=" * 65)

if warnings:
    print("\nWARNINGS:")

    for number, warning in enumerate(
        warnings,
        start=1
    ):
        print(f"{number}. {warning}")

if errors:
    print("\nEXPERIMENT DESIGN INVALID:")

    for number, error in enumerate(
        errors,
        start=1
    ):
        print(f"{number}. {error}")

    sys.exit(1)

print("\nEXPERIMENT DESIGN STRUCTURE PASSED")

if warnings:
    print(
        "Replace all model/provider placeholders "
        "before generating or running the smoke test."
    )