from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy import stats


INPUT_FILE = Path("results/benchmark_v2/luna_run_scores.csv")
OUTPUT_DIR = Path(
    "results/benchmark_v2/statistical_analysis_luna/domain_analysis"
)

DOMAIN_NAMES = {
    "CS": "Customer Support",
    "ERP": "ERP and Procurement",
    "FIN": "Finance and Invoices",
    "HC": "Healthcare",
    "SC": "Supply Chain",
    "SEC": "Security and IT Operations",
    "SWE": "Software Engineering",
}

EXPECTED_PAIRS = {
    "Customer Support": 75,
    "ERP and Procurement": 75,
    "Finance and Invoices": 75,
    "Healthcare": 50,
    "Supply Chain": 75,
    "Security and IT Operations": 75,
    "Software Engineering": 75,
}

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


def calculate_power(effect_size, sample_size):
    if sample_size < 2 or not np.isfinite(effect_size):
        return np.nan

    degrees_freedom = sample_size - 1
    critical_value = stats.t.ppf(
        1 - ALPHA / 2,
        degrees_freedom,
    )

    noncentrality = abs(effect_size) * np.sqrt(sample_size)

    return (
        stats.nct.cdf(
            -critical_value,
            degrees_freedom,
            noncentrality,
        )
        + 1
        - stats.nct.cdf(
            critical_value,
            degrees_freedom,
            noncentrality,
        )
    )


def analyse_domain(domain_data, domain_name):
    native = (
        domain_data[
            domain_data["Configuration"] == "native"
        ]
        .set_index(["Framework", "Workflow"])
        .add_suffix("_native")
    )

    teaoa = (
        domain_data[
            domain_data["Configuration"] == "teaoa"
        ]
        .set_index(["Framework", "Workflow"])
        .add_suffix("_teaoa")
    )

    pairs = native.join(teaoa, how="inner").reset_index()

    expected = EXPECTED_PAIRS[domain_name]

    if len(pairs) != expected:
        raise ValueError(
            f"{domain_name}: expected {expected} pairs, "
            f"found {len(pairs)}"
        )

    native_scores = pairs["Percentage_native"].astype(float)
    teaoa_scores = pairs["Percentage_teaoa"].astype(float)

    differences = teaoa_scores - native_scores

    sample_size = len(differences)
    mean_difference = differences.mean()
    difference_sd = differences.std(ddof=1)

    standard_error = stats.sem(differences)
    critical_value = stats.t.ppf(
        1 - ALPHA / 2,
        sample_size - 1,
    )

    confidence_low = (
        mean_difference - critical_value * standard_error
    )
    confidence_high = (
        mean_difference + critical_value * standard_error
    )

    if difference_sd > 0:
        effect_size = mean_difference / difference_sd

        t_result = stats.ttest_rel(
            teaoa_scores,
            native_scores,
        )
    else:
        effect_size = 0.0
        t_result = None

    if np.allclose(differences, 0):
        wilcoxon_statistic = 0.0
        wilcoxon_p_value = 1.0
    else:
        wilcoxon_result = stats.wilcoxon(
            teaoa_scores,
            native_scores,
            zero_method="wilcox",
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

    discordant = native_only + teaoa_only

    if discordant:
        mcnemar_p_value = stats.binomtest(
            min(native_only, teaoa_only),
            discordant,
            p=0.5,
        ).pvalue
    else:
        mcnemar_p_value = 1.0

    pairs.to_csv(
        OUTPUT_DIR
        / f"{domain_name.lower().replace(' ', '_')}_pairs.csv",
        index=False,
    )

    return {
        "domain": domain_name,
        "paired_runs": sample_size,
        "native_mean_score": native_scores.mean(),
        "native_score_sd": native_scores.std(ddof=1),
        "teaoa_mean_score": teaoa_scores.mean(),
        "teaoa_score_sd": teaoa_scores.std(ddof=1),
        "mean_difference": mean_difference,
        "difference_ci95_low": confidence_low,
        "difference_ci95_high": confidence_high,
        "paired_t_statistic": (
            t_result.statistic if t_result else 0.0
        ),
        "paired_t_p_value": (
            t_result.pvalue if t_result else 1.0
        ),
        "wilcoxon_statistic": wilcoxon_statistic,
        "wilcoxon_p_value": wilcoxon_p_value,
        "cohens_dz": effect_size,
        "observed_power": calculate_power(
            effect_size,
            sample_size,
        ),
        "native_completion_rate": (
            native_completed.mean() * 100
        ),
        "teaoa_completion_rate": (
            teaoa_completed.mean() * 100
        ),
        "completion_difference_points": (
            teaoa_completed.mean()
            - native_completed.mean()
        ) * 100,
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
        raise FileNotFoundError(INPUT_FILE)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data = pd.read_csv(INPUT_FILE)

    data["DomainCode"] = (
        data["Workflow"].str.split("-").str[0]
    )

    data["Domain"] = data["DomainCode"].map(DOMAIN_NAMES)

    if data["Domain"].isna().any():
        unknown = sorted(
            data.loc[data["Domain"].isna(), "Workflow"].unique()
        )

        raise ValueError(
            f"Unknown workflow domain: {unknown}"
        )

    results = []

    for domain_name in DOMAIN_NAMES.values():
        domain_data = data[data["Domain"] == domain_name]

        results.append(
            analyse_domain(domain_data, domain_name)
        )

    results_table = pd.DataFrame(results)

    results_table["paired_t_p_value_holm"] = (
        holm_correction(
            results_table["paired_t_p_value"].to_numpy()
        )
    )

    results_table["significant_after_holm"] = (
        results_table["paired_t_p_value_holm"] < ALPHA
    )

    numeric_columns = results_table.select_dtypes(
        include=[np.number]
    ).columns

    results_table[numeric_columns] = (
        results_table[numeric_columns].round(6)
    )

    csv_path = OUTPUT_DIR / "domain_statistical_results.csv"
    json_path = OUTPUT_DIR / "domain_statistical_results.json"

    results_table.to_csv(csv_path, index=False)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(
            results_table.to_dict(orient="records"),
            file,
            indent=2,
        )

    display_columns = [
        "domain",
        "paired_runs",
        "native_mean_score",
        "teaoa_mean_score",
        "mean_difference",
        "difference_ci95_low",
        "difference_ci95_high",
        "paired_t_p_value",
        "paired_t_p_value_holm",
        "cohens_dz",
    ]

    print("\nDOMAIN-LEVEL NATIVE VS TEAOA ANALYSIS\n")

    print(
        results_table[display_columns].to_string(
            index=False
        )
    )

    print("\nDomain analysis completed.")
    print(f"CSV report: {csv_path}")
    print(f"JSON report: {json_path}")
    print("No API calls were made.")


if __name__ == "__main__":
    main()