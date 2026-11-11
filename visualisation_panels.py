"""
visualisation_panels.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section B, Question 2 (6 marks): publication-quality visualisation module.

Renders the three mandatory panels from the cleaned dataset and writes them to
``assets/figures`` at 300 dpi:

    panel1_grid_vs_solar.png   hourly grid demand vs. rooftop solar generation
    panel2_cost_by_user.png    session cost distribution by user type
    panel3_temp_vs_energy.png  battery temperature vs. energy delivered
    panel_all.png              composite A4-landscape panel for the dashboard

Run with::

    python visualisation_panels.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

import data_pipeline
import visualisations as viz

BASE_DIR = Path(__file__).resolve().parent
FIGURE_DIR = BASE_DIR / "assets" / "figures"
LOGGER = logging.getLogger("ev_visuals")


def render_panels(frame: pd.DataFrame) -> dict[str, Path]:
    """Build every Section B panel and return the written file paths.

    Parameters
    ----------
    frame:
        Cleaned session table produced by :mod:`data_pipeline`.

    Returns
    -------
    dict[str, Path]
        Mapping of panel name to the PNG written on disk.
    """
    viz.apply_house_style()
    outputs: dict[str, Path] = {}

    outputs["panel1"] = viz.save(viz.plot_grid_vs_solar(frame),
                                 FIGURE_DIR / "panel1_grid_vs_solar.png")
    outputs["panel2"] = viz.save(viz.plot_cost_by_user(frame),
                                 FIGURE_DIR / "panel2_cost_by_user.png")
    outputs["panel3"] = viz.save(viz.plot_temp_vs_energy(frame),
                                 FIGURE_DIR / "panel3_temp_vs_energy.png")
    outputs["composite"] = viz.save(viz.build_publication_panel(frame),
                                    FIGURE_DIR / "panel_all.png")

    # --- quantitative sanity checks printed for the marker ---------------- #
    demand = viz.hourly_grid_demand(frame)
    peak = demand.loc[demand["Grid_Demand_kWh"].idxmax()]
    solar_peak = demand.loc[demand["Solar_Generation_kW"].idxmax()]
    print("\n--- PANEL 1 CHECK: grid demand vs solar generation ---")
    print(f"Peak demand hour      : {int(peak['Start_Hour']):02d}:00  "
          f"({peak['Grid_Demand_kWh']:,.1f} kWh)")
    print(f"Peak solar hour       : {int(solar_peak['Start_Hour']):02d}:00  "
          f"({solar_peak['Solar_Generation_kW']:,.1f} kW)")
    overlap = float((demand["Solar_Generation_kW"] > 400).sum())
    print(f"Hours with >400 kW PV : {overlap:.0f} of 24")

    print("\n--- PANEL 2 CHECK: session cost by user type ---")
    print(frame.groupby("User_Type")["Net_Billable_MYR"]
          .describe()[["count", "mean", "50%", "max"]].round(2).to_string())

    print("\n--- PANEL 3 CHECK: battery temperature vs energy ---")
    print(f"Pearson r             : "
          f"{frame['Battery_Temp_C'].corr(frame['Energy_kWh']):+.3f}")
    print(f"Rows above 45 degC    : {int((frame['Battery_Temp_C'] > 45).sum())}")

    return outputs


def main() -> int:
    """Load the cleaned dataset, render the panels and report the file paths."""
    logging.basicConfig(level=logging.INFO,
                        format="[%(levelname)-7s] %(message)s", stream=sys.stdout)
    try:
        frame = data_pipeline.load()
    except (FileNotFoundError, pd.errors.EmptyDataError) as exc:
        LOGGER.error("Cannot build panels: %s", exc)
        return 2

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    written = render_panels(frame)
    print("\n--- FIGURES WRITTEN ---")
    for name, path in written.items():
        print(f"{name:<10} -> {path.relative_to(BASE_DIR)} "
              f"({path.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
