"""
visualisations.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)

Reusable, publication-quality chart builders for the Smart Campus Energy & EV
Fleet platform.  Every function returns a Matplotlib ``Figure`` so that the
same chart can be rendered to PNG in the report pipeline and streamed into the
Streamlit dashboard without duplicating plotting logic.

Charts
------
``plot_hourly_revenue_by_charger``  Section A Q3 / Section B dashboard
``plot_correlation_heatmap``        Section A Q3
``plot_grid_vs_solar``              Section B Q2 Panel 1
``plot_cost_by_user``               Section B Q2 Panel 2
``plot_temp_vs_energy``             Section B Q2 Panel 3
``build_publication_panel``         Section B Q2 composite three-panel figure
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

# --------------------------------------------------------------------------- #
# House style: one place to change the look of every figure in the submission
# --------------------------------------------------------------------------- #
BRAND_NAVY: Final[str] = "#1F3864"
BRAND_BLUE: Final[str] = "#2E75B6"
BRAND_ORANGE: Final[str] = "#C55A11"
BRAND_GREY: Final[str] = "#7F7F7F"
ACCENT_RED: Final[str] = "#C00000"
SOLAR_GOLD: Final[str] = "#F2B705"

CHARGER_PALETTE: Final[dict[str, str]] = {"AC": BRAND_BLUE, "DC": BRAND_ORANGE}
USER_PALETTE: Final[dict[str, str]] = {
    "Student": BRAND_BLUE,
    "Staff": BRAND_NAVY,
    "Visitor": BRAND_ORANGE,
}
USER_ORDER: Final[list[str]] = ["Student", "Staff", "Visitor"]

# Installed rooftop PV capacity used for the generation curve (kWp)
PV_CAPACITY_KWP: Final[float] = 1200.0
SUNRISE_HOUR: Final[float] = 7.0
SUNSET_HOUR: Final[float] = 19.0


def apply_house_style() -> None:
    """Apply the shared Matplotlib/Seaborn theme (idempotent)."""
    sns.set_theme(context="notebook", style="whitegrid", palette="deep")
    matplotlib.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 11.5,
        "axes.titleweight": "bold",
        "axes.titlecolor": BRAND_NAVY,
        "axes.labelsize": 10,
        "axes.labelcolor": "#333333",
        "axes.edgecolor": "#BFBFBF",
        "axes.grid": True,
        "grid.color": "#E6E6E6",
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "xtick.color": "#404040",
        "ytick.color": "#404040",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


# --------------------------------------------------------------------------- #
# Section A, Question 3 — hourly revenue split by charger type
# --------------------------------------------------------------------------- #
def hourly_revenue_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Pivot net billable revenue into ``hour x charger type`` form (AC/DC).

    Returns
    -------
    pandas.DataFrame
        Index ``Start_Hour`` (0-23); columns ``AC`` and ``DC`` in MYR.
    """
    pivot = (
        frame.pivot_table(index="Start_Hour", columns="Charger_Type",
                          values="Net_Billable_MYR", aggfunc="sum", fill_value=0.0)
        .reindex(range(24), fill_value=0.0)
        .sort_index(axis=1)
    )
    return pivot.round(2)


