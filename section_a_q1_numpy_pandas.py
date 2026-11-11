"""
section_a_q1_numpy_pandas.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section A, Question 1 (5 marks)

Role of NumPy vs Pandas on high-frequency energy-grid telemetry, demonstrated
with executable examples on the Smart Campus EV dataset:

    Demo 1  NumPy 2-D array slicing  : isolate the 12:00-17:59 peak-load block
    Demo 2  NumPy boolean masking    : battery temperatures above 45 degC
    Demo 3  Pandas median imputation : repair missing Duration_Mins / Energy_kWh
    Demo 4  Pandas groupby           : charging revenue per charger type
    Demo 5  Benchmarks               : NumPy vs loop, Pandas groupby vs dict

Run with::

    python section_a_q1_numpy_pandas.py
"""

from __future__ import annotations

import timeit
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
RAW_CSV: Final[Path] = BASE_DIR / "assets" / "ev_campus_dataset.csv"
CLEAN_CSV: Final[Path] = BASE_DIR / "assets" / "cleaned_energy_sales_data.csv"
FIGURE_DIR: Final[Path] = BASE_DIR / "assets" / "figures"

PEAK_WINDOW: Final[tuple[int, int]] = (12, 18)   # 12:00 <= h < 18:00
TEMP_ALERT_C: Final[float] = 45.0


def _banner(title: str) -> None:
    """Print a consistent console section header."""
    print("\n" + "=" * 74)
    print(f" {title}")
    print("=" * 74)


def load_telemetry_matrix(csv_path: Path) -> tuple[np.ndarray, list[str]]:
    """Load the numeric telemetry columns into a dense 2-D NumPy array.

    NumPy wants a single homogeneous ``dtype``, so the five telemetry fields are
    stacked as ``float64``.  One contiguous block of memory means every later
    operation (slice, mask, reduce) is a C loop over a flat buffer with no
    per-cell Python object overhead.

    Returns
    -------
    tuple[numpy.ndarray, list[str]]
        ``(matrix, column_names)`` where ``matrix`` has shape ``(n_sessions, 5)``:
        ``Start_Hour, Duration_Mins, Energy_kWh, Overstay_Mins, Battery_Temp_C``.
    """
    frame = pd.read_csv(csv_path)
    columns = ["Start_Hour", "Duration_Mins", "Energy_kWh",
               "Overstay_Mins", "Battery_Temp_C"]
    # NaN survives the cast, which is exactly what Demo 3 needs to repair.
    matrix = frame[columns].to_numpy(dtype="float64")
    return matrix, columns


# --------------------------------------------------------------------------- #
# Demo 1 - 2-D array slicing for peak-load hours
# --------------------------------------------------------------------------- #
def demo_slicing(matrix: np.ndarray, columns: list[str]) -> None:
    """Slice a contiguous 2-D block for the peak charging window.

    ``np.argsort`` + ``np.searchsorted`` find the row offsets of the window in
    O(n log n); the resulting ``matrix[lo:hi, cols]`` selection is a *view*
    (``.base`` is not ``None``) and therefore copies no telemetry at all.
    """
    _banner("DEMO 1 (NumPy) - 2-D array slicing: 12:00-17:59 peak-load block")

    start_hour = matrix[:, 0]
    order = np.argsort(start_hour, kind="stable")
    sorted_hours = start_hour[order]
    low, high = np.searchsorted(sorted_hours, PEAK_WINDOW, side="left")

    energy_col = columns.index("Energy_kWh")
    temp_col = columns.index("Battery_Temp_C")
    peak_block = matrix[order][low:high][:, [energy_col, temp_col]]   # rows + cols

    print(f"Full matrix shape               : {matrix.shape}")
    print(f"Peak window row offsets         : [{low}:{high}]")
    print(f"Peak block shape (rows, cols)   : {peak_block.shape}")
    print(f"Derived from a view (no copy)   : {peak_block.base is not None}")
    print(f"Blocks before NaN repair        : "
          f"{int(np.isnan(peak_block[:, 0]).sum())} missing energy cell(s)")

    # NumPy propagates NaN by design: mean() of a column with one gap is NaN.
    # The analyst therefore either masks the gaps or uses the NaN-aware ufunc.
    print(f"Plain mean() with gaps present  : {peak_block[:, 0].mean()}")
    print(f"np.nanmean() (gap-aware)        : {np.nanmean(peak_block[:, 0]):,.2f} kWh")
    print(f"np.nansum()  (gap-aware)        : {np.nansum(peak_block[:, 0]):,.2f} kWh")
    print(f"Peak mean battery temperature   : {np.nanmean(peak_block[:, 1]):.2f} degC")

    print("\nPer-column gap-aware mean (axis=0 reduction):")
    for name, value in zip(columns, np.nanmean(matrix, axis=0)):
        print(f"   {name:<16}: {value:>10.2f}")


