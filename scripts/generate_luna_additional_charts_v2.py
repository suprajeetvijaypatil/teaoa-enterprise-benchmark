from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE_DIR = Path(
    "results/benchmark_v2/statistical_analysis_luna"
)
FIGURE_DIR = BASE_DIR / "figures"

SUMMARY_FILE = Path(
    "results/benchmark_v2/"
    "luna_summary_by_framework_configuration.csv"
)

DOMAIN_FILE = (
    BASE_DIR
    / "domain_analysis"
    / "domain_statistical_results.csv"
)

CRITERION_FILE = (
    BASE_DIR
    / "criterion_analysis"
    / "criterion_statistical_results.csv"
)

NATIVE_COLOR = "#607D9B"
TEAOA_COLOR = "#1B9E77"
GRID_COLOR = "#D8DEE6"


def configure_plot():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "figure.facecolor": "white",
            "axes.facecolor": "#FAFBFC",
        }
    )


def style_axis(axis):
    axis.grid(
        axis="y",
        color=GRID_COLOR,
        linewidth=0.8,
        alpha=0.8,
    )
    axis.set_axisbelow(True)

    for spine in ["top", "right", "left"]:
        axis.spines[spine].set_visible(False)

    axis.spines["bottom"].set_color("#AAB2BD")


def save_figure(figure, filename):
    png_path = FIGURE_DIR / f"{filename}.png"
    pdf_path = FIGURE_DIR / f"{filename}.pdf"

    figure.savefig(
        png_path,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )

    figure.savefig(
        pdf_path,
        bbox_inches="tight",
        facecolor="white",
    )

    plt.close(figure)

    print(f"Saved: {png_path}")
    print(f"Saved: {pdf_path}")


def add_bar_labels(axis, bars, decimals=1):
    label_format = f"%.{decimals}f"

    axis.bar_label(
        bars,
        fmt=label_format,
        padding=3,
        fontsize=8.5,
    )


def generate_domain_chart():
    data = pd.read_csv(DOMAIN_FILE)

    domains = data["domain"].tolist()
    native = data["native_mean_score"].to_numpy()
    teaoa = data["teaoa_mean_score"].to_numpy()

    x = np.arange(len(domains))
    width = 0.36

    figure, axis = plt.subplots(figsize=(13, 7))

    native_bars = axis.bar(
        x - width / 2,
        native,
        width,
        label="Native",
        color=NATIVE_COLOR,
        edgecolor="white",
    )

    teaoa_bars = axis.bar(
        x + width / 2,
        teaoa,
        width,
        label="TEAOA",
        color=TEAOA_COLOR,
        edgecolor="white",
    )

    axis.set_title(
        "Native vs TEAOA Scores by Enterprise Domain",
        loc="left",
        fontweight="bold",
        pad=18,
    )

    axis.text(
        0,
        1.01,
        "Paired GPT-5.6 Luna benchmark results",
        transform=axis.transAxes,
        color="#4B5563",
    )

    axis.set_ylabel("Mean score (%)")
    axis.set_xticks(x)

    axis.set_xticklabels(
        [
            label.replace(" and ", "\nand ")
            for label in domains
        ],
        rotation=0,
        ha="center",
    )

    axis.set_ylim(0, 65)
    style_axis(axis)

    add_bar_labels(axis, native_bars, 1)
    add_bar_labels(axis, teaoa_bars, 1)

    for index, row in data.iterrows():
        adjusted_p = row["paired_t_p_value_holm"]
        significant = "*" if adjusted_p < 0.05 else "ns"

        axis.text(
            index,
            max(
                row["native_mean_score"],
                row["teaoa_mean_score"],
            ) + 4.5,
            (
                f"Delta {row['mean_difference']:+.2f}\n"
                f"p-adj={adjusted_p:.3f} {significant}"
            ),
            ha="center",
            fontsize=8,
            color="#303640",
        )

    axis.legend(
        frameon=False,
        ncol=2,
        loc="upper right",
    )

    figure.subplots_adjust(
        left=0.07,
        right=0.98,
        bottom=0.20,
        top=0.86,
    )

    figure.text(
        0.07,
        0.04,
        "* Holm-adjusted p < 0.05; ns = not significant.",
        fontsize=8.5,
        color="#4B5563",
    )

    save_figure(
        figure,
        "luna_domain_native_vs_teaoa_scores",
    )


