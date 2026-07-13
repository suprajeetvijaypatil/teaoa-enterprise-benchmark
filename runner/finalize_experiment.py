from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

try:
    from scipy.stats import binomtest, wilcoxon
except ImportError:
    binomtest = None
    wilcoxon = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIRECTORY = PROJECT_ROOT / "benchmark" / "tasks"
RAW_DIRECTORY = PROJECT_ROOT / "results" / "raw"
PROCESSED_DIRECTORY = PROJECT_ROOT / "results" / "processed"
FIGURE_DIRECTORY = PROJECT_ROOT / "results" / "figures"

FRAMEWORKS = [
    "langgraph",
    "crewai",
    "autogen",
    "semantic_kernel",
]
CONFIGURATIONS = [
    "native",
    "teaoa",
]
REPEATS = [
    1,
    2,
]


def load_expected_task_ids() -> list[str]:
    task_ids: list[str] = []

    for path in sorted(TASK_DIRECTORY.glob("*.json")):
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise ValueError(f"Empty benchmark task: {path.name}")

        task = json.loads(text)
        if "task_id" not in task:
            raise ValueError(f"Missing task_id in {path.name}")

        task_ids.append(str(task["task_id"]))

    if len(task_ids) != 10:
        raise RuntimeError(
            f"Expected 10 benchmark tasks, but found {len(task_ids)}."
        )

    if len(set(task_ids)) != len(task_ids):
        raise RuntimeError("Duplicate task_id values exist in benchmark tasks.")

    return task_ids


def flatten_record(record: dict[str, Any], filename: str) -> dict[str, Any]:
    execution = record.get("execution_result", {})

    return {
        "filename": filename,
        "framework": str(record.get("framework", "")),
        "configuration": str(record.get("configuration", "")),
        "repeat_number": int(record.get("repeat_number", 0)),
        "task_id": str(record.get("task_id", "")),
        "domain": str(record.get("domain", "")),
        "scenario": str(record.get("scenario", "")),
        "risk_class": str(record.get("risk_class", "")),
        "proposed_tool": str(record.get("proposed_tool", "")),
        "execution_status": str(execution.get("status", "")),
        "policy_decision": str(record.get("policy_decision", "")),
        "step_success": bool(record.get("step_success", False)),
        "sla_compliant": bool(record.get("sla_compliant", False)),
        "unsafe_action_attempts": int(
            record.get("unsafe_action_attempts", 0)
        ),
        "unsafe_actions_executed": int(
            record.get("unsafe_actions_executed", 0)
        ),
        "governance_violations": int(
            record.get("governance_violations", 0)
        ),
        "human_interventions": int(
            record.get("human_interventions", 0)
        ),
        "tool_failures": int(record.get("tool_failures", 0)),
        "recovered_failures": int(
            record.get("recovered_failures", 0)
        ),
        "input_tokens": int(record.get("input_tokens", 0)),
        "output_tokens": int(record.get("output_tokens", 0)),
        "estimated_cost_usd": float(
            record.get("estimated_cost_usd", 0.0)
        ),
        "model_latency_seconds": float(
            record.get("model_latency_seconds", 0.0)
        ),
        "total_latency_seconds": float(
            record.get("total_latency_seconds", 0.0)
        ),
    }


def load_and_validate_records(
    expected_task_ids: list[str],
) -> pd.DataFrame:
    expected_keys = {
        (framework, configuration, task_id, repeat)
        for framework in FRAMEWORKS
        for configuration in CONFIGURATIONS
        for task_id in expected_task_ids
        for repeat in REPEATS
    }

    records_by_key: dict[
        tuple[str, str, str, int],
        dict[str, Any],
    ] = {}
    duplicate_files: defaultdict[
        tuple[str, str, str, int],
        list[str],
    ] = defaultdict(list)

    for path in sorted(RAW_DIRECTORY.glob("*.json")):
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise ValueError(f"Empty raw result file: {path.name}")

        record = json.loads(text)

        key = (
            str(record.get("framework", "")),
            str(record.get("configuration", "")),
            str(record.get("task_id", "")),
            int(record.get("repeat_number", 0)),
        )

        if key not in expected_keys:
            continue

        if key in records_by_key:
            duplicate_files[key].append(path.name)
            continue

        records_by_key[key] = flatten_record(record, path.name)

    if duplicate_files:
        lines = [
            f"{key}: {files}"
            for key, files in duplicate_files.items()
        ]
        raise RuntimeError(
            "Duplicate generalized result records were found:\n"
            + "\n".join(lines)
        )

    missing = sorted(expected_keys - set(records_by_key))

    if missing:
        preview = "\n".join(str(item) for item in missing[:20])
        raise RuntimeError(
            f"Experiment is incomplete. Missing {len(missing)} result "
            f"records. First missing records:\n{preview}"
        )

    rows = [
        records_by_key[key]
        for key in sorted(records_by_key)
    ]

    dataframe = pd.DataFrame(rows)

    if len(dataframe) != 160:
        raise RuntimeError(
            f"Expected 160 validated records, but found {len(dataframe)}."
        )

    return dataframe


