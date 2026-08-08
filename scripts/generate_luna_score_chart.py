from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUTPUT_DIR = Path("results/benchmark_v2/statistical_analysis_luna/figures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

frameworks = [
    "AutoGen",
    "CrewAI",
    "LangGraph",
    "OpenAI Agents",
    "Semantic Kernel",
]
native = np.array([35.6785, 36.0893, 33.8927, 34.9106, 35.5357])
teaoa = np.array([36.9641, 37.0176, 36.1427, 36.8926, 36.4462])
p_values = [0.004161, 0.213775, 0.001922, 0.005408, 0.081146]

x = np.arange(len(frameworks))
width = 0.36

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 15,
    "axes.labelsize": 11,
})

fig, ax = plt.subplots(figsize=(11.2, 6.4))
fig.patch.set_facecolor("white")
ax.set_facecolor("#FAFBFC")
fig.subplots_adjust(left=0.08, right=0.98, bottom=0.19, top=0.82)

native_bars = ax.bar(
    x - width / 2,
    native,
    width,
    label="Native",
    color="#607D9B",
    edgecolor="white",
    linewidth=0.8,
)
teaoa_bars = ax.bar(
    x + width / 2,
    teaoa,
    width,
    label="TEAOA",
    color="#1B9E77",
    edgecolor="white",
    linewidth=0.8,
)

ax.set_title(
    "Native vs TEAOA Mean Benchmark Scores",
    loc="left",
    fontweight="bold",
    pad=18,
)
ax.text(
    0,
    1.025,
    "GPT-5.6 Luna | 100 paired workflows per framework | Temperature 0.0",
    transform=ax.transAxes,
    color="#4B5563",
    fontsize=10,
)
ax.set_ylabel("Mean score (%)")
ax.set_xticks(x, frameworks)
ax.set_ylim(30, 40.5)
ax.grid(axis="y", color="#D8DEE6", linewidth=0.8, alpha=0.8)
ax.set_axisbelow(True)

for spine in ["top", "right", "left"]:
    ax.spines[spine].set_visible(False)
ax.spines["bottom"].set_color("#AAB2BD")

ax.bar_label(native_bars, fmt="%.2f", padding=3, fontsize=9)
ax.bar_label(teaoa_bars, fmt="%.2f", padding=3, fontsize=9)

for index, (native_score, teaoa_score, p_value) in enumerate(
    zip(native, teaoa, p_values)
):
    difference = teaoa_score - native_score
    significance = "*" if p_value < 0.05 else "ns"
    ax.text(
        index,
        max(native_score, teaoa_score) + 0.85,
        f"Delta +{difference:.2f} | p={p_value:.3f} {significance}",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#303640",
    )

ax.legend(
    frameon=False,
    ncol=2,
    loc="upper right",
    bbox_to_anchor=(1, 1.19),
)

fig.text(
    0.08,
    0.035,
    "Note: * p < 0.05 (uncorrected paired t-test); ns = not significant. "
    "Overall paired effect: +1.47 points, p < 0.001, Cohen's dz = 0.233.",
    fontsize=8.5,
    color="#4B5563",
)

png_path = OUTPUT_DIR / "luna_native_vs_teaoa_mean_scores.png"
pdf_path = OUTPUT_DIR / "luna_native_vs_teaoa_mean_scores.pdf"

fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
fig.savefig(pdf_path, bbox_inches="tight", facecolor="white")
plt.close(fig)

print(png_path.resolve())
print(pdf_path.resolve())