# --------------------------------------------------------------------------- #
# Demo 2 - boolean masking for overheating batteries
# --------------------------------------------------------------------------- #
def demo_masking(matrix: np.ndarray, columns: list[str]) -> None:
    """Select overheating sessions with a boolean mask (no Python loop)."""
    _banner("DEMO 2 (NumPy) - boolean masking: battery temperature > 45 degC")

    temp_col = columns.index("Battery_Temp_C")
    energy_col = columns.index("Energy_kWh")
    overstay_col = columns.index("Overstay_Mins")
    temperatures = matrix[:, temp_col]

    overheating = temperatures > TEMP_ALERT_C          # element-wise comparison
    hot_energy = matrix[overheating, energy_col]        # fancy-index extraction
    hot_energy = hot_energy[~np.isnan(hot_energy)]      # drop unrepaired gaps

    print(f"Total sessions                  : {temperatures.size:,}")
    print(f"Sessions above {TEMP_ALERT_C:.0f} degC          : "
          f"{int(overheating.sum()):,} ({overheating.mean() * 100:.1f} %)")
    print(f"Max battery temperature         : {temperatures.max():.1f} degC")
    print(f"Mean energy of overheated rows  : {hot_energy.mean():.2f} kWh")
    print(f"Mean energy of all valid rows   : "
          f"{np.nanmean(matrix[:, energy_col]):.2f} kWh")
    print(f"Energy delivered while >45 degC : {hot_energy.sum():,.2f} kWh")

    # Compound mask: overheating AND overstay above 20 minutes, in one pass
    critical = overheating & (matrix[:, overstay_col] > 20)
    print(f"Overheating AND overstay > 20   : {int(critical.sum())} session(s)")
    critical_ids = np.flatnonzero(critical)
    print(f"Row indices of those sessions   : {critical_ids[:10].tolist()}"
          f"{' ...' if critical_ids.size > 10 else ''}")

    # np.where returns the indices instead of a boolean mask (same result,
    # different contract: useful when the row order must be preserved).
    print(f"np.where() index count          : {np.where(critical)[0].size}")


# --------------------------------------------------------------------------- #
# Demo 3 - Pandas median imputation
# --------------------------------------------------------------------------- #
def demo_imputation(csv_path: Path) -> pd.DataFrame:
    """Repair missing telemetry with the median strategy and log the effect.

    Median imputation is preferred over the mean for right-skewed charging data
    (a single 214-minute overstay session would drag a mean far above the
    typical session); the median keeps the imputed value inside the dense body
    of the distribution.
    """
    _banner("DEMO 3 (Pandas) - median imputation of missing power data")

    raw = pd.read_csv(csv_path)
    numeric = raw.select_dtypes(include="number")
    missing = numeric.isna().sum()
    missing = missing[missing > 0]
    print("Columns containing nulls before imputation:")
    print(missing.to_string())

    medians = numeric.median(numeric_only=True)
    repaired = raw.copy()
    for column in missing.index:
        repaired[column] = repaired[column].fillna(medians[column])

    print("\nMedians applied:")
    for column in missing.index:
        print(f"   {column:<16} median = {medians[column]:>8.2f}")
    print(f"\nTotal nulls after imputation    : "
          f"{int(repaired[list(numeric.columns)].isna().sum().sum())}")
    print(f"Rows / columns returned         : {repaired.shape}")
    return repaired


# --------------------------------------------------------------------------- #
# Demo 4 - group-wise revenue with .groupby()
# --------------------------------------------------------------------------- #
def demo_groupby() -> pd.DataFrame:
    """Aggregate charging revenue per charger type and per hour with Pandas.

    One ``.groupby()`` call replaces a Python dictionary of accumulators: the
    split-apply-combine machinery is executed in Cython, the group keys are
    hashed once, and the aggregate columns are built in a single pass.
    """
    _banner("DEMO 4 (Pandas) - group-wise charging revenue with .groupby()")

    frame = pd.read_csv(CLEAN_CSV)
    by_charger = (
        frame.groupby("Charger_Type", as_index=True)
        .agg(Sessions=("Session_ID", "count"),
             Energy_kWh=("Energy_kWh", "sum"),
             Revenue_MYR=("Net_Billable_MYR", "sum"),
             Avg_Cost_MYR=("Net_Billable_MYR", "mean"))
        .round(2)
        .sort_values("Revenue_MYR", ascending=False)
    )
    by_charger["Revenue_Share_%"] = (
        by_charger["Revenue_MYR"] / by_charger["Revenue_MYR"].sum() * 100
    ).round(1)
    print(by_charger.to_string())

    hourly = frame.pivot_table(index="Start_Hour", columns="Charger_Type",
                               values="Net_Billable_MYR", aggfunc="sum",
                               fill_value=0.0).round(2)
    peak_hour = int(hourly.sum(axis=1).idxmax())
    print(f"\nPeak revenue hour (all chargers) : {peak_hour:02d}:00  "
          f"({hourly.sum(axis=1).max():,.2f} MYR)")
    print("\nPivot of net revenue (first 8 hours):")
    print(hourly.head(8).to_string())
    return frame


# --------------------------------------------------------------------------- #
# Demo 5 - vectorisation and groupby benchmarks
# --------------------------------------------------------------------------- #
def demo_benchmark(frame: pd.DataFrame) -> dict[str, float]:
    """Time row-wise DataFrame idioms against vectorised column arithmetic.

    Workload A reproduces the per-session power rate (``kW = kWh / hours``)
    behind the overheating alert, implemented three ways:

    * ``DataFrame.iterrows()`` - the classic row-at-a-time anti-pattern;
    * ``DataFrame.apply(axis=1)`` - still one Python call per row;
    * vectorised columns - one C loop over contiguous ``float64`` buffers.

    Workload B reproduces the segmented revenue report (sum, energy and session
    count per hour x charger x user type) with ``.groupby()`` against a plain
    dictionary accumulator over the real table replicated to 1,200,000 rows.
    """
    _banner("DEMO 5 - vectorisation and groupby benchmarks")

    rng = np.random.default_rng(seed=42)
    n_rows = 200_000
    row_frame = pd.DataFrame({
        "Battery_Temp_C": rng.normal(35.0, 6.0, n_rows),
        "Energy_kWh": rng.normal(15.5, 7.5, n_rows).clip(min=1.0),
        "Duration_Mins": rng.normal(94.0, 43.0, n_rows).clip(min=15.0),
    })
    temps_array = row_frame["Battery_Temp_C"].to_numpy()
    energy_array = row_frame["Energy_kWh"].to_numpy()
    duration_array = row_frame["Duration_Mins"].to_numpy()

    def via_iterrows() -> float:
        total = 0.0
        for _, row in row_frame.iterrows():
            if row["Battery_Temp_C"] > 40.0:
                total += row["Energy_kWh"] / (row["Duration_Mins"] / 60.0)
        return total

    def via_apply() -> float:
        masked = row_frame[row_frame["Battery_Temp_C"] > 40.0]
        return float(masked.apply(
            lambda row: row["Energy_kWh"] / (row["Duration_Mins"] / 60.0), axis=1
        ).sum())

    def via_numpy() -> float:
        mask = temps_array > 40.0
        return float((energy_array[mask] / (duration_array[mask] / 60.0)).sum())

    repeats = 2
    iterrows_seconds = min(timeit.repeat(via_iterrows, number=1, repeat=repeats))
    apply_seconds = min(timeit.repeat(via_apply, number=1, repeat=repeats))
    vector_seconds = min(timeit.repeat(via_numpy, number=1, repeat=repeats))

    # Workload B: Pandas groupby vs a dict-of-tuples accumulator
    big = pd.concat([frame] * 1000, ignore_index=True)
    group_keys = ["Start_Hour", "Charger_Type", "User_Type"]

    def pandas_groupby() -> pd.DataFrame:
        return big.groupby(group_keys).agg(
            revenue=("Net_Billable_MYR", "sum"),
            energy=("Energy_kWh", "sum"),
            sessions=("Session_ID", "count"),
        )

    def dict_accumulator() -> dict[tuple[int, str, str], list[float]]:
        totals: dict[tuple[int, str, str], list[float]] = {}
        for hour, charger, user, revenue, energy in zip(
                big["Start_Hour"].tolist(), big["Charger_Type"].tolist(),
                big["User_Type"].tolist(), big["Net_Billable_MYR"].tolist(),
                big["Energy_kWh"].tolist()):
            key = (hour, charger, user)
            acc = totals.get(key)
            if acc is None:
                totals[key] = [revenue, energy, 1.0]
            else:
                acc[0] += revenue
                acc[1] += energy
                acc[2] += 1.0
        return totals

    groupby_seconds = min(timeit.repeat(pandas_groupby, number=1, repeat=repeats))
    dict_seconds = min(timeit.repeat(dict_accumulator, number=1, repeat=repeats))

    speedup = apply_seconds / vector_seconds
    iterrows_speedup = iterrows_seconds / vector_seconds
    groupby_speedup = dict_seconds / groupby_seconds

    print(f"\nWorkload A - power-rate computation, {n_rows:,} sessions")
    print(f"   df.iterrows() loop           : {iterrows_seconds:8.3f} s  "
          f"({iterrows_speedup:,.0f}x slower)")
    print(f"   df.apply(axis=1)             : {apply_seconds:8.3f} s  "
          f"({speedup:,.0f}x slower)")
    print(f"   NumPy vectorised             : {vector_seconds:8.3f} s  "
          f"(baseline)")
    print(f"   Rows processed per second    : {n_rows / vector_seconds:,.0f}")
    print(f"   Results agree?               : "
          f"{abs(via_apply() - via_numpy()) / via_numpy() < 1e-9}")

    print(f"\nWorkload B - segmented revenue over {len(big):,} rows "
          f"({len(pandas_groupby())} groups)")
    print(f"   Python dict accumulator      : {dict_seconds:8.3f} s")
    print(f"   Pandas .groupby().agg()      : {groupby_seconds:8.3f} s")
    print(f"   Speed-up factor              : {groupby_speedup:8.1f}x")
    dict_totals = dict_accumulator()
    group_totals = pandas_groupby()
    same_length = len(dict_totals) == len(group_totals)
    same_values = same_length and all(
        abs(dict_totals[key][0] - group_totals.loc[key, "revenue"]) < 1e-6
        for key in dict_totals
    )
    print(f"   Aggregates agree?            : {same_values}")

    _plot_benchmark(iterrows_seconds, apply_seconds, vector_seconds,
                    dict_seconds, groupby_seconds)
    return {
        "iterrows_s": iterrows_seconds,
        "apply_s": apply_seconds,
        "vector_s": vector_seconds,
        "vector_speedup": speedup,
        "iterrows_speedup": iterrows_speedup,
        "dict_s": dict_seconds,
        "groupby_s": groupby_seconds,
        "groupby_speedup": groupby_speedup,
    }


def _plot_benchmark(iterrows_seconds: float, apply_seconds: float,
                    vector_seconds: float, dict_seconds: float,
                    groupby_seconds: float) -> None:
    """Render the timing comparison figure used in the report."""
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.7))

    labels = ["df.iterrows()", "df.apply(axis=1)", "NumPy vectorised"]
    values = [iterrows_seconds, apply_seconds, vector_seconds]
    colours = ["#C55A11", "#ED9B5B", "#2E75B6"]
    bars = axes[0].barh(labels, values, color=colours, height=0.5)
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Execution time for 200,000 rows (s, log scale)")
    axes[0].set_title("(a) Row-wise idioms vs. vectorised arithmetic")
    for bar, value in zip(bars, values):
        axes[0].text(value * 1.25, bar.get_y() + bar.get_height() / 2,
                     f"{value:.3f} s", va="center", fontsize=8.5, fontweight="bold")
    axes[0].set_xlim(min(values) * 0.4, max(values) * 6)

    labels_b = ["Dict accumulator", "Pandas .groupby()"]
    values_b = [dict_seconds, groupby_seconds]
    bars_b = axes[1].barh(labels_b, values_b, color=["#C55A11", "#2E75B6"],
                          height=0.45)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Execution time for 1,200,000 rows (s, log scale)")
    axes[1].set_title("(b) Segmented revenue report")
    for bar, value in zip(bars_b, values_b):
        axes[1].text(value * 1.25, bar.get_y() + bar.get_height() / 2,
                     f"{value:.3f} s", va="center", fontsize=8.5, fontweight="bold")
    axes[1].set_xlim(min(values_b) * 0.4, max(values_b) * 6)

    fig.tight_layout()
    path = FIGURE_DIR / "fig_a1_vectorisation_benchmark.png"
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nBenchmark figure written to      : {path.relative_to(BASE_DIR)}")


def main() -> int:
    """Execute every Section A Question 1 demonstration."""
    print("ITS72604 FINAL EXAMINATION - SECTION A, QUESTION 1")
    print("NumPy and Pandas roles in high-frequency energy grid telemetry")

    matrix, columns = load_telemetry_matrix(RAW_CSV)
    demo_slicing(matrix, columns)
    demo_masking(matrix, columns)
    demo_imputation(RAW_CSV)
    frame = demo_groupby()
    demo_benchmark(frame)

    _banner("QUESTION 1 DEMONSTRATIONS COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