def wilson_interval(
    successes: int,
    total: int,
    z_value: float = 1.96,
) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0

    proportion = successes / total
    denominator = 1 + (z_value**2 / total)

    centre = (
        proportion
        + z_value**2 / (2 * total)
    ) / denominator

    margin = (
        z_value
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z_value**2 / (4 * total**2)
        )
        / denominator
    )

    return max(0.0, centre - margin), min(1.0, centre + margin)


def create_framework_summary(runs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for (framework, configuration), group in runs.groupby(
        ["framework", "configuration"],
        sort=True,
    ):
        total = len(group)
        successes = int(group["step_success"].sum())
        success_low, success_high = wilson_interval(successes, total)

        sla_successes = int(group["sla_compliant"].sum())
        sla_low, sla_high = wilson_interval(sla_successes, total)

        unsafe_executions = int(
            group["unsafe_actions_executed"].sum()
        )
        violations = int(
            group["governance_violations"].sum()
        )
        failures = int(group["tool_failures"].sum())

        success_rate = successes / total
        safety_rate = 1 - (unsafe_executions / total)
        governance_compliance = 1 - (violations / total)
        sla_rate = sla_successes / total
        tool_reliability = 1 - (failures / total)

        eaori = 100 * (
            0.30 * success_rate
            + 0.25 * safety_rate
            + 0.20 * governance_compliance
            + 0.15 * sla_rate
            + 0.10 * tool_reliability
        )

        rows.append(
            {
                "framework": framework,
                "configuration": configuration,
                "completed_runs": total,
                "successful_runs": successes,
                "success_rate_percent": 100 * success_rate,
                "success_ci95_low_percent": 100 * success_low,
                "success_ci95_high_percent": 100 * success_high,
                "sla_compliant_runs": sla_successes,
                "sla_compliance_percent": 100 * sla_rate,
                "sla_ci95_low_percent": 100 * sla_low,
                "sla_ci95_high_percent": 100 * sla_high,
                "unsafe_action_attempts": int(
                    group["unsafe_action_attempts"].sum()
                ),
                "unsafe_actions_executed": unsafe_executions,
                "governance_violations": violations,
                "human_interventions": int(
                    group["human_interventions"].sum()
                ),
                "tool_failures": failures,
                "recovered_failures": int(
                    group["recovered_failures"].sum()
                ),
                "average_latency_seconds": float(
                    group["total_latency_seconds"].mean()
                ),
                "median_latency_seconds": float(
                    group["total_latency_seconds"].median()
                ),
                "latency_q1_seconds": float(
                    group["total_latency_seconds"].quantile(0.25)
                ),
                "latency_q3_seconds": float(
                    group["total_latency_seconds"].quantile(0.75)
                ),
                "input_tokens": int(group["input_tokens"].sum()),
                "output_tokens": int(group["output_tokens"].sum()),
                "estimated_cost_usd": float(
                    group["estimated_cost_usd"].sum()
                ),
                "exploratory_eaori": eaori,
            }
        )

    return pd.DataFrame(rows)


def create_paired_comparisons(
    runs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    native = runs[runs["configuration"] == "native"].copy()
    teaoa = runs[runs["configuration"] == "teaoa"].copy()

    paired = native.merge(
        teaoa,
        on=["framework", "task_id", "repeat_number"],
        suffixes=("_native", "_teaoa"),
        validate="one_to_one",
    )

    paired["delta_success"] = (
        paired["step_success_teaoa"].astype(int)
        - paired["step_success_native"].astype(int)
    )
    paired["delta_latency_seconds"] = (
        paired["total_latency_seconds_teaoa"]
        - paired["total_latency_seconds_native"]
    )
    paired["delta_unsafe_executions"] = (
        paired["unsafe_actions_executed_teaoa"]
        - paired["unsafe_actions_executed_native"]
    )
    paired["delta_governance_violations"] = (
        paired["governance_violations_teaoa"]
        - paired["governance_violations_native"]
    )

    test_rows: list[dict[str, Any]] = []

    for framework, group in paired.groupby("framework", sort=True):
        native_success = group["step_success_native"].astype(int)
        teaoa_success = group["step_success_teaoa"].astype(int)

        native_only = int(
            ((native_success == 1) & (teaoa_success == 0)).sum()
        )
        teaoa_only = int(
            ((native_success == 0) & (teaoa_success == 1)).sum()
        )
        discordant = native_only + teaoa_only

        if binomtest is not None and discordant > 0:
            success_p = float(
                binomtest(
                    k=teaoa_only,
                    n=discordant,
                    p=0.5,
                    alternative="two-sided",
                ).pvalue
            )
        else:
            success_p = float("nan")

        latency_difference = group["delta_latency_seconds"]

        if (
            wilcoxon is not None
            and len(latency_difference) > 0
            and not (latency_difference == 0).all()
        ):
            try:
                latency_p = float(
                    wilcoxon(latency_difference).pvalue
                )
            except ValueError:
                latency_p = float("nan")
        else:
            latency_p = float("nan")

        test_rows.extend(
            [
                {
                    "framework": framework,
                    "comparison": "step_success_mcnemar_exact",
                    "pairs": len(group),
                    "native_mean": float(native_success.mean()),
                    "teaoa_mean": float(teaoa_success.mean()),
                    "teaoa_minus_native": float(
                        teaoa_success.mean() - native_success.mean()
                    ),
                    "p_value": success_p,
                },
                {
                    "framework": framework,
                    "comparison": "latency_wilcoxon",
                    "pairs": len(group),
                    "native_mean": float(
                        group["total_latency_seconds_native"].mean()
                    ),
                    "teaoa_mean": float(
                        group["total_latency_seconds_teaoa"].mean()
                    ),
                    "teaoa_minus_native": float(
                        latency_difference.mean()
                    ),
                    "p_value": latency_p,
                },
            ]
        )

    return paired, pd.DataFrame(test_rows)


def save_bar_chart(
    summary: pd.DataFrame,
    value_column: str,
    title: str,
    ylabel: str,
    filename: str,
) -> None:
    pivot = summary.pivot(
        index="framework",
        columns="configuration",
        values=value_column,
    )

    figure, axis = plt.subplots(figsize=(8, 5))
    pivot.plot(kind="bar", ax=axis)

    axis.set_title(title)
    axis.set_xlabel("Framework")
    axis.set_ylabel(ylabel)
    axis.tick_params(axis="x", rotation=20)
    axis.legend(title="Configuration")

    figure.tight_layout()

    figure.savefig(
        FIGURE_DIRECTORY / f"{filename}.png",
        dpi=300,
        bbox_inches="tight",
    )
    figure.savefig(
        FIGURE_DIRECTORY / f"{filename}.pdf",
        bbox_inches="tight",
    )
    plt.close(figure)


def save_latency_boxplot(runs: pd.DataFrame) -> None:
    labels: list[str] = []
    values: list[pd.Series] = []

    for framework in FRAMEWORKS:
        for configuration in CONFIGURATIONS:
            group = runs[
                (runs["framework"] == framework)
                & (runs["configuration"] == configuration)
            ]
            labels.append(f"{framework}\n{configuration}")
            values.append(group["total_latency_seconds"])

    figure, axis = plt.subplots(figsize=(11, 5))
    axis.boxplot(values, tick_labels=labels)
    axis.set_title("End-to-End Latency Distribution")
    axis.set_ylabel("Seconds")
    axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()

    figure.savefig(
        FIGURE_DIRECTORY / "latency_boxplot.png",
        dpi=300,
        bbox_inches="tight",
    )
    figure.savefig(
        FIGURE_DIRECTORY / "latency_boxplot.pdf",
        bbox_inches="tight",
    )
    plt.close(figure)


def save_latex_table(summary: pd.DataFrame) -> None:
    path = PROCESSED_DIRECTORY / "pilot_results_table.tex"

    lines = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Budget-Constrained Cross-Framework First-Action Pilot Results}",
        r"\label{tab:cross-framework-pilot}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrrr}",
        r"\toprule",
        (
            r"Framework & Configuration & Runs & Success (\%) & "
            r"SLA (\%) & Unsafe Exec. & Gov. Viol. & "
            r"Median Lat. (s) & Cost (USD) & EAORI \\"
        ),
        r"\midrule",
    ]

    for _, row in summary.sort_values(
        ["framework", "configuration"]
    ).iterrows():
        framework = str(row["framework"]).replace("_", r"\_")
        configuration = str(row["configuration"]).replace("_", r"\_")

        lines.append(
            f"{framework} & {configuration} & "
            f"{int(row['completed_runs'])} & "
            f"{row['success_rate_percent']:.1f} & "
            f"{row['sla_compliance_percent']:.1f} & "
            f"{int(row['unsafe_actions_executed'])} & "
            f"{int(row['governance_violations'])} & "
            f"{row['median_latency_seconds']:.3f} & "
            f"{row['estimated_cost_usd']:.4f} & "
            f"{row['exploratory_eaori']:.1f} \\"
        )

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table*}",
        ]
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_method_notes() -> None:
    path = PROCESSED_DIRECTORY / "paper_results_notes.txt"

    text = '''
Recommended description:

A budget-constrained first-action pilot was conducted across ten synthetic
enterprise scenarios. Four orchestration frameworks were evaluated in native
and TEAOA-governed configurations with two repetitions per scenario, yielding
160 runs. The foundation model, prompt, dynamic tool schemas, synthetic action
semantics, and scoring logic were held constant. Framework-specific runtimes
controlled only the proposal-to-execution sequence.

Important limitation:

The experiment evaluates first-action selection and governance enforcement,
not complete long-horizon workflow completion. Synthetic tools, one foundation
model, two repetitions, and a small task set limit external validity. The
exploratory EAORI score is a proposed composite measure and has not yet been
independently validated.
'''.strip()

    path.write_text(text + "\n", encoding="utf-8")


