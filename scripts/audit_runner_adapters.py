from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

DESIGN_FILE = (
    ROOT / "experiment" / "experiment_design.json"
)

FRAMEWORKS = ROOT / "frameworks"
RUNNER = ROOT / "runner"
TEAOA = ROOT / "teaoa"
RESULTS = ROOT / "results"

REPORT_FILE = RESULTS / "adapter_runner_audit.json"

RESULTS.mkdir(parents=True, exist_ok=True)


design = json.loads(
    DESIGN_FILE.read_text(encoding="utf-8-sig")
)

framework_files = sorted(
    path.relative_to(ROOT).as_posix()
    for path in FRAMEWORKS.rglob("*.py")
)

runner_files = sorted(
    path.relative_to(ROOT).as_posix()
    for path in RUNNER.rglob("*.py")
)

configured_adapters = []

for framework in design.get("frameworks", []):
    adapter_path = ROOT / framework["adapter"]

    configured_adapters.append({
        "framework": framework["name"],
        "configured_path": framework["adapter"],
        "marked_implemented": framework["implemented"],
        "file_exists": adapter_path.is_file()
    })


search_patterns = [
    "benchmark/tasks",
    "benchmark\\tasks",
    "benchmark_manifest.csv",
    "first_action",
    "first-action",
    "range(2)",
    "repetitions = 2",
    "repetitions=2",
    "10 tasks",
    "10 scenarios",
    "max_steps",
    "allowed_tools",
    "forbidden_tools",
    "evaluate_action",
    "tool_broker",
    "benchmark_v2"
]

findings = []

files_to_scan = (
    list(FRAMEWORKS.rglob("*.py"))
    + list(RUNNER.rglob("*.py"))
)

for path in files_to_scan:
    try:
        text = path.read_text(
            encoding="utf-8-sig",
            errors="replace"
        )
    except Exception as error:
        findings.append({
            "file": path.relative_to(ROOT).as_posix(),
            "pattern": "READ_ERROR",
            "line": 0,
            "text": str(error)
        })
        continue

    for line_number, line in enumerate(
        text.splitlines(),
        start=1
    ):
        lowered_line = line.lower()

        for pattern in search_patterns:
            if pattern.lower() in lowered_line:
                findings.append({
                    "file": path.relative_to(ROOT).as_posix(),
                    "pattern": pattern,
                    "line": line_number,
                    "text": line.strip()
                })


required_teaoa_files = [
    "teaoa/policy.py",
    "teaoa/tool_broker.py",
    "teaoa/__init__.py"
]

teaoa_status = []

for relative_path in required_teaoa_files:
    path = ROOT / relative_path

    teaoa_status.append({
        "file": relative_path,
        "exists": path.is_file()
    })


gitignore_path = ROOT / ".gitignore"

if gitignore_path.exists():
    gitignore_text = gitignore_path.read_text(
        encoding="utf-8-sig",
        errors="replace"
    )
else:
    gitignore_text = ""

env_ignored = any(
    line.strip() in {".env", "*.env"}
    for line in gitignore_text.splitlines()
)


report = {
    "configured_adapters": configured_adapters,
    "actual_framework_files": framework_files,
    "actual_runner_files": runner_files,
    "teaoa_core_files": teaoa_status,
    "env_ignored": env_ignored,
    "pilot_assumption_findings": findings
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)


print("=" * 70)
print("TEAOA ADAPTER AND RUNNER AUDIT")
print("=" * 70)

print("\nConfigured adapters:")

for adapter in configured_adapters:
    status = (
        "FOUND"
        if adapter["file_exists"]
        else "MISSING"
    )

    print(
        f"{status}: {adapter['framework']} -> "
        f"{adapter['configured_path']} "
        f"(implemented={adapter['marked_implemented']})"
    )

print("\nActual framework Python files:")

for file in framework_files:
    print(f"  {file}")

print("\nActual runner Python files:")

for file in runner_files:
    print(f"  {file}")

print("\nTEAOA core files:")

for item in teaoa_status:
    status = "FOUND" if item["exists"] else "MISSING"
    print(f"{status}: {item['file']}")

print(f"\n.env ignored: {env_ignored}")
print(
    "Potential pilot assumptions found:",
    len(findings)
)
print(f"Report: {REPORT_FILE}")

print("=" * 70)
print("AUDIT COMPLETE — NO FILES WERE MODIFIED")