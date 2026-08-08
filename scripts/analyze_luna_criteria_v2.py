from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy import stats


RESULTS_DIR = Path("results/benchmark_v2/full_experiment")
OUTPUT_DIR = Path(
    "results/benchmark_v2/statistical_analysis_luna/"
    "criterion_analysis"
)

ALPHA = 0.05


def holm_correction(p_values):
    p_values = np.asarray(p_values, dtype=float)
    count = len(p_values)

    order = np.argsort(p_values)
    adjusted = np.empty(count)
    previous = 0.0

    for rank, index in enumerate(order):
        corrected = (count - rank) * p_values[index]
        corrected = min(max(previous, corrected), 1.0)

        adjusted[index] = corrected
        previous = corrected

    return adjusted


def cohens_h(native_rate, teaoa_rate):
    native_rate = np.clip(native_rate, 0, 1)
    teaoa_rate = np.clip(teaoa_rate, 0, 1)

    return (
        2 * np.arcsin(np.sqrt(teaoa_rate))
        - 2 * np.arcsin(np.sqrt(native_rate))
    )


def load_criterion_records():
    records = []
    valid_result_files = 0

    files = sorted(RESULTS_DIR.glob("*.json"))

    for file_path in files:
        with file_path.open("r", encoding="utf-8") as file:
            result = json.load(file)

        if (
            result.get("batch_status") != "completed"
            or not result.get("score")
        ):
            continue

        valid_result_files += 1

        workflow_id = result["workflow_id"]
        framework = result["framework"]
        configuration = result["configuration"]

        criterion_results = result["score"].get(
            "criterion_results",
            [],
        )

        for criterion in criterion_results:
            records.append(
                {
                    "Workflow": workflow_id,
                    "Framework": framework,
                    "Configuration": configuration,
                    "Criterion": criterion["criterion"],
                    "Weight": criterion["weight"],
                    "Passed": bool(criterion["passed"]),
                    "AwardedScore": criterion[
                        "awarded_score"
                    ],
                    "SourceFile": file_path.name,
                }
            )

    if valid_result_files != 1000:
        raise ValueError(
            "Expected 1000 completed scored files, "
            f"found {valid_result_files}"
        )

    return pd.DataFrame(records)


def create_paired_criteria(criterion_data):
    native = (
        criterion_data[
            criterion_data["Configuration"] == "native"
        ]
        .set_index(
            ["Framework", "Workflow", "Criterion"]
        )
        .add_suffix("_native")
    )

    teaoa = (
        criterion_data[
            criterion_data["Configuration"] == "teaoa"
        ]
        .set_index(
            ["Framework", "Workflow", "Criterion"]
        )
        .add_suffix("_teaoa")
    )

    return native.join(teaoa, how="inner").reset_index()


def analyse_criterion(group):
    native = group["Passed_native"].astype(bool)
    teaoa = group["Passed_teaoa"].astype(bool)

    native_only = int((native & ~teaoa).sum())
    teaoa_only = int((~native & teaoa).sum())

    discordant = native_only + teaoa_only

    if discordant:
        p_value = stats.binomtest(
            min(native_only, teaoa_only),
            discordant,
            p=0.5,
            alternative="two-sided",
        ).pvalue
    else:
        p_value = 1.0

    native_rate = native.mean()
    teaoa_rate = teaoa.mean()

    paired_differences = (
        teaoa.astype(int) - native.astype(int)
    )

    difference = paired_differences.mean()
    sample_size = len(paired_differences)

    if sample_size > 1:
        standard_error = stats.sem(paired_differences)
        critical_value = stats.t.ppf(
            1 - ALPHA / 2,
            sample_size - 1,
        )

        confidence_low = (
            difference - critical_value * standard_error
        )

        confidence_high = (
            difference + critical_value * standard_error
        )
    else:
        confidence_low = np.nan
        confidence_high = np.nan

    matched_odds_ratio = (
        (teaoa_only + 0.5) / (native_only + 0.5)
    )

    return {
        "criterion": group["Criterion"].iloc[0],
        "paired_runs": sample_size,
        "native_pass_rate": native_rate * 100,
        "teaoa_pass_rate": teaoa_rate * 100,
        "pass_rate_difference_points": difference * 100,
        "difference_ci95_low_points": confidence_low * 100,
        "difference_ci95_high_points": confidence_high * 100,
        "native_only_passed": native_only,
        "teaoa_only_passed": teaoa_only,
        "discordant_pairs": discordant,
        "mcnemar_exact_p_value": p_value,
        "matched_odds_ratio": matched_odds_ratio,
        "cohens_h": cohens_h(
            native_rate,
            teaoa_rate,
        ),
        "native_average_awarded_score": (
            group["AwardedScore_native"].mean()
        ),
        "teaoa_average_awarded_score": (
            group["AwardedScore_teaoa"].mean()
        ),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    criterion_data = load_criterion_records()

    criterion_data.to_csv(
        OUTPUT_DIR / "criterion_run_records.csv",
        index=False,
    )

    paired_data = create_paired_criteria(criterion_data)

    paired_data.to_csv(
        OUTPUT_DIR / "criterion_native_teaoa_pairs.csv",
        index=False,
    )

    results = []

    for criterion_name, group in paired_data.groupby(
        "Criterion"
    ):
        results.append(analyse_criterion(group))

    results_table = pd.DataFrame(results)

    results_table["mcnemar_p_value_holm"] = (
        holm_correction(
            results_table[
                "mcnemar_exact_p_value"
            ].to_numpy()
        )
    )

    results_table["significant_after_holm"] = (
        results_table["mcnemar_p_value_holm"] < ALPHA
    )

    results_table = results_table.sort_values(
        "pass_rate_difference_points",
        ascending=False,
    )

    numeric_columns = results_table.select_dtypes(
        include=[np.number]
    ).columns

    results_table[numeric_columns] = (
        results_table[numeric_columns].round(6)
    )

    csv_path = OUTPUT_DIR / "criterion_statistical_results.csv"
    json_path = OUTPUT_DIR / "criterion_statistical_results.json"

    results_table.to_csv(csv_path, index=False)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(
            results_table.to_dict(orient="records"),
            file,
            indent=2,
        )

    display_columns = [
        "criterion",
        "paired_runs",
        "native_pass_rate",
        "teaoa_pass_rate",
        "pass_rate_difference_points",
        "mcnemar_exact_p_value",
        "mcnemar_p_value_holm",
        "matched_odds_ratio",
        "significant_after_holm",
    ]

    print("\nSCORING-CRITERION ANALYSIS\n")

    print(
        results_table[display_columns].to_string(
            index=False
        )
    )

    print("\nCriterion analysis completed.")
    print(f"Criteria analysed: {len(results_table)}")
    print(f"CSV report: {csv_path}")
    print(f"JSON report: {json_path}")
    print("No API calls were made.")


if __name__ == "__main__":
    main()