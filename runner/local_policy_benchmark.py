import csv
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from teaoa.policy import PolicyDecision, evaluate_action


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_DIRECTORY = (
    PROJECT_ROOT
    / "benchmark"
    / "tasks"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "results"
    / "processed"
    / "local_policy_results.csv"
)


def load_task(path: Path) -> dict[str, Any]:
    """
    Load one benchmark task.

    The utf-8-sig encoding also supports JSON files containing
    an invisible byte-order mark.
    """

    print(f"Loading: {path.name}")

    text = path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not text:
        raise ValueError(
            f"The task file is empty: {path.name}"
        )

    try:
        task = json.loads(text)

    except JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {path.name}: "
            f"line {error.lineno}, "
            f"column {error.colno}. "
            f"{error.msg}"
        ) from error

    if not isinstance(task, dict):
        raise ValueError(
            f"The root JSON value in {path.name} "
            "must be an object."
        )

    return task


def expected_allowed_decision(
    risk_class: str,
    human_approval_required: bool,
) -> PolicyDecision:
    """
    Return the expected policy decision for an allowed tool.
    """

    if (
        human_approval_required
        or risk_class.lower() == "high"
    ):
        return PolicyDecision.REQUIRE_APPROVAL

    return PolicyDecision.ALLOW


def validate_required_fields(
    task: dict[str, Any],
    filename: str,
) -> None:
    """
    Check that each benchmark task contains required fields.
    """

    required_fields = [
        "task_id",
        "domain",
        "scenario",
        "risk_class",
        "allowed_tools",
        "forbidden_tools",
        "human_approval_required",
        "success_conditions",
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in task
    ]

    if missing_fields:
        raise ValueError(
            f"{filename} is missing required fields: "
            f"{', '.join(missing_fields)}"
        )

    if not isinstance(task["allowed_tools"], list):
        raise ValueError(
            f"allowed_tools must be a list in {filename}."
        )

    if not isinstance(task["forbidden_tools"], list):
        raise ValueError(
            f"forbidden_tools must be a list in {filename}."
        )

    if not task["allowed_tools"]:
        raise ValueError(
            f"{filename} has no allowed tools."
        )

    if not task["forbidden_tools"]:
        raise ValueError(
            f"{filename} has no forbidden tools."
        )

    if not isinstance(
        task["human_approval_required"],
        bool,
    ):
        raise ValueError(
            "human_approval_required must be true or false "
            f"in {filename}."
        )


def main() -> None:
    """
    Evaluate allowed and forbidden tool decisions across
    all ten benchmark tasks.
    """

    task_files = sorted(
        TASK_DIRECTORY.glob("*.json")
    )

    if len(task_files) != 10:
        raise RuntimeError(
            "Expected exactly 10 JSON task files, "
            f"but found {len(task_files)} in "
            f"{TASK_DIRECTORY}."
        )

    rows: list[dict[str, Any]] = []

    for task_path in task_files:
        task = load_task(task_path)

        validate_required_fields(
            task=task,
            filename=task_path.name,
        )

        allowed_tools = task["allowed_tools"]
        forbidden_tools = task["forbidden_tools"]
        risk_class = str(task["risk_class"])
        approval_required = bool(
            task["human_approval_required"]
        )

        # Test the first allowed tool.
        allowed_tool = str(allowed_tools[0])

        allowed_decision = evaluate_action(
            tool_name=allowed_tool,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            risk_class=risk_class,
            human_approval_required=(
                approval_required
            ),
        )

        expected_allowed = (
            expected_allowed_decision(
                risk_class=risk_class,
                human_approval_required=(
                    approval_required
                ),
            )
        )

        rows.append(
            {
                "filename": task_path.name,
                "task_id": task["task_id"],
                "domain": task["domain"],
                "scenario": task["scenario"],
                "risk_class": risk_class,
                "check_type": "allowed_tool",
                "tool_name": allowed_tool,
                "actual_decision": (
                    allowed_decision.value
                ),
                "expected_decision": (
                    expected_allowed.value
                ),
                "passed": (
                    allowed_decision
                    == expected_allowed
                ),
            }
        )

        # Test the first forbidden tool.
        forbidden_tool = str(
            forbidden_tools[0]
        )

        forbidden_decision = evaluate_action(
            tool_name=forbidden_tool,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            risk_class=risk_class,
            human_approval_required=(
                approval_required
            ),
        )

        rows.append(
            {
                "filename": task_path.name,
                "task_id": task["task_id"],
                "domain": task["domain"],
                "scenario": task["scenario"],
                "risk_class": risk_class,
                "check_type": "forbidden_tool",
                "tool_name": forbidden_tool,
                "actual_decision": (
                    forbidden_decision.value
                ),
                "expected_decision": (
                    PolicyDecision.DENY.value
                ),
                "passed": (
                    forbidden_decision
                    == PolicyDecision.DENY
                ),
            }
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "filename",
        "task_id",
        "domain",
        "scenario",
        "risk_class",
        "check_type",
        "tool_name",
        "actual_decision",
        "expected_decision",
        "passed",
    ]

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

    passed_checks = sum(
        1
        for row in rows
        if row["passed"] is True
    )

    total_checks = len(rows)

    print()
    print("LOCAL TEAOA POLICY BENCHMARK")
    print("-----------------------------")
    print(f"Tasks evaluated: {len(task_files)}")
    print(
        f"Policy checks passed: "
        f"{passed_checks}/{total_checks}"
    )
    print(f"Results saved to: {OUTPUT_FILE}")

    if passed_checks != total_checks:
        failed_rows = [
            row
            for row in rows
            if row["passed"] is False
        ]

        print()
        print("FAILED CHECKS:")

        for row in failed_rows:
            print(
                f"- {row['task_id']} | "
                f"{row['tool_name']} | "
                f"expected="
                f"{row['expected_decision']} | "
                f"actual="
                f"{row['actual_decision']}"
            )

        raise RuntimeError(
            "One or more policy checks failed. "
            "Review local_policy_results.csv."
        )

    print("All local policy checks passed.")


if __name__ == "__main__":
    main()