def generate_criterion_chart():
    data = pd.read_csv(CRITERION_FILE)

    data = data.sort_values(
        "pass_rate_difference_points",
        ascending=True,
    )

    labels = [
        label.replace("_", " ").title()
        for label in data["criterion"]
    ]

    native = data["native_pass_rate"].to_numpy()
    teaoa = data["teaoa_pass_rate"].to_numpy()

    y = np.arange(len(labels))
    height = 0.36

    figure, axis = plt.subplots(figsize=(12, 9))

    native_bars = axis.barh(
        y - height / 2,
        native,
        height,
        label="Native",
        color=NATIVE_COLOR,
        edgecolor="white",
    )

    teaoa_bars = axis.barh(
        y + height / 2,
        teaoa,
        height,
        label="TEAOA",
        color=TEAOA_COLOR,
        edgecolor="white",
    )

    axis.set_title(
        "Scoring-Criterion Pass Rates",
        loc="left",
        fontweight="bold",
        pad=18,
    )

    axis.text(
        0,
        1.01,
        "Paired native and TEAOA criterion outcomes",
        transform=axis.transAxes,
        color="#4B5563",
    )

    axis.set_xlabel("Pass rate (%)")
    axis.set_yticks(y, labels)
    axis.set_xlim(0, 108)

    axis.grid(
        axis="x",
        color=GRID_COLOR,
        linewidth=0.8,
        alpha=0.8,
    )

    axis.set_axisbelow(True)

    for spine in ["top", "right", "bottom"]:
        axis.spines[spine].set_visible(False)

    axis.spines["left"].set_color("#AAB2BD")

    axis.bar_label(
        native_bars,
        fmt="%.1f",
        padding=3,
        fontsize=8,
    )

    axis.bar_label(
        teaoa_bars,
        fmt="%.1f",
        padding=3,
        fontsize=8,
    )

    axis.legend(
        frameon=False,
        ncol=2,
        loc="lower right",
    )

    figure.subplots_adjust(
        left=0.31,
        right=0.97,
        bottom=0.10,
        top=0.89,
    )

    figure.text(
        0.31,
        0.025,
        (
            "Correct recovery or escalation was the only "
            "criterion significant after Holm correction."
        ),
        fontsize=8.5,
        color="#4B5563",
    )

    save_figure(
        figure,
        "luna_criterion_pass_rates",
    )


def generate_completion_chart():
    data = pd.read_csv(SUMMARY_FILE)

    framework_order = [
        "autogen",
        "crewai",
        "langgraph",
        "openai_agents",
        "semantic_kernel",
    ]

    display_names = {
        "autogen": "AutoGen",
        "crewai": "CrewAI",
        "langgraph": "LangGraph",
        "openai_agents": "OpenAI Agents",
        "semantic_kernel": "Semantic Kernel",
    }

    native = (
        data[data["Configuration"] == "native"]
        .set_index("Framework")
        .loc[framework_order]
    )

    teaoa = (
        data[data["Configuration"] == "teaoa"]
        .set_index("Framework")
        .loc[framework_order]
    )

    x = np.arange(len(framework_order))
    width = 0.36

    figure, axis = plt.subplots(figsize=(11.5, 6.5))

    native_bars = axis.bar(
        x - width / 2,
        native["CompletionRate"],
        width,
        label="Native",
        color=NATIVE_COLOR,
        edgecolor="white",
    )

    teaoa_bars = axis.bar(
        x + width / 2,
        teaoa["CompletionRate"],
        width,
        label="TEAOA",
        color=TEAOA_COLOR,
        edgecolor="white",
    )

    axis.set_title(
        "Workflow Runtime Completion Rates",
        loc="left",
        fontweight="bold",
        pad=18,
    )

    axis.text(
        0,
        1.01,
        (
            "Runtime completion indicates normal model-reported "
            "completion, not strict scorer completion"
        ),
        transform=axis.transAxes,
        color="#4B5563",
        fontsize=9.5,
    )

    axis.set_ylabel("Completion rate (%)")
    axis.set_xticks(
        x,
        [display_names[name] for name in framework_order],
    )

    axis.set_ylim(0, 100)
    style_axis(axis)

    add_bar_labels(axis, native_bars, 0)
    add_bar_labels(axis, teaoa_bars, 0)

    axis.legend(
        frameon=False,
        ncol=2,
        loc="upper right",
    )

    figure.subplots_adjust(
        left=0.08,
        right=0.98,
        bottom=0.16,
        top=0.84,
    )

    figure.text(
        0.08,
        0.035,
        (
            "Overall completion: Native 83.4%; "
            "TEAOA 81.2%; McNemar p=0.126."
        ),
        fontsize=8.5,
        color="#4B5563",
    )

    save_figure(
        figure,
        "luna_framework_completion_rates",
    )


def generate_efficiency_chart():
    data = pd.read_csv(SUMMARY_FILE)

    framework_order = [
        "autogen",
        "crewai",
        "langgraph",
        "openai_agents",
        "semantic_kernel",
    ]

    display_names = [
        "AutoGen",
        "CrewAI",
        "LangGraph",
        "OpenAI Agents",
        "Semantic Kernel",
    ]

    native = (
        data[data["Configuration"] == "native"]
        .set_index("Framework")
        .loc[framework_order]
    )

    teaoa = (
        data[data["Configuration"] == "teaoa"]
        .set_index("Framework")
        .loc[framework_order]
    )

    x = np.arange(len(framework_order))
    width = 0.36

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(14, 6.5),
    )

    native_turn_bars = axes[0].bar(
        x - width / 2,
        native["AverageTurns"],
        width,
        label="Native",
        color=NATIVE_COLOR,
        edgecolor="white",
    )

    teaoa_turn_bars = axes[0].bar(
        x + width / 2,
        teaoa["AverageTurns"],
        width,
        label="TEAOA",
        color=TEAOA_COLOR,
        edgecolor="white",
    )

    axes[0].set_title(
        "Average Model Turns",
        fontweight="bold",
    )

    axes[0].set_ylabel("Turns per run")
    axes[0].set_xticks(x, display_names, rotation=20)
    axes[0].set_ylim(0, 12)

    style_axis(axes[0])
    add_bar_labels(axes[0], native_turn_bars, 1)
    add_bar_labels(axes[0], teaoa_turn_bars, 1)

    native_token_bars = axes[1].bar(
        x - width / 2,
        native["AverageTokens"] / 1000,
        width,
        label="Native",
        color=NATIVE_COLOR,
        edgecolor="white",
    )

    teaoa_token_bars = axes[1].bar(
        x + width / 2,
        teaoa["AverageTokens"] / 1000,
        width,
        label="TEAOA",
        color=TEAOA_COLOR,
        edgecolor="white",
    )

    axes[1].set_title(
        "Average Token Usage",
        fontweight="bold",
    )

    axes[1].set_ylabel("Tokens per run (thousands)")
    axes[1].set_xticks(x, display_names, rotation=20)
    axes[1].set_ylim(0, 36)

    style_axis(axes[1])
    add_bar_labels(axes[1], native_token_bars, 1)
    add_bar_labels(axes[1], teaoa_token_bars, 1)

    figure.suptitle(
        "Native vs TEAOA Execution Efficiency",
        x=0.06,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )

    figure.legend(
        handles=[
            native_turn_bars,
            teaoa_turn_bars,
        ],
        labels=[
            "Native",
            "TEAOA",
        ],
        frameon=False,
        ncol=2,
        loc="upper right",
        bbox_to_anchor=(0.98, 0.98),
    )

    figure.subplots_adjust(
        left=0.06,
        right=0.98,
        bottom=0.19,
        top=0.83,
        wspace=0.22,
    )

    figure.text(
        0.06,
        0.035,
        (
            "Across all frameworks, TEAOA used approximately "
            "9.1% fewer turns and 9.0% fewer tokens."
        ),
        fontsize=8.5,
        color="#4B5563",
    )

    save_figure(
        figure,
        "luna_execution_efficiency",
    )


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    configure_plot()

    generate_domain_chart()
    generate_criterion_chart()
    generate_completion_chart()
    generate_efficiency_chart()

    print("\nAll additional charts generated.")
    print(f"Output directory: {FIGURE_DIR.resolve()}")
    print("No API calls were made.")


if __name__ == "__main__":
    main()