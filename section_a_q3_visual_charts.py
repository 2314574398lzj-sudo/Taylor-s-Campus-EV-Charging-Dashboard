"""
section_a_q3_visual_charts.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section A, Question 3 (5 marks)

Two executive-report charts, each built twice - once with explicit Matplotlib
primitives and once with the declarative Seaborn API - so the comparison in the
report is backed by code and by measured construction times:

    Chart 1  grouped multi-bar : hourly charging revenue split by AC / DC
    Chart 2  correlation heatmap: ambient temperature, duration, grid load

Outputs (assets/figures):
    fig_a3_chart1_matplotlib_vs_seaborn.png
    fig_a3_chart2_matplotlib_vs_seaborn.png

Run with::

    python section_a_q3_visual_charts.py
"""

from __future__ import annotations

import timeit
from pathlib import Path
from typing import Final

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import visualisations as viz

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
CLEAN_CSV: Final[Path] = BASE_DIR / "assets" / "cleaned_energy_sales_data.csv"
FIGURE_DIR: Final[Path] = BASE_DIR / "assets" / "figures"

matplotlib.use("Agg")          # headless rendering for the report pipeline


def _banner(title: str) -> None:
    """Print a consistent console section header."""
    print("\n" + "=" * 78)
    print(f" {title}")
    print("=" * 78)


# --------------------------------------------------------------------------- #
# Chart 1 - grouped multi-bar: hourly revenue by charger type
# --------------------------------------------------------------------------- #
def chart1_matplotlib(frame: pd.DataFrame) -> plt.Figure:
    """Explicit Matplotlib implementation: every artist is positioned by hand."""
    pivot = (frame.pivot_table(index="Start_Hour", columns="Charger_Type",
                               values="Net_Billable_MYR", aggfunc="sum",
                               fill_value=0.0)
             .reindex(range(24), fill_value=0.0))
    fig, ax = plt.subplots(figsize=(7.6, 3.9))
    hours = np.arange(24)
    width = 0.40
    ax.bar(hours - width / 2, pivot["AC"], width=width, color="#2E75B6",
           label="AC", edgecolor="white", linewidth=0.5)
    ax.bar(hours + width / 2, pivot["DC"], width=width, color="#C55A11",
           label="DC", edgecolor="white", linewidth=0.5)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{hour:02d}" for hour in hours], fontsize=7)
    ax.set_xlabel("Hour of day (24-hour clock)")
    ax.set_ylabel("Net billable revenue (MYR)")
    ax.set_title("Chart 1 — Matplotlib: hourly revenue by charger type")
    ax.legend(title="Charger", frameon=False, fontsize=8, title_fontsize=8)
    ax.grid(axis="y", color="#E6E6E6")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return fig


def chart1_seaborn(frame: pd.DataFrame) -> plt.Figure:
    """Declarative Seaborn implementation: grouping, hue and legend are implied."""
    long = (frame.groupby(["Start_Hour", "Charger_Type"], as_index=False)
            ["Net_Billable_MYR"].sum())
    fig, ax = plt.subplots(figsize=(7.6, 3.9))
    sns.barplot(data=long, x="Start_Hour", y="Net_Billable_MYR",
                hue="Charger_Type", hue_order=["AC", "DC"],
                palette={"AC": "#2E75B6", "DC": "#C55A11"},
                width=0.78, ax=ax)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{hour:02d}" for hour in range(0, 24, 2)], fontsize=8)
    ax.set_xlabel("Hour of day (24-hour clock)")
    ax.set_ylabel("Net billable revenue (MYR)")
    ax.set_title("Chart 1 — Seaborn: hourly revenue by charger type")
    ax.legend(title="Charger", frameon=False, fontsize=8, title_fontsize=8)
    return fig


# --------------------------------------------------------------------------- #
# Chart 2 - correlation heatmap
# --------------------------------------------------------------------------- #
def chart2_matplotlib(frame: pd.DataFrame) -> plt.Figure:
    """Matplotlib ``imshow`` heatmap: masking, ticks and labels written manually."""
    corr = viz.correlation_matrix(frame)
    values = corr.to_numpy()
    upper = np.triu(np.ones_like(values, dtype=bool), k=1)
    masked = np.ma.array(values, mask=upper)

    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    image = ax.imshow(masked, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    cbar = fig.colorbar(image, ax=ax, shrink=0.78)
    cbar.set_label("Pearson r", fontsize=8)
    ticks = np.arange(len(corr))
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels(corr.columns, rotation=35, ha="right", fontsize=7)
    ax.set_yticklabels(corr.index, fontsize=7)
    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            if not upper[row, col]:
                ax.text(col, row, f"{values[row, col]:.2f}", ha="center",
                        va="center", fontsize=7.5,
                        color="white" if abs(values[row, col]) > 0.55 else "black")
    ax.set_title("Chart 2 — Matplotlib: temperature / duration / load", fontsize=10)
    return fig


def chart2_seaborn(frame: pd.DataFrame) -> plt.Figure:
    """Seaborn ``heatmap``: masking, annotation and colour bar built in."""
    corr = viz.correlation_matrix(frame)
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", annot_kws={"size": 8},
                cmap="vlag", vmin=-1, vmax=1, center=0, square=True,
                linewidths=1.2, linecolor="white",
                cbar_kws={"shrink": 0.78, "label": "Pearson r"}, ax=ax)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right", fontsize=7)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=7)
    ax.set_title("Chart 2 — Seaborn: temperature / duration / load", fontsize=10)
    return fig