def plot_hourly_revenue_by_charger(frame: pd.DataFrame,
                                   engine: Literal["matplotlib", "seaborn"] = "seaborn",
                                   ax: plt.Axes | None = None,
                                   show_title: bool = True) -> Figure:
    """Grouped multi-bar chart of hourly revenue split by charger type.

    Parameters
    ----------
    frame:
        Cleaned session table containing ``Start_Hour``, ``Charger_Type`` and
        ``Net_Billable_MYR``.
    engine:
        ``"matplotlib"`` draws the bars explicitly with ``ax.bar`` (full manual
        control, more code); ``"seaborn"`` delegates the grouping, colour
        mapping and legend to ``sns.barplot`` (less code, consistent palette).
    ax:
        Optional existing axes to draw into (used for the side-by-side report
        figure); a new figure is created when omitted.

    Returns
    -------
    matplotlib.figure.Figure
    """
    apply_house_style()
    pivot = hourly_revenue_table(frame)
    hours = pivot.index.to_numpy()
    width = 0.40

    if ax is None:
        fig, ax = plt.subplots(figsize=(9.0, 4.6))
    else:
        fig = ax.get_figure()

    if engine == "matplotlib":
        # --- explicit, low-level Matplotlib implementation ------------------ #
        ax.bar(hours - width / 2, pivot.get("AC", 0.0), width=width,
               color=BRAND_BLUE, edgecolor="white", linewidth=0.6, label="AC")
        ax.bar(hours + width / 2, pivot.get("DC", 0.0), width=width,
               color=BRAND_ORANGE, edgecolor="white", linewidth=0.6, label="DC")
        ax.set_xticks(hours)
        ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)
        ax.legend(title="Charger type", loc="upper left")
        if show_title:
            ax.set_title("Hourly charging revenue by charger type (Matplotlib)")
    else:
        # --- declarative Seaborn implementation --------------------------- #
        long = (frame.groupby(["Start_Hour", "Charger_Type"], as_index=False)
                ["Net_Billable_MYR"].sum())
        sns.barplot(data=long, x="Start_Hour", y="Net_Billable_MYR",
                    hue="Charger_Type", hue_order=["AC", "DC"],
                    palette=CHARGER_PALETTE, width=0.78, ax=ax)
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=8)
        ax.legend(title="Charger type", loc="upper left")
        if show_title:
            ax.set_title("Hourly charging revenue by charger type (Seaborn)")

    ax.set_xlabel("Hour of day (24-hour clock)")
    ax.set_ylabel("Net billable revenue (MYR)")
    ax.margins(x=0.01)
    return fig


# --------------------------------------------------------------------------- #
# Section A, Question 3 — correlation heatmap
# --------------------------------------------------------------------------- #
CORRELATION_FIELDS: Final[dict[str, str]] = {
    "Ambient_Temp_C": "Ambient temp (°C)",
    "Battery_Temp_C": "Battery temp (°C)",
    "Duration_Mins": "Charging duration (min)",
    "Power_Rate_kW": "Grid load / power (kW)",
    "Energy_kWh": "Energy delivered (kWh)",
}


def correlation_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation matrix of the thermal, duration and load fields."""
    columns = [c for c in CORRELATION_FIELDS if c in frame.columns]
    return frame[columns].corr(method="pearson").rename(
        index=CORRELATION_FIELDS, columns=CORRELATION_FIELDS
    )


def plot_correlation_heatmap(frame: pd.DataFrame, show_title: bool = True) -> Figure:
    """Annotated correlation heatmap (masked upper triangle, diverging palette)."""
    apply_house_style()
    corr = correlation_matrix(frame)
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)

    sns.heatmap(
        corr, mask=mask, annot=True, fmt=".2f", annot_kws={"size": 9},
        cmap="vlag", vmin=-1, vmax=1, center=0, square=True,
        linewidths=1.4, linecolor="white",
        cbar_kws={"shrink": 0.72, "label": "Pearson r"},
        ax=ax,
    )
    if show_title:
        ax.set_title(
            "Correlation of ambient temperature, duration and grid load",
            pad=12,
        )
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right", fontsize=9)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=9)
    return fig


# --------------------------------------------------------------------------- #
# Section B, Question 2 — the three dashboard panels
# --------------------------------------------------------------------------- #
def solar_generation_kw(hours: np.ndarray) -> np.ndarray:
    """Modelled rooftop PV output (kW) across the 24-hour day.

    A half-sine irradiance profile is used between 07:00 and 19:00, scaled to
    the installed 1,200 kWp campus array; output is zero outside daylight.

    Parameters
    ----------
    hours:
        Array of clock hours (0-23).

    Returns
    -------
    numpy.ndarray
        Generation in kW, same shape as ``hours``.
    """
    hours = np.asarray(hours, dtype=float)
    daylight = (hours >= SUNRISE_HOUR) & (hours <= SUNSET_HOUR)
    shape = np.sin(np.pi * (hours - SUNRISE_HOUR) / (SUNSET_HOUR - SUNRISE_HOUR))
    return np.where(daylight, PV_CAPACITY_KWP * np.clip(shape, 0.0, 1.0), 0.0)


def hourly_grid_demand(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate observed charging demand and modelled PV supply per hour."""
    demand = (frame.groupby("Start_Hour")
              .agg(Grid_Demand_kWh=("Energy_kWh", "sum"),
                   Sessions=("Session_ID", "count"))
              .reindex(range(24), fill_value=0))
    demand["Solar_Generation_kW"] = solar_generation_kw(demand.index.to_numpy())
    demand["Net_Grid_Load_kWh"] = (demand["Grid_Demand_kWh"]
                                   - demand["Solar_Generation_kW"])
    return demand.reset_index()


