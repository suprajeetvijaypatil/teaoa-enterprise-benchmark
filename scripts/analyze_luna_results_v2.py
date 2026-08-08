from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy import stats


INPUT_FILE = Path("results/benchmark_v2/luna_run_scores.csv")
OUTPUT_DIR = Path("results/benchmark_v2/statistical_analysis_luna")

ALPHA = 0.05


def calculate_power(effect_size, sample_size, alpha=0.05):
    if sample_size < 2 or not np.isfinite(effect_size):
        return np.nan

    degrees_freedom = sample_size - 1
    critical_value = stats.t.ppf(
        1 - alpha / 2,
        degrees_freedom,
    )

    noncentrality = abs(effect_size) * np.sqrt(sample_size)

    lower_power = stats.nct.cdf(
        -critical_value,
        degrees_freedom,
        noncentrality,
    )

    upper_power = 1 - stats.nct.cdf(
        critical_value,
        degrees_freedom,
        noncentrality,
    )

    return lower_power + upper_power


def holm_correction(p_values):
    p_values = np.asarray(p_values, dtype=float)
    number_of_tests = len(p_values)

    order = np.argsort(p_values)
    adjusted = np.empty(number_of_tests)

    previous = 0.0

    for rank, index in enumerate(order):
        corrected = (number_of_tests - rank) * p_values[index]
        corrected = max(previous, corrected)
        corrected = min(corrected, 1.0)

        adjusted[index] = corrected
        previous = corrected

    return adjusted


def create_pairs(data, framework=None):
    if framework is not None:
        data = data[data["Framework"] == framework].copy()

    native = data[data["Configuration"] == "native"].copy()
    teaoa = data[data["Configuration"] == "teaoa"].copy()

    pair_columns = ["Framework", "Workflow"]

    native = native.set_index(pair_columns)
    teaoa = teaoa.set_index(pair_columns)

    pairs = native[
        [
            "Percentage",
            "Completed",
            "ModelTurns",
            "TotalTokens",
        ]
    ].join(
        teaoa[
            [
                "Percentage",
                "Completed",
                "ModelTurns",
                "TotalTokens",
            ]
        ],
        how="inner",
        lsuffix="_native",
        rsuffix="_teaoa",
    )

    return pairs.reset_index()