def main() -> None:
    PROCESSED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    FIGURE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    expected_task_ids = load_expected_task_ids()
    runs = load_and_validate_records(expected_task_ids)

    runs_path = PROCESSED_DIRECTORY / "all_framework_results.csv"
    runs.to_csv(runs_path, index=False)

    summary = create_framework_summary(runs)
    summary_path = PROCESSED_DIRECTORY / "combined_framework_summary.csv"
    summary.to_csv(summary_path, index=False)

    paired, tests = create_paired_comparisons(runs)
    paired_path = PROCESSED_DIRECTORY / "paired_native_teaoa_results.csv"
    tests_path = PROCESSED_DIRECTORY / "paired_statistical_tests.csv"
    paired.to_csv(paired_path, index=False)
    tests.to_csv(tests_path, index=False)

    save_bar_chart(
        summary,
        "success_rate_percent",
        "First-Action Success Rate",
        "Success rate (%)",
        "success_rate",
    )
    save_bar_chart(
        summary,
        "unsafe_actions_executed",
        "Unsafe Actions Executed",
        "Number of executions",
        "unsafe_actions_executed",
    )
    save_bar_chart(
        summary,
        "governance_violations",
        "Governance Violations",
        "Number of violations",
        "governance_violations",
    )
    save_bar_chart(
        summary,
        "estimated_cost_usd",
        "Estimated API Cost",
        "USD",
        "estimated_cost",
    )
    save_bar_chart(
        summary,
        "exploratory_eaori",
        "Exploratory Enterprise Agent Orchestration Readiness Index",
        "EAORI (0-100)",
        "eaori",
    )
    save_latency_boxplot(runs)
    save_latex_table(summary)
    save_method_notes()

    print()
    print("FINAL EXPERIMENT VALIDATION")
    print("-" * 60)
    print(f"Validated generalized runs: {len(runs)}")
    print(f"Task IDs: {len(expected_task_ids)}")
    print()
    print(summary.to_string(index=False))
    print()
    print(f"All runs CSV: {runs_path}")
    print(f"Summary CSV: {summary_path}")
    print(f"Paired results: {paired_path}")
    print(f"Statistical tests: {tests_path}")
    print(
        "LaTeX table: "
        f"{PROCESSED_DIRECTORY / 'pilot_results_table.tex'}"
    )
    print(f"Figures: {FIGURE_DIRECTORY}")
    print()
    print("FINALIZATION COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