def plot_grid_vs_solar(frame: pd.DataFrame, ax: plt.Axes | None = None,
                       show_title: bool = True) -> Figure:
    """Panel 1: hourly grid demand peaks against the modelled solar curve."""
    apply_house_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(9.0, 4.8))
    else:
        fig = ax.get_figure()

    data = hourly_grid_demand(frame)
    sns.lineplot(data=data, x="Start_Hour", y="Grid_Demand_kWh",
                 color=BRAND_NAVY, linewidth=2.4, marker="o", markersize=5,
                 label="Grid demand (kWh)", ax=ax)
    ax.fill_between(data["Start_Hour"], data["Grid_Demand_kWh"],
                    color=BRAND_NAVY, alpha=0.10)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Charging demand (kWh)", color=BRAND_NAVY)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 2))

    twin = ax.twinx()
    twin.grid(False)
    twin.plot(data["Start_Hour"], data["Solar_Generation_kW"],
              color=SOLAR_GOLD, linewidth=2.6, linestyle="--", marker="s",
              markersize=4.5, label="Solar generation (kW)")
    twin.fill_between(data["Start_Hour"], data["Solar_Generation_kW"],
                      color=SOLAR_GOLD, alpha=0.18)
    twin.set_ylabel("Solar generation (kW)", color="#B8860B")
    twin.set_ylim(0, PV_CAPACITY_KWP * 1.15)
    twin.spines["right"].set_visible(True)
    twin.spines["right"].set_color("#B8860B")

    peak_hour = int(data.loc[data["Grid_Demand_kWh"].idxmax(), "Start_Hour"])
    peak_value = float(data["Grid_Demand_kWh"].max())
    ax.annotate(f"Demand peak {peak_value:,.0f} kWh\nat {peak_hour:02d}:00",
                xy=(peak_hour, peak_value),
                xytext=(peak_hour + 1.6, peak_value * 0.98),
                fontsize=8.5, color=BRAND_NAVY, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=BRAND_NAVY, lw=1.1))

    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="upper left")
    if show_title:
        ax.set_title("Panel 1 — Hourly grid demand vs. rooftop solar generation")
    return fig


def plot_cost_by_user(frame: pd.DataFrame, ax: plt.Axes | None = None,
                      show_title: bool = True) -> Figure:
    """Panel 2: distribution of session cost per user type (box + strip)."""
    apply_house_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(7.4, 4.8))
    else:
        fig = ax.get_figure()

    present = [u for u in USER_ORDER if u in set(frame["User_Type"])]
    sns.boxplot(data=frame, x="User_Type", y="Net_Billable_MYR", order=present,
                hue="User_Type", hue_order=present, legend=False,
                palette=USER_PALETTE, width=0.55, linewidth=1.3,
                fliersize=0, ax=ax)
    sns.stripplot(data=frame.sample(min(len(frame), 320), random_state=7),
                  x="User_Type", y="Net_Billable_MYR", order=present,
                  color="#404040", size=2.0, alpha=0.35, jitter=0.22, ax=ax)

    overall_median = float(frame["Net_Billable_MYR"].median())
    ax.axhline(overall_median, color=ACCENT_RED, linestyle=":", linewidth=1.4,
               label=f"Fleet median = {overall_median:,.2f} MYR")
    ax.legend(loc="upper left")

    for index, user in enumerate(present):
        cohort = frame.loc[frame["User_Type"] == user, "Net_Billable_MYR"]
        median = float(cohort.median())
        ax.text(index, median, f"{median:,.2f}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="white",
                bbox=dict(boxstyle="round,pad=0.18", fc=BRAND_GREY, ec="none"))

    ax.set_xlabel("User type")
    ax.set_ylabel("Session cost (MYR)")
    if show_title:
        ax.set_title("Panel 2 — Charging session cost by user type")

    # The fleet has a small number of very high-cost overstay sessions; they
    # would compress the boxes into the bottom of the plot, so the axis is
    # clipped at a readable ceiling and the excluded sessions are annotated.
    ceiling = 40.0
    clipped = int((frame["Net_Billable_MYR"] > ceiling).sum())
    if clipped:
        ax.set_ylim(0, ceiling)
        ax.text(0.99, 0.62,
                f"{clipped} overstay sessions above\n{ceiling:.0f} MYR are outside "
                f"the axis\n(fleet maximum {frame['Net_Billable_MYR'].max():,.2f} MYR)",
                transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
                color="#595959",
                bbox=dict(boxstyle="round,pad=0.3", fc="#F7F7F7", ec="#D9D9D9"))
    return fig


