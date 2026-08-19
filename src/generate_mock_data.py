"""
generate_mock_data.py

Produces fake (but structurally realistic) crew-capacity, work-order-backlog,
and 5-year-forecast data for the Electric Operations PMO capability-forecasting
demo. Nothing here is real Con Edison data -- it's shaped to resemble what a
"Programs & Project Planning" role would pull from WMS / Oracle BI, so the rest
of the pipeline (aggregation, variance flagging, narrative) has something
realistic to chew on.

Run directly to (re)write the three CSVs under data/:
    python src/generate_mock_data.py
"""

import numpy as np
import pandas as pd
from pathlib import Path

SEED = 42
rng = np.random.default_rng(SEED)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

REGIONS = ["Manhattan", "Bronx", "Brooklyn/Queens", "Westchester"]
PROGRAMS = [
    "Overhead Line Rebuild",
    "Underground Cable Replacement",
    "Substation Upgrade",
    "Vegetation Management",
    "Storm Hardening",
]

# Trailing 12 months ending at the "current" reporting month.
MONTHS = pd.period_range(end="2026-08", periods=12, freq="M")

# Baseline monthly available crew-hours per region (varies by region size).
BASE_CAPACITY = {
    "Manhattan": 9200,
    "Bronx": 7400,
    "Brooklyn/Queens": 10600,
    "Westchester": 6100,
}

# Regions where the work-order backlog is deliberately ramping past capacity,
# so the variance/status logic downstream has something real to flag.
DEMAND_GROWTH = {
    "Manhattan": 0.030,   # steady overrun growth -> should trip "warning"/"critical"
    "Bronx": 0.006,       # roughly tracks capacity -> stays "good"
    "Brooklyn/Queens": 0.041,  # fastest-growing backlog -> should trip "critical"
    "Westchester": -0.004,     # slightly under -> stays "good"/surplus
}


def build_crew_capacity() -> pd.DataFrame:
    rows = []
    for region in REGIONS:
        base = BASE_CAPACITY[region]
        for i, month in enumerate(MONTHS):
            # Mild winter dip (storm/emergency response pulls crews off planned work)
            month_num = month.month
            seasonal = -0.08 if month_num in (12, 1, 2) else 0.0
            noise = rng.normal(0, 0.02)
            hours = base * (1 + seasonal + noise)
            rows.append(
                {
                    "region": region,
                    "month": str(month),
                    "available_crew_hours": round(hours),
                }
            )
    return pd.DataFrame(rows)


def build_work_order_backlog() -> pd.DataFrame:
    rows = []
    for region in REGIONS:
        base_demand = BASE_CAPACITY[region] * 0.90  # starts a bit under capacity
        growth = DEMAND_GROWTH[region]
        for i, month in enumerate(MONTHS):
            region_total = base_demand * ((1 + growth) ** i) * (1 + rng.normal(0, 0.015))
            # Split the region's monthly demand across programs with fixed-ish weights
            weights = rng.dirichlet(np.ones(len(PROGRAMS)) * 3)
            for program, w in zip(PROGRAMS, weights):
                rows.append(
                    {
                        "region": region,
                        "program": program,
                        "month": str(MONTHS[i]),
                        "required_hours": round(region_total * w),
                        "priority": rng.choice(["High", "Medium", "Low"], p=[0.25, 0.5, 0.25]),
                    }
                )
    return pd.DataFrame(rows)


def build_five_year_forecast() -> pd.DataFrame:
    rows = []
    years = list(range(2026, 2031))
    for region in REGIONS:
        base = BASE_CAPACITY[region] * 12  # annualized
        growth = DEMAND_GROWTH[region] + 0.01  # forecast assumes a bit more capital-plan growth
        for i, year in enumerate(years):
            planned = base * ((1 + growth) ** i)
            rows.append(
                {
                    "region": region,
                    "year": year,
                    "planned_hours": round(planned),
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cap = build_crew_capacity()
    backlog = build_work_order_backlog()
    forecast = build_five_year_forecast()

    cap.to_csv(DATA_DIR / "crew_capacity.csv", index=False)
    backlog.to_csv(DATA_DIR / "work_order_backlog.csv", index=False)
    forecast.to_csv(DATA_DIR / "five_year_forecast.csv", index=False)

    print(f"Wrote {len(cap)} rows to data/crew_capacity.csv")
    print(f"Wrote {len(backlog)} rows to data/work_order_backlog.csv")
    print(f"Wrote {len(forecast)} rows to data/five_year_forecast.csv")
