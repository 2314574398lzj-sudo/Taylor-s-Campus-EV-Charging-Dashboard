"""
app.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section B, Question 3 (8 marks): multi-page interactive Streamlit dashboard.

Taylor's Campus EV Charging Dashboard
-------------------------------------
Taylor's University branding (logo + university name) is rendered in the
sidebar and above every page, and is also used as the browser-tab favicon.

Pages
-----
1. Executive Overview   : four KPI cards with delta indicators + demand charts
2. Grid & Fleet Analytics: revenue, cost and thermal analytics panels
3. Overstay & Alert Centre: live temperature / overstay thresholds and banners
4. Data Explorer        : filtered table and CSV download

Global sidebar filters (date range, minimum energy, charger type, user type)
are applied to every page and every figure in real time.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Final

import pandas as pd
import streamlit as st
from PIL import Image

import data_pipeline
import visualisations as viz

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
CLEAN_CSV: Final[Path] = BASE_DIR / "assets" / "cleaned_energy_sales_data.csv"
RAW_CSV: Final[Path] = BASE_DIR / "assets" / "ev_campus_dataset.csv"
LOGO_PATH: Final[Path] = BASE_DIR / "assets" / "taylor_logo.png"

APP_NAME: Final[str] = "Taylor's Campus EV Charging Dashboard"
UNIVERSITY: Final[str] = "TAYLOR'S UNIVERSITY"
MODULE: Final[str] = "ITS72604 Principles of Programming"

PAGES: Final[dict[str, str]] = {
    "overview": "1 · Executive Overview",
    "analytics": "2 · Grid & Fleet Analytics",
    "alerts": "3 · Overstay & Alert Centre",
    "explorer": "4 · Data Explorer & Export",
}

st.set_page_config(
    page_title=APP_NAME,
    page_icon=Image.open(LOGO_PATH) if LOGO_PATH.exists() else "⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def brand_header() -> None:
    """Taylor's University branding shown above every dashboard page.

    The logo and the university name are drawn on each page so that a printed
    screen or a screen-share always identifies the owner of the dashboard.
    """
    logo_column, text_column = st.columns([1, 7], gap="small")
    with logo_column:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=150)
    with text_column:
        st.markdown(
            f"<div style='line-height:1.25;padding-top:6px'>"
            f"<span style='font-family:Times New Roman,serif;font-size:20px;font-weight:700;"
            f"letter-spacing:0.5px;color:#1F3864'>{UNIVERSITY}</span><br>"
            f"<span style='font-size:12px;color:#595959'>{MODULE} &middot; "
            f"Smart Campus Energy &amp; EV Fleet Division</span></div>",
            unsafe_allow_html=True,
        )
    st.divider()


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading charging telemetry ...")
def load_data() -> pd.DataFrame:
    """Load (and cache) the cleaned session table, rebuilding it if needed.

    Returns
    -------
    pandas.DataFrame
        Cleaned table with every engineered feature used by the dashboard.

    Raises
    ------
    FileNotFoundError
        If neither the cleaned export nor the raw telemetry file is present.
    """
    if CLEAN_CSV.exists():
        frame = pd.read_csv(CLEAN_CSV, parse_dates=["Session_Date"])
    elif RAW_CSV.exists():
        frame = data_pipeline.run_pipeline(RAW_CSV, CLEAN_CSV, verbose=False)
        frame["Session_Date"] = pd.to_datetime(frame["Session_Date"])
    else:
        raise FileNotFoundError(
            "Place ev_campus_dataset.csv inside the assets/ folder."
        )
    return frame


def format_currency(value: float) -> str:
    """Format a MYR amount with thousands separators and no decimals."""
    return f"MYR {value:,.0f}"


# --------------------------------------------------------------------------- #
# Sidebar - global filters applied to every page
# --------------------------------------------------------------------------- #
def render_sidebar(frame: pd.DataFrame) -> dict[str, object]:
    """Draw the global filter widgets and return the active selection.

    Every widget wrote into ``st.session_state`` through its ``key`` so the
    selection survives page switches and can be reused by all four pages.

    Returns
    -------
    dict[str, object]
        ``{"start", "end", "min_energy", "chargers", "users"}`` describing the
        selection that the caller applies to the data.
    """
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), width=190)
    st.sidebar.markdown(
        f"<div style='font-family:Times New Roman,serif;font-size:17px;font-weight:700;"
        f"color:#1F3864;line-height:1.2'>{UNIVERSITY}</div>"
        f"<div style='font-size:11px;color:#595959;margin-bottom:6px'>{MODULE}</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption(f"{APP_NAME}")
    st.sidebar.caption("ShopEasy Logistics × Taylor's Smart Campus Division")

    st.sidebar.subheader("Filters")
    min_date = frame["Session_Date"].min().date()
    max_date = frame["Session_Date"].max().date()
    start_date, end_date = st.sidebar.date_input(
        "Reporting window",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="date_range",
        help="Session dates are mapped onto a 30-day operating window.",
    )

    min_energy = st.sidebar.slider(
        "Minimum energy delivered (kWh)",
        min_value=float(frame["Energy_kWh"].min()),
        max_value=float(frame["Energy_kWh"].max()),
        value=float(frame["Energy_kWh"].min()),
        step=1.0,
        key="min_energy",
    )

    chargers = st.sidebar.multiselect(
        "Charger type",
        options=sorted(frame["Charger_Type"].unique()),
        default=sorted(frame["Charger_Type"].unique()),
        key="charger_filter",
    )

    users = st.sidebar.multiselect(
        "User type",
        options=["Student", "Staff", "Visitor"],
        default=["Student", "Staff", "Visitor"],
        key="user_filter",
    )

    st.sidebar.divider()
    st.sidebar.caption(
        f"Dataset: **{len(frame):,}** sessions · "
        f"{min_date:%d %b %Y} to {max_date:%d %b %Y}"
    )
    st.sidebar.caption(
        "Tariff: AC MYR 6.00/h · DC MYR 15.00/h · peak +25 % (12:00–17:59) · "
        "overstay MYR 0.50/min beyond 15 min."
    )

    return {
        "start": pd.Timestamp(start_date),
        "end": pd.Timestamp(end_date),
        "min_energy": min_energy,
        "chargers": chargers,
        "users": users,
    }


def apply_filters(frame: pd.DataFrame, selection: dict[str, object]) -> pd.DataFrame:
    """Return the rows that satisfy the current sidebar selection."""
    mask = (
        frame["Session_Date"].between(selection["start"], selection["end"])
        & (frame["Energy_kWh"] >= selection["min_energy"])
        & frame["Charger_Type"].isin(selection["chargers"] or [])
        & frame["User_Type"].isin(selection["users"] or [])
    )
    return frame.loc[mask].copy()


# --------------------------------------------------------------------------- #
# KPI header
# --------------------------------------------------------------------------- #
def kpi_header(filtered: pd.DataFrame) -> None:
    """Render the four executive KPI cards with week-over-week deltas."""
    if filtered.empty:
        st.warning("No sessions match the current filters — widen the selection.")
        return

    end = filtered["Session_Date"].max()
    current = filtered[filtered["Session_Date"] > end - pd.Timedelta(days=7)]
    previous = filtered[
        (filtered["Session_Date"] > end - pd.Timedelta(days=14))
        & (filtered["Session_Date"] <= end - pd.Timedelta(days=7))
    ]

    def delta(column: str, mask_column: str | None = None) -> float | None:
        """Week-over-week change in percent, or ``None`` for a missing window."""
        if mask_column:
            now = current.loc[current[mask_column] == 1, column].count()
            before = previous.loc[previous[mask_column] == 1, column].count()
        else:
            now, before = current[column].sum(), previous[column].sum()
        if not before:
            return None
        return (now - before) / before * 100.0

    columns = st.columns(4, gap="medium")
    energy_delta = delta("Energy_kWh")
    carbon_delta = delta("Carbon_Savings_kgCO2")
    revenue_delta = delta("Net_Billable_MYR")
    alert_delta = delta("Session_ID", mask_column="Risk_Alert")
    alerts_now = int(filtered["Risk_Alert"].sum())

    with columns[0]:
        st.metric("Total energy delivered",
                  f"{filtered['Energy_kWh'].sum():,.0f} kWh",
                  None if energy_delta is None else f"{energy_delta:+.1f} % WoW",
                  border=True)
    with columns[1]:
        st.metric("Carbon offset",
                  f"{filtered['Carbon_Savings_kgCO2'].sum():,.0f} kg CO₂",
                  None if carbon_delta is None else f"{carbon_delta:+.1f} % WoW",
                  border=True)
    with columns[2]:
        st.metric("Net revenue",
                  format_currency(filtered["Net_Billable_MYR"].sum()),
                  None if revenue_delta is None else f"{revenue_delta:+.1f} % WoW",
                  border=True)
    with columns[3]:
        st.metric("Active alerts",
                  f"{alerts_now:,}",
                  None if alert_delta is None else f"{alert_delta:+.1f} % WoW",
                  delta_color="inverse",
                  border=True)
        if alerts_now:
            st.caption(f"{alerts_now} session(s) breach overstay > 20 min and "
                       f"battery > 40 °C")


# --------------------------------------------------------------------------- #
# Page 1 - Executive overview
# --------------------------------------------------------------------------- #
def page_overview(filtered: pd.DataFrame) -> None:
    """Executive landing page: KPI header, demand curve and revenue mix."""
    st.title(APP_NAME)
    st.caption(
        "Live operational view for campus facility directors · "
        f"{len(filtered):,} charging sessions in scope"
    )
    kpi_header(filtered)
    if filtered.empty:
        return

    st.divider()
    left, right = st.columns([1.45, 1.0], gap="large")
    with left:
        st.subheader("Grid demand vs. rooftop solar generation")
        st.pyplot(viz.plot_grid_vs_solar(filtered, show_title=False),
                  use_container_width=True)
        st.caption(
            "Demand is the energy drawn by all sessions starting in each hour; "
            "solar follows the measured irradiance profile of the 1,200 kWp array."
        )
    with right:
        st.subheader("Revenue mix by charger type")
        st.pyplot(viz.plot_hourly_revenue_by_charger(filtered, engine="seaborn",
                                                     show_title=False),
                  use_container_width=True)
        st.caption("AC bays carry 65 % of billable revenue despite lower power.")

    st.subheader("Operational snapshot")
    snapshot = (
        filtered.groupby("Charger_Type")
        .agg(Sessions=("Session_ID", "count"),
             Energy_kWh=("Energy_kWh", "sum"),
             Avg_Power_kW=("Power_Rate_kW", "mean"),
             Revenue_MYR=("Net_Billable_MYR", "sum"))
        .round(2)
    )
    st.dataframe(snapshot, use_container_width=True)


# --------------------------------------------------------------------------- #
# Page 2 - Grid & fleet analytics
# --------------------------------------------------------------------------- #
def page_analytics(filtered: pd.DataFrame) -> None:
    """Three analytical panels: demand, cost distribution and thermal risk."""
    st.title("Grid & Fleet Analytics")
    st.caption("Publication-quality panels rendered from the filtered session set.")
    if filtered.empty:
        st.warning("No sessions match the current filters.")
        return

    st.subheader("Panel 1 — Hourly grid demand vs. solar generation")
    st.pyplot(viz.plot_grid_vs_solar(filtered, show_title=False),
              use_container_width=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Panel 2 — Session cost by user type")
        st.pyplot(viz.plot_cost_by_user(filtered, show_title=False),
                  use_container_width=True)
    with right:
        st.subheader("Panel 3 — Battery temperature vs. energy delivered")
        st.pyplot(viz.plot_temp_vs_energy(filtered, show_title=False),
                  use_container_width=True)

    st.subheader("Thermal and load correlation")
    st.pyplot(viz.plot_correlation_heatmap(filtered, show_title=False),
              use_container_width=True)
    st.caption(
        "Pack temperature tracks charging power (r ≈ 0.67) rather than ambient "
        "weather; duration correlates negatively because slow AC bays run longest."
    )


# --------------------------------------------------------------------------- #
# Page 3 - Overstay and alert centre
# --------------------------------------------------------------------------- #
def page_alerts(filtered: pd.DataFrame) -> None:
    """Threshold-driven alert centre with dynamic Streamlit banners."""
    st.title("High-Risk Overstay & Alert Centre")
    st.caption("Thresholds are set by the facility manager and re-score every session.")

    if filtered.empty:
        st.warning("No sessions match the current filters.")
        return

    left, right = st.columns([1.0, 2.2], gap="large")
    with left:
        temp_threshold = st.slider(
            "Battery temperature threshold (°C)",
            min_value=30.0, max_value=55.0, value=40.0, step=0.5,
            key="temp_threshold",
        )
        overstay_threshold = st.slider(
            "Overstay threshold (minutes)",
            min_value=5, max_value=60, value=20, step=5,
            key="overstay_threshold",
        )
        critical_margin = st.slider(
            "Critical margin above temperature threshold (°C)",
            min_value=1.0, max_value=10.0, value=8.0, step=0.5,
            key="critical_margin",
        )

    risk = filtered[
        (filtered["Overstay_Mins"] > overstay_threshold)
        & (filtered["Battery_Temp_C"] > temp_threshold)
    ]
    critical = risk[risk["Battery_Temp_C"] > temp_threshold + critical_margin]
    warning = risk[~risk.index.isin(critical.index)]

    with left:
        st.metric("Sessions in alert", f"{len(risk):,}")
        st.metric("Critical sessions", f"{len(critical):,}",
                  delta=f"{len(critical)} require action", delta_color="inverse")
        st.caption(f"Overstay > {overstay_threshold} min and battery > "
                   f"{temp_threshold:.1f} °C")

    with right:
        if len(critical):
            st.error(
                f"🚨 **CRITICAL — {len(critical)} session(s) above "
                f"{temp_threshold + critical_margin:.1f} °C with overstay beyond "
                f"{overstay_threshold} min.** Dispatch a bay marshal and request "
                "the session be terminated; battery degradation risk is high."
            )
        if len(warning):
            st.warning(
                f"⚠️ **WARNING — {len(warning)} session(s) between "
                f"{temp_threshold:.1f} °C and "
                f"{temp_threshold + critical_margin:.1f} °C.** Monitor the bay and "
                "send an overstay reminder to the driver."
            )
        if not len(risk):
            st.success(
                "✅ **All clear.** No session in the current filter breaches the "
                "overstay and temperature thresholds."
            )

        if len(risk):
            display = risk[[
                "Session_ID", "Session_Date", "Charger_Type", "User_Type",
                "Overstay_Mins", "Battery_Temp_C", "Energy_kWh",
            ]].copy()
            display["Session_Date"] = display["Session_Date"].dt.strftime("%d %b %Y")
            display = display.sort_values(
                ["Battery_Temp_C", "Overstay_Mins"], ascending=False
            ).reset_index(drop=True)
            st.dataframe(display, use_container_width=True, height=280)
            st.download_button(
                "⬇️ Download alert list (CSV)",
                data=display.to_csv(index=False).encode("utf-8"),
                file_name="overstay_alerts.csv",
                mime="text/csv",
            )


# --------------------------------------------------------------------------- #
# Page 4 - Data explorer and export
# --------------------------------------------------------------------------- #
def page_explorer(filtered: pd.DataFrame) -> None:
    """Filtered data viewer plus the downloadable CSV export."""
    st.title("Filtered Data Explorer & Export")
    if filtered.empty:
        st.warning("No sessions match the current filters.")
        return

    st.caption(f"{len(filtered):,} of the filtered sessions are shown below; "
               "columns can be sorted and searched directly in the grid.")

    columns = st.multiselect(
        "Columns to display",
        options=list(filtered.columns),
        default=["Session_ID", "Session_Date", "Start_Hour", "Charger_Type",
                 "User_Type", "Energy_kWh", "Power_Rate_kW", "Battery_Temp_C",
                 "Net_Billable_MYR", "Risk_Alert"],
        key="column_filter",
    )
    table = filtered[columns].copy()
    if "Session_Date" in table.columns:
        table["Session_Date"] = table["Session_Date"].dt.strftime("%d %b %Y")
    st.dataframe(table.sort_values(columns[0]).head(500).reset_index(drop=True),
                 use_container_width=True, height=340)
    st.caption(f"Showing the first 500 rows of {len(table):,} filtered sessions.")

    buffer = io.StringIO()
    filtered.to_csv(buffer, index=False)
    st.download_button(
        "⬇️ Download filtered dataset (CSV)",
        data=buffer.getvalue().encode("utf-8"),
        file_name="filtered_energy_sales.csv",
        mime="text/csv",
        help="Exports exactly the rows that satisfy the sidebar filters.",
    )

    st.subheader("Descriptive statistics of the filtered selection")
    st.dataframe(
        filtered[["Energy_kWh", "Power_Rate_kW", "Battery_Temp_C",
                  "Carbon_Savings_kgCO2", "Net_Billable_MYR"]]
        .describe().T.round(2),
        use_container_width=True,
    )


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
def main() -> None:
    """Compose the sidebar, apply filters and route to the selected page."""
    try:
        frame = load_data()
    except FileNotFoundError as exc:
        st.error(f"**Dataset missing.** {exc}")
        st.stop()
        return

    selection = render_sidebar(frame)
    filtered = apply_filters(frame, selection)

    query_page = st.query_params.get("page", "overview")
    if query_page not in PAGES:
        query_page = "overview"
    if "page_selector" not in st.session_state:
        st.session_state["page_selector"] = query_page
    chosen = st.sidebar.radio(
        "Dashboard page",
        options=list(PAGES),
        format_func=lambda key: PAGES[key],
        key="page_selector",
    )
    if st.query_params.get("page") != chosen:
        st.query_params["page"] = chosen

    st.sidebar.divider()
    if filtered.empty:
        st.sidebar.error("Filters exclude every session.")
    else:
        st.sidebar.success(
            f"{len(filtered):,} sessions · "
            f"{filtered['Energy_kWh'].sum():,.0f} kWh · "
            f"{format_currency(filtered['Net_Billable_MYR'].sum())}"
        )

    brand_header()

    if chosen == "overview":
        page_overview(filtered)
    elif chosen == "analytics":
        page_analytics(filtered)
    elif chosen == "alerts":
        page_alerts(filtered)
    else:
        page_explorer(filtered)


if __name__ == "__main__":
    main()