def plot_temp_vs_energy(frame: pd.DataFrame, ax: plt.Axes | None = None,
                        show_title: bool = True) -> Figure:
    """Panel 3: battery temperature against energy delivered with trendlines."""
    apply_house_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(7.6, 4.8))
    else:
        fig = ax.get_figure()

    sns.scatterplot(data=frame, x="Battery_Temp_C", y="Energy_kWh",
                    hue="Charger_Type", hue_order=["AC", "DC"],
                    palette=CHARGER_PALETTE, alpha=0.55, s=18,
                    edgecolor="none", ax=ax)
    sns.regplot(data=frame, x="Battery_Temp_C", y="Energy_kWh", scatter=False,
                color="#404040", line_kws={"linewidth": 2.0, "linestyle": "-"},
                ax=ax, label="Fleet trend")
    for charger, colour in CHARGER_PALETTE.items():
        subset = frame[frame["Charger_Type"] == charger]
        if len(subset) > 5:
            sns.regplot(data=subset, x="Battery_Temp_C", y="Energy_kWh",
                        scatter=False, color=colour,
                        line_kws={"linewidth": 1.4, "linestyle": "--"}, ax=ax)

    slope = np.polyfit(frame["Battery_Temp_C"], frame["Energy_kWh"], 1)[0]
    r_value = frame["Battery_Temp_C"].corr(frame["Energy_kWh"])
    ax.text(0.02, 0.97, f"slope = {slope:+.3f} kWh/°C\nPearson r = {r_value:+.3f}",
            transform=ax.transAxes, va="top", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.35", fc="#FFFFFF", ec="#D9D9D9"))

    ax.axvline(45.0, color=ACCENT_RED, linestyle=":", linewidth=1.3)
    ax.text(45.6, ax.get_ylim()[1] * 0.97, "45 °C thermal alert", rotation=90,
            va="top", fontsize=7.5, color=ACCENT_RED)
    ax.set_xlabel("Battery temperature (°C)")
    ax.set_ylabel("Energy delivered (kWh)")
    if show_title:
        ax.set_title("Panel 3 — Battery temperature vs. energy delivered")
    ax.legend(loc="upper right", title="")
    return fig


def build_publication_panel(frame: pd.DataFrame) -> Figure:
    """Composite A4-landscape figure containing all three required panels."""
    apply_house_style()
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.6),
                             gridspec_kw={"width_ratios": [1.25, 1.0, 1.0]})
    plot_grid_vs_solar(frame, ax=axes[0])
    plot_cost_by_user(frame, ax=axes[1])
    plot_temp_vs_energy(frame, ax=axes[2])
    fig.suptitle("Taylor's Smart Campus — EV Charging Analytics Panel",
                 fontsize=13, fontweight="bold", color=BRAND_NAVY, y=1.03)
    fig.tight_layout()
    return fig


def save(fig: Figure, path: Path) -> Path:
    """Save a figure to ``path`` at 300 dpi and close it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