# --------------------------------------------------------------------------- #
# Timing harness
# --------------------------------------------------------------------------- #
def time_builder(builder, frame: pd.DataFrame, repeats: int = 7) -> float:
    """Return the fastest construction time (seconds) of ``builder(frame)``.

    Figures are closed after each run so that no memory or rendering state is
    carried between timings; ``min`` is used because the fastest run is the
    least contaminated by background OS activity.
    """

    def run_once() -> None:
        figure = builder(frame)
        plt.close(figure)

    return min(timeit.repeat(run_once, number=1, repeat=repeats))


def main() -> int:
    """Render both charts in both libraries and report the timings."""
    print("ITS72604 FINAL EXAMINATION - SECTION A, QUESTION 3")
    print("Matplotlib vs Seaborn: design, code effort and execution cost")

    frame = pd.read_csv(CLEAN_CSV)
    viz.apply_house_style()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------- Chart 1 -------------------------------------------- #
    _banner("CHART 1 - grouped multi-bar: hourly revenue by charger type")
    fig1 = chart1_matplotlib(frame)
    fig1.tight_layout()
    fig1.savefig(FIGURE_DIR / "fig_a3_chart1_matplotlib.png", dpi=300,
                 bbox_inches="tight", facecolor="white")
    plt.close(fig1)

    fig1b = chart1_seaborn(frame)
    fig1b.tight_layout()
    fig1b.savefig(FIGURE_DIR / "fig_a3_chart1_seaborn.png", dpi=300,
                  bbox_inches="tight", facecolor="white")
    plt.close(fig1b)

    # ---------------- Chart 2 -------------------------------------------- #
    _banner("CHART 2 - correlation heatmap of temperature, duration and load")
    fig2 = chart2_matplotlib(frame)
    fig2.tight_layout()
    fig2.savefig(FIGURE_DIR / "fig_a3_chart2_matplotlib.png", dpi=300,
                 bbox_inches="tight", facecolor="white")
    plt.close(fig2)

    fig2b = chart2_seaborn(frame)
    fig2b.tight_layout()
    fig2b.savefig(FIGURE_DIR / "fig_a3_chart2_seaborn.png", dpi=300,
                  bbox_inches="tight", facecolor="white")
    plt.close(fig2b)

    # ---------------- Measured comparison -------------------------------- #
    _banner("MEASURED CONSTRUCTION TIME (fastest of 7 runs, seconds)")
    timings = {
        "chart1_matplotlib": time_builder(chart1_matplotlib, frame),
        "chart1_seaborn": time_builder(chart1_seaborn, frame),
        "chart2_matplotlib": time_builder(chart2_matplotlib, frame),
        "chart2_seaborn": time_builder(chart2_seaborn, frame),
    }
    for name, seconds in timings.items():
        print(f"   {name:<20}: {seconds * 1000:8.2f} ms")

    # ---------------- Data evidence for the narrative -------------------- #
    _banner("DATA EVIDENCE USED IN THE REPORT")
    corr = viz.correlation_matrix(frame)
    print("Correlation matrix (Pearson r):")
    print(corr.round(3).to_string())
    pivot = viz.hourly_revenue_table(frame)
    print(f"\nPeak AC revenue hour            : {pivot['AC'].idxmax():02d}:00 "
          f"({pivot['AC'].max():,.2f} MYR)")
    print(f"Peak DC revenue hour            : {pivot['DC'].idxmax():02d}:00 "
          f"({pivot['DC'].max():,.2f} MYR)")
    print(f"AC share of total revenue       : "
          f"{pivot['AC'].sum() / pivot.sum().sum() * 100:.1f} %")
    load_corr = corr["Grid load / power (kW)"].drop("Grid load / power (kW)")
    print(f"Strongest |r| with grid load    : {load_corr.abs().idxmax()}")

    print("\nFigures written:")
    for path in sorted(FIGURE_DIR.glob("fig_a3_*.png")):
        print(f"   {path.name}  ({path.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
