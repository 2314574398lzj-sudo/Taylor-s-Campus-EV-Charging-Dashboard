"""
data_pipeline.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section B, Question 1 (8 marks): production-grade data pipeline.

Purpose
-------
Read the raw EV charging telemetry (``assets/ev_campus_dataset.csv``), cleanse it,
engineer the derived commercial and sustainability metrics, and export the
analysis-ready table to ``assets/cleaned_energy_sales_data.csv``.  A full
data-quality and summary-statistics report is written to the execution console.

Pipeline stages
---------------
1. ``extract()``           - defensive CSV ingestion with encoding fallback.
2. ``cleanse()``           - de-duplication, numeric coercion, median imputation,
                             categorical validation, range checks.
3. ``add_features()``      - Duration_Hours, Power_Rate_kW, Carbon_Savings_kgCO2,
                             Peak/Hub rate card, Net_Billable_MYR, risk flags.
4. ``summarise()``         - console summary statistics for the facility manager.
5. ``load()``              - single entry point used by ``app.py``.

Tariff assumptions (MYR) — documented so that the figures are auditable
-----------------------------------------------------------------------
Base rate          : AC = 6.00 / hour, DC = 15.00 / hour
Peak surcharge     : +25 % of base fee for sessions starting 12:00-17:59
Overstay penalty   : 0.50 / minute beyond a 15-minute grace period
Carbon intensity   : 0.475 kg CO2 avoided per kWh of grid energy displaced
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Module-level configuration (single source of truth for the whole project)
# --------------------------------------------------------------------------- #
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
ASSET_DIR: Final[Path] = BASE_DIR / "assets"

RAW_FILE: Final[Path] = ASSET_DIR / "ev_campus_dataset.csv"
CLEAN_FILE: Final[Path] = ASSET_DIR / "cleaned_energy_sales_data.csv"
SALES_FILE: Final[Path] = ASSET_DIR / "sales_data.csv"

REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "Session_ID",
    "Charger_Type",
    "User_Type",
    "Start_Hour",
    "Duration_Mins",
    "Energy_kWh",
    "Overstay_Mins",
    "Battery_Temp_C",
    "Grid_Status_Label",
)

NUMERIC_COLUMNS: Final[tuple[str, ...]] = (
    "Start_Hour",
    "Duration_Mins",
    "Energy_kWh",
    "Overstay_Mins",
    "Battery_Temp_C",
)

CATEGORY_DOMAIN: Final[dict[str, set[str]]] = {
    "Charger_Type": {"AC", "DC"},
    "User_Type": {"Student", "Staff", "Visitor"},
    "Grid_Status_Label": {"Normal", "Grid_Surge", "Overheated"},
}

# Tariff / assumption constants
BASE_RATE_MYR: Final[dict[str, float]] = {"AC": 6.00, "DC": 15.00}
PEAK_HOURS: Final[range] = range(12, 18)          # 12:00 - 17:59
PEAK_SURCHARGE_RATE: Final[float] = 0.25
OVERSTAY_GRACE_MIN: Final[int] = 15
OVERSTAY_RATE_MYR_PER_MIN: Final[float] = 0.50
CARBON_FACTOR_KG_PER_KWH: Final[float] = 0.475
ALERT_OVERSTAY_MIN: Final[int] = 20               # Section A threshold
ALERT_TEMP_C: Final[float] = 40.0                 # Section A threshold

# Reporting calendar: the anonymised extract carries no timestamps, therefore
# the 1,200 sessions are mapped onto a deterministic 30-day operating window
# (40 sessions per day) so that date filtering is meaningful in the dashboard.
REPORT_START_DATE: Final[pd.Timestamp] = pd.Timestamp("2026-04-01")
SESSIONS_PER_DAY: Final[int] = 40

LOGGER: Final[logging.Logger] = logging.getLogger("ev_pipeline")


# --------------------------------------------------------------------------- #
# 1. Extraction
# --------------------------------------------------------------------------- #
def extract(csv_path: Path = RAW_FILE) -> pd.DataFrame:
    """Read the raw telemetry CSV into a DataFrame.

    Parameters
    ----------
    csv_path:
        Path to the raw session export.

    Returns
    -------
    pandas.DataFrame
        Raw, un-validated session table.

    Raises
    ------
    FileNotFoundError
        If the export file is missing; the caller decides whether to abort.
    pd.errors.EmptyDataError
        If the file exists but contains no parsable rows.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw dataset not found: {csv_path}")

    try:
        frame = pd.read_csv(csv_path)
        LOGGER.info("Extracted %s rows x %s columns from %s",
                    f"{len(frame):,}", frame.shape[1], csv_path.name)
    except UnicodeDecodeError:                     # pragma: no cover - defensive
        LOGGER.warning("UTF-8 decode failed; retrying with latin-1.")
        frame = pd.read_csv(csv_path, encoding="latin-1")
    except pd.errors.EmptyDataError as exc:
        raise pd.errors.EmptyDataError(f"{csv_path} contains no data.") from exc

    return frame


# --------------------------------------------------------------------------- #
# 2. Cleansing
# --------------------------------------------------------------------------- #
def _coerce_numeric(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Coerce telemetry columns to numeric and report how many cells were damaged."""
    coerced: dict[str, int] = {}
    for column in NUMERIC_COLUMNS:
        if column not in frame.columns:
            continue
        original = pd.to_numeric(frame[column], errors="coerce")
        # cells that existed but could not be parsed (e.g. "N/A", "  ", "-")
        damaged = int(frame[column].notna().sum() - original.notna().sum())
        coerced[column] = damaged
        frame[column] = original
    return frame, coerced


def _median_impute(frame: pd.DataFrame) -> dict[str, float]:
    """Impute missing numeric cells with the column median.

    The median is chosen over the mean because charging duration and energy
    delivered are right-skewed; the median is robust to the long tail of
    overstay sessions and therefore does not inflate the reconstructed load.

    Returns
    -------
    dict[str, float]
        Mapping of ``column -> median`` actually used, for the audit log.
    """
    medians: dict[str, float] = {}
    for column in NUMERIC_COLUMNS:
        if column not in frame.columns:
            continue
        missing = int(frame[column].isna().sum())
        if missing:
            median = float(frame[column].median())
            frame[column] = frame[column].fillna(median)
            medians[column] = median
            LOGGER.info("Imputed %s missing value(s) in %-16s with median %.2f",
                        missing, column, median)
    return medians


def _validate_categories(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Normalise and validate the categorical columns against their domain.

    Steps: strip surrounding whitespace, apply a title/upper normalisation,
    replace the common synonyms, and map anything outside the domain to the
    explicit ``"Unclassified"`` sentinel so that no silent category is created.

    Returns
    -------
    dict[str, list[str]]
        ``column -> sorted list of invalid values`` found (already replaced).
    """
    synonyms = {
        "Charger_Type": {"ac": "AC", "ac fast": "AC", "ac_fast": "AC",
                         "dc": "DC", "dc fast": "DC", "dc_ultra": "DC"},
        "User_Type": {"student": "Student", "staff": "Staff",
                      "visitor": "Visitor", "public": "Visitor"},
        "Grid_Status_Label": {"normal": "Normal", "grid surge": "Grid_Surge",
                              "grid_surge": "Grid_Surge",
                              "overheated": "Overheated"},
    }
    issues: dict[str, list[str]] = {}

    for column, domain in CATEGORY_DOMAIN.items():
        if column not in frame.columns:
            continue
        cleaned = frame[column].astype("string").str.strip()
        lookup = synonyms[column]
        cleaned = cleaned.map(
            lambda value, lk=lookup: lk.get(str(value).lower(), value)
        )
        invalid = ~cleaned.isin(domain) & cleaned.notna()
        if invalid.any():
            issues[column] = sorted(cleaned[invalid].astype(str).unique().tolist())
            LOGGER.warning("Column %s: %s invalid categor(y/ies) -> 'Unclassified': %s",
                           column, int(invalid.sum()), issues[column])
            cleaned = cleaned.where(~invalid, "Unclassified")
        frame[column] = cleaned.fillna("Unclassified")
    return issues


def _range_guard(frame: pd.DataFrame) -> pd.DataFrame:
    """Clamp physically impossible values to NaN and re-impute afterwards."""
    bounds = {
        "Start_Hour": (0, 23),
        "Duration_Mins": (1, 24 * 60),
        "Energy_kWh": (0.1, 120.0),
        "Overstay_Mins": (0, 24 * 60),
        "Battery_Temp_C": (5.0, 80.0),
    }
    for column, (low, high) in bounds.items():
        if column not in frame.columns:
            continue
        out_of_range = frame[column].notna() & ~frame[column].between(low, high)
        if out_of_range.any():
            LOGGER.warning("Column %s: %s out-of-range value(s) nulled.",
                           column, int(out_of_range.sum()))
            frame.loc[out_of_range, column] = np.nan
    return frame


def cleanse(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the full cleansing stage and return the cleaned frame plus an audit dict."""
    report: dict[str, object] = {}

    missing_required = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing_required:
        raise KeyError(f"Dataset is missing required column(s): {missing_required}")

    report["rows_in"] = int(len(frame))
    before = frame.duplicated(subset="Session_ID").sum()
    frame = frame.drop_duplicates(subset="Session_ID", keep="first").copy()
    report["duplicates_removed"] = int(before)

    frame, coerced = _coerce_numeric(frame)
    report["non_numeric_cells"] = {k: v for k, v in coerced.items() if v}

    frame = _range_guard(frame)
    null_counts = frame[list(NUMERIC_COLUMNS)].isna().sum()
    report["null_before_impute"] = {
        column: int(count) for column, count in null_counts.items() if count
    }
    report["medians_used"] = _median_impute(frame)
    report["invalid_categories"] = _validate_categories(frame)

    frame["Start_Hour"] = frame["Start_Hour"].round().astype("int64")
    frame["Overstay_Mins"] = frame["Overstay_Mins"].round().astype("int64")
    report["rows_out"] = int(len(frame))
    return frame, report


# --------------------------------------------------------------------------- #
# 3. Feature engineering
# --------------------------------------------------------------------------- #
def _ambient_temperature(start_hour: pd.Series) -> pd.Series:
    """Reconstruct ambient bay temperature from the diurnal irradiance profile.

    The telemetry extract only carries pack temperature.  For the correlation
    study we therefore rebuild an ambient series for the Subang Jaya campus
    (night floor 25.0 degC, afternoon peak 31.0 degC) from the session start
    hour.  This is an explicit modelling assumption, not a measurement.
    """
    hour = start_hour.to_numpy(dtype="float64")
    daytime = (hour >= 7) & (hour <= 19)
    solar_shape = np.sin(np.pi * (hour - 7) / 12.0)
    ambient = np.where(daytime, 25.0 + 6.0 * np.clip(solar_shape, 0.0, 1.0), 25.0)
    return pd.Series(np.round(ambient, 2), index=start_hour.index,
                     name="Ambient_Temp_C")


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Create the derived commercial, sustainability and risk features."""
    out = frame.copy()

    # --- time base and operating calendar ---------------------------------- #
    out["Duration_Hours"] = (out["Duration_Mins"] / 60.0).round(4)
    out["Session_Date"] = (
        REPORT_START_DATE
        + pd.to_timedelta(np.arange(len(out)) // SESSIONS_PER_DAY, unit="D")
    )
    out["Day_of_Week"] = out["Session_Date"].dt.day_name()

    # --- physics: power rate must never divide by zero --------------------- #
    out["Power_Rate_kW"] = np.where(
        out["Duration_Hours"] > 0,
        out["Energy_kWh"] / out["Duration_Hours"],
        np.nan,
    ).round(4)

    # --- sustainability ---------------------------------------------------- #
    out["Carbon_Savings_kgCO2"] = (
        out["Energy_kWh"] * CARBON_FACTOR_KG_PER_KWH
    ).round(4)

    # --- tariff: base fee, peak surcharge, overstay penalty ---------------- #
    out["Base_Rate_MYR"] = out["Charger_Type"].map(BASE_RATE_MYR).astype("float64")
    out["Base_Fee_MYR"] = (out["Base_Rate_MYR"] * out["Duration_Hours"]).round(4)
    out["Peak_Hour_Flag"] = out["Start_Hour"].isin(PEAK_HOURS).astype("int8")
    out["Peak_Surge_MYR"] = (out["Base_Fee_MYR"] * PEAK_SURCHARGE_RATE
                             * out["Peak_Hour_Flag"]).round(4)
    billable_overstay = (out["Overstay_Mins"] - OVERSTAY_GRACE_MIN).clip(lower=0)
    out["Overstay_Fee_MYR"] = (billable_overstay * OVERSTAY_RATE_MYR_PER_MIN).round(4)
    out["Net_Billable_MYR"] = (
        out["Base_Fee_MYR"] + out["Peak_Surge_MYR"] + out["Overstay_Fee_MYR"]
    ).round(4)

    # --- thermal and risk analytics --------------------------------------- #
    out["Ambient_Temp_C"] = _ambient_temperature(out["Start_Hour"])
    out["Temp_Delta_C"] = (out["Battery_Temp_C"] - out["Ambient_Temp_C"]).round(2)
    out["Risk_Alert"] = (
        (out["Overstay_Mins"] > ALERT_OVERSTAY_MIN)
        & (out["Battery_Temp_C"] > ALERT_TEMP_C)
    ).astype("int8")

    ordered = [
        "Session_ID", "Session_Date", "Day_of_Week", "Start_Hour",
        "Charger_Type", "User_Type", "Duration_Mins", "Duration_Hours",
        "Energy_kWh", "Power_Rate_kW", "Overstay_Mins", "Battery_Temp_C",
        "Ambient_Temp_C", "Temp_Delta_C", "Grid_Status_Label",
        "Carbon_Savings_kgCO2", "Base_Rate_MYR", "Base_Fee_MYR",
        "Peak_Hour_Flag", "Peak_Surge_MYR", "Overstay_Fee_MYR",
        "Net_Billable_MYR", "Risk_Alert",
    ]
    return out[ordered]


# --------------------------------------------------------------------------- #
# 4. Reporting
# --------------------------------------------------------------------------- #
def _format_console_report(frame: pd.DataFrame, report: dict[str, object]) -> str:
    """Build the console summary printed after a successful pipeline run."""
    pd.set_option("display.width", 110)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.float_format", lambda value: f"{value:,.2f}")

    total_energy = frame["Energy_kWh"].sum()
    total_carbon = frame["Carbon_Savings_kgCO2"].sum()
    total_revenue = frame["Net_Billable_MYR"].sum()
    alerts = int(frame["Risk_Alert"].sum())

    charger = (
        frame.groupby("Charger_Type")
        .agg(Sessions=("Session_ID", "count"),
             Energy_kWh=("Energy_kWh", "sum"),
             Avg_Power_kW=("Power_Rate_kW", "mean"),
             Revenue_MYR=("Net_Billable_MYR", "sum"))
        .round(2)
    )
    users = (
        frame.groupby("User_Type")
        .agg(Sessions=("Session_ID", "count"),
             Energy_kWh=("Energy_kWh", "sum"),
             Avg_Cost_MYR=("Net_Billable_MYR", "mean"),
             Avg_Overstay_min=("Overstay_Mins", "mean"))
        .round(2)
    )
    describe_cols = ["Duration_Mins", "Energy_kWh", "Power_Rate_kW",
                     "Carbon_Savings_kgCO2", "Net_Billable_MYR"]
    stats = frame[describe_cols].describe().T[["count", "mean", "std",
                                               "min", "50%", "max"]].round(2)

    lines = [
        "=" * 78,
        " SMART CAMPUS ENERGY & EV FLEET  -  DATA PIPELINE EXECUTION REPORT",
        "=" * 78,
        f" Source file          : {RAW_FILE.name}",
        f" Output file          : {CLEAN_FILE.name}",
        f" Rows in / out        : {report['rows_in']:,} / {report['rows_out']:,}",
        f" Duplicates removed   : {report['duplicates_removed']}",
        f" Non-numeric cells    : {report['non_numeric_cells'] or 'none'}",
        f" Nulls before impute  : {report['null_before_impute']}",
        f" Medians used         : "
        + ", ".join(f"{k}={v:,.2f}" for k, v in report["medians_used"].items()),
        f" Invalid categories   : {report['invalid_categories'] or 'none'}",
        "",
        "------------------------------------------------------------------",
        " EXECUTIVE TOTALS",
        "------------------------------------------------------------------",
        f" Total energy delivered : {total_energy:>12,.2f} kWh",
        f" Carbon offset          : {total_carbon:>12,.2f} kg CO2",
        f" Net billable revenue   : {total_revenue:>12,.2f} MYR",
        f" High-risk alert rows   : {alerts:>12,}",
        "",
        "------------------------------------------------------------------",
        " SUMMARY: CHARGER TYPE",
        "------------------------------------------------------------------",
        charger.to_string(),
        "",
        "------------------------------------------------------------------",
        " SUMMARY: USER TYPE",
        "------------------------------------------------------------------",
        users.to_string(),
        "",
        "------------------------------------------------------------------",
        " SUMMARY STATISTICS: KEY NUMERIC FEATURES",
        "------------------------------------------------------------------",
        stats.to_string(),
        "",
        "------------------------------------------------------------------",
        " HEAD OF CLEANED DATASET (first 5 rows, 10 columns)",
        "------------------------------------------------------------------",
        frame.iloc[:5, :10].to_string(index=False),
        "=" * 78,
        f" [OK] Cleaned dataset exported -> {CLEAN_FILE}",
        "=" * 78,
    ]
    return "\n".join(lines)


def summarise(frame: pd.DataFrame, report: dict[str, object]) -> str:
    """Print (and return) the console summary statistics block."""
    text = _format_console_report(frame, report)
    print(text)
    return text


# --------------------------------------------------------------------------- #
# 5. Public API
# --------------------------------------------------------------------------- #
def run_pipeline(raw_path: Path = RAW_FILE,
                 output_path: Path = CLEAN_FILE,
                 verbose: bool = True) -> pd.DataFrame:
    """Execute extract -> cleanse -> feature engineering -> export.

    Parameters
    ----------
    raw_path:
        Source CSV.
    output_path:
        Destination CSV for the analytics-ready table.
    verbose:
        When ``True`` the summary report is printed to ``stdout``.

    Returns
    -------
    pandas.DataFrame
        The cleaned, feature-enriched session table.

    Raises
    ------
    FileNotFoundError
        Propagated when the raw export is unavailable.
    """
    raw = extract(raw_path)
    cleaned, report = cleanse(raw)
    enriched = add_features(cleaned)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(output_path, index=False)
    LOGGER.info("Wrote %s rows x %s columns to %s",
                f"{len(enriched):,}", enriched.shape[1], output_path.name)

    if verbose:
        summarise(enriched, report)
    return enriched


def load(raw_path: Path = RAW_FILE) -> pd.DataFrame:
    """Return the cleaned table, rebuilding it if the cached export is stale."""
    if CLEAN_FILE.exists() and CLEAN_FILE.stat().st_mtime >= raw_path.stat().st_mtime:
        return pd.read_csv(CLEAN_FILE, parse_dates=["Session_Date"])
    return run_pipeline(raw_path, CLEAN_FILE, verbose=False)


def main() -> int:
    """CLI entry point; returns a POSIX exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)-7s] %(message)s",
        stream=sys.stdout,
    )
    try:
        run_pipeline()
    except FileNotFoundError as exc:
        LOGGER.error("%s", exc)
        return 2
    except (KeyError, pd.errors.EmptyDataError) as exc:
        LOGGER.error("Schema error: %s", exc)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