def analyse_pairs(pairs, framework_name):
    native_scores = pairs["Percentage_native"].astype(float)
    teaoa_scores = pairs["Percentage_teaoa"].astype(float)

    differences = teaoa_scores - native_scores

    sample_size = len(differences)
    mean_difference = differences.mean()
    difference_sd = differences.std(ddof=1)

    if sample_size > 1:
        standard_error = stats.sem(differences)
        critical_value = stats.t.ppf(
            1 - ALPHA / 2,
            sample_size - 1,
        )

        confidence_low = mean_difference - (
            critical_value * standard_error
        )
        confidence_high = mean_difference + (
            critical_value * standard_error
        )
    else:
        confidence_low = np.nan
        confidence_high = np.nan

    if difference_sd > 0:
        effect_size = mean_difference / difference_sd
        t_statistic, t_p_value = stats.ttest_rel(
            teaoa_scores,
            native_scores,
        )
    else:
        effect_size = 0.0
        t_statistic = 0.0
        t_p_value = 1.0

    if np.allclose(differences, 0):
        wilcoxon_statistic = 0.0
        wilcoxon_p_value = 1.0
    else:
        wilcoxon_result = stats.wilcoxon(
            teaoa_scores,
            native_scores,
            zero_method="wilcox",
            alternative="two-sided",
        )

        wilcoxon_statistic = wilcoxon_result.statistic
        wilcoxon_p_value = wilcoxon_result.pvalue

    native_completed = (
        pairs["Completed_native"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    teaoa_completed = (
        pairs["Completed_teaoa"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    native_only = int(
        (native_completed & ~teaoa_completed).sum()
    )

    teaoa_only = int(
        (~native_completed & teaoa_completed).sum()
    )

    discordant_pairs = native_only + teaoa_only

    if discordant_pairs > 0:
        mcnemar_p_value = stats.binomtest(
            min(native_only, teaoa_only),
            discordant_pairs,
            p=0.5,
            alternative="two-sided",
        ).pvalue
    else:
        mcnemar_p_value = 1.0

    statistical_power = calculate_power(
        effect_size,
        sample_size,
        ALPHA,
    )

    return {
        "framework": framework_name,
        "paired_runs": sample_size,
        "native_mean_score": native_scores.mean(),
        "native_score_sd": native_scores.std(ddof=1),
        "teaoa_mean_score": teaoa_scores.mean(),
        "teaoa_score_sd": teaoa_scores.std(ddof=1),
        "mean_difference_teaoa_minus_native": mean_difference,
        "difference_sd": difference_sd,
        "difference_ci95_low": confidence_low,
        "difference_ci95_high": confidence_high,
        "paired_t_statistic": t_statistic,
        "paired_t_p_value": t_p_value,
        "wilcoxon_statistic": wilcoxon_statistic,
        "wilcoxon_p_value": wilcoxon_p_value,
        "cohens_dz": effect_size,
        "observed_power": statistical_power,
        "native_completion_rate": (
            native_completed.mean() * 100
        ),
        "teaoa_completion_rate": (
            teaoa_completed.mean() * 100
        ),
        "completion_difference_points": (
            teaoa_completed.mean() -
            native_completed.mean()
        ) * 100,
        "native_only_completed": native_only,
        "teaoa_only_completed": teaoa_only,
        "mcnemar_exact_p_value": mcnemar_p_value,
        "native_average_turns": (
            pairs["ModelTurns_native"].mean()
        ),
        "teaoa_average_turns": (
            pairs["ModelTurns_teaoa"].mean()
        ),
        "native_average_tokens": (
            pairs["TotalTokens_native"].mean()
        ),
        "teaoa_average_tokens": (
            pairs["TotalTokens_teaoa"].mean()
        ),
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data = pd.read_csv(INPUT_FILE)

    required_columns = {
        "Workflow",
        "Framework",
        "Configuration",
        "Percentage",
        "Completed",
        "ModelTurns",
        "TotalTokens",
    }

    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    if len(data) != 1000:
        raise ValueError(
            f"Expected 1000 scored runs, found {len(data)}"
        )

    frameworks = sorted(data["Framework"].unique())

    all_pairs = create_pairs(data)

    if len(all_pairs) != 500:
        raise ValueError(
            f"Expected 500 overall pairs, found {len(all_pairs)}"
        )

    all_pairs.to_csv(
        OUTPUT_DIR / "all_native_teaoa_pairs.csv",
        index=False,
    )

    results = [
        analyse_pairs(all_pairs, "all_frameworks")
    ]

    framework_pairs = {}

    for framework in frameworks:
        pairs = create_pairs(data, framework)

        if len(pairs) != 100:
            raise ValueError(
                f"{framework}: expected 100 pairs, "
                f"found {len(pairs)}"
            )

        framework_pairs[framework] = pairs

        pairs.to_csv(
            OUTPUT_DIR / f"{framework}_pairs.csv",
            index=False,
        )

        results.append(
            analyse_pairs(pairs, framework)
        )

    results_table = pd.DataFrame(results)

    framework_mask = (
        results_table["framework"] != "all_frameworks"
    )

    framework_p_values = results_table.loc[
        framework_mask,
        "paired_t_p_value",
    ].to_numpy()

    results_table.loc[
        framework_mask,
        "paired_t_p_value_holm",
    ] = holm_correction(framework_p_values)

    results_table.loc[
        framework_mask,
        "significant_after_holm",
    ] = (
        results_table.loc[
            framework_mask,
            "paired_t_p_value_holm",
        ] < ALPHA
    )

    numeric_columns = results_table.select_dtypes(
        include=[np.number]
    ).columns

    results_table[numeric_columns] = (
        results_table[numeric_columns].round(6)
    )

    csv_output = OUTPUT_DIR / "paired_statistical_results.csv"
    json_output = OUTPUT_DIR / "paired_statistical_results.json"

    results_table.to_csv(
        csv_output,
        index=False,
    )

    with json_output.open("w", encoding="utf-8") as file:
        json.dump(
            results_table.to_dict(orient="records"),
            file,
            indent=2,
        )

    display_columns = [
        "framework",
        "paired_runs",
        "native_mean_score",
        "teaoa_mean_score",
        "mean_difference_teaoa_minus_native",
        "difference_ci95_low",
        "difference_ci95_high",
        "paired_t_p_value",
        "cohens_dz",
        "observed_power",
    ]

    print("\nPAIRED NATIVE VS TEAOA ANALYSIS\n")
    print(
        results_table[display_columns].to_string(
            index=False
        )
    )

    print("\nAnalysis completed.")
    print(f"CSV report: {csv_output}")
    print(f"JSON report: {json_output}")
    print("No API calls were made.")


if __name__ == "__main__":
    main()