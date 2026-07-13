from __future__ import annotations
import argparse
import json
import subprocess
import sys
from runner.shared_experiment import PROJECT_ROOT, list_task_files, result_path

RUNNER_MODULES = {
    "langgraph": "frameworks.langgraph.all_tasks_runner",
    "crewai": "frameworks.crewai.all_tasks_runner",
    "autogen": "frameworks.autogen.all_tasks_runner",
    "semantic_kernel": "frameworks.semantic_kernel.all_tasks_runner",
}
LOCAL_BUDGET_LIMIT_USD = 8.00

def existing_estimated_cost() -> float:
    total = 0.0
    raw = PROJECT_ROOT / "results" / "raw"
    for path in raw.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            total += float(data.get("estimated_cost_usd", 0.0))
        except (ValueError, json.JSONDecodeError):
            continue
    return total

def run_matrix(framework: str, repeats: int, task_limit: int | None, dry_run: bool) -> None:
    task_files = list_task_files()
    if task_limit is not None:
        task_files = task_files[:task_limit]
    module = RUNNER_MODULES[framework]
    planned = skipped = 0
    for task_path in task_files:
        task = json.loads(task_path.read_text(encoding="utf-8-sig"))
        for configuration in ("native", "teaoa"):
            for repeat in range(1, repeats + 1):
                path = result_path(framework, configuration, str(task["task_id"]), repeat)
                if path.exists() and path.stat().st_size > 0:
                    print(f"SKIP existing: {path.name}")
                    skipped += 1
                    continue
                if existing_estimated_cost() >= LOCAL_BUDGET_LIMIT_USD:
                    raise RuntimeError("Local estimated spend reached the $8 stop limit.")
                command = [
                    sys.executable, "-m", module,
                    "--task", task_path.name,
                    "--configuration", configuration,
                    "--repeat", str(repeat),
                ]
                print("RUN:", " ".join(command))
                planned += 1
                if not dry_run:
                    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    print()
    print(f"Framework: {framework}")
    print(f"New runs planned/executed: {planned}")
    print(f"Existing runs skipped: {skipped}")
    print(f"Local estimated spend: ${existing_estimated_cost():.6f}")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", choices=list(RUNNER_MODULES), required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--task-limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_matrix(args.framework, args.repeats, args.task_limit, args.dry_run)
