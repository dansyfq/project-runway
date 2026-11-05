"""Price-trend numbers for the public Trends screen.

Everything comes from the full HDB resale history in data/resale.parquet (1990 to the latest month).
Medians are shown only where a cell has at least MIN_SALES sales, so a thin town/flat-type/year is left
blank instead of looking precise. Prices are nominal (not adjusted for inflation).

Kept deliberately simple: four group-bys over the ~1M rows, then plain Python to lay the results out.
"""

from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
import pandas as pd

PARQUET = Path(__file__).resolve().parent.parent / "data" / "resale.parquet"
COLUMNS = ["month", "town", "flat_type", "resale_price", "price_psm", "remaining_lease"]
FLAT_TYPES = ["3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
ALL_TOWNS = "All towns"
MIN_SALES = 10
RECENT_MONTHS = 24  # the lease chart looks at the latest two years of sales
BAND_STARTS = [50, 60, 70, 80, 90]  # lease bands: under 50, 50-59, ..., 90 or more
BAND_LABELS = ["Under 50", "50 to 59", "60 to 69", "70 to 79", "80 to 89", "90 or more"]


def _aggregate(d: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Median price and price per sqm, plus the number of sales, for each group."""
    return d.groupby(keys).agg(
        price=("resale_price", "median"), psm=("price_psm", "median"), n=("resale_price", "size")
    ).reset_index()


def _fill(agg: pd.DataFrame, by_town: bool, size: int, out: dict) -> None:
    """Write each group's medians into out[metric][flat_type][place][position]; thin groups stay None."""
    for row in agg.itertuples(index=False):
        if int(row.n) < MIN_SALES:
            continue
        place = str(row.town) if by_town else ALL_TOWNS
        for metric, value, step in (("price", row.price, 100), ("psm", row.psm, 1)):
            cells = out[metric][str(row.flat_type)].setdefault(place, [None] * size)
            cells[int(row.pos)] = int(round(float(value) / step) * step)


def build_trends(df: pd.DataFrame) -> dict:
    df = df[COLUMNS].copy()
    df["town"] = df["town"].astype(str)
    df["flat_type"] = df["flat_type"].astype(str)
    df = df[df["flat_type"].isin(FLAT_TYPES)].copy()
    month = pd.to_datetime(df["month"])
    year = month.dt.year.to_numpy()
    first, last_year = int(year.min()), int(year.max())
    last = month.max()
    since = last - pd.DateOffset(months=RECENT_MONTHS - 1)

    yearly = df.assign(pos=year - first)
    recent = df[(month >= since).to_numpy()].copy()
    recent["pos"] = np.searchsorted(BAND_STARTS, recent["remaining_lease"].to_numpy(dtype=float), side="right")

    def empty() -> dict:
        return {metric: {t: {} for t in FLAT_TYPES} for metric in ("price", "psm")}

    by_year, by_band = empty(), empty()
    n_years = last_year - first + 1
    for frame, size, out in ((yearly, n_years, by_year), (recent, len(BAND_LABELS), by_band)):
        _fill(_aggregate(frame, ["flat_type", "town", "pos"]), True, size, out)
        _fill(_aggregate(frame, ["flat_type", "pos"]), False, size, out)

    return {
        "years": list(range(first, last_year + 1)),
        "towns": sorted(df["town"].unique().tolist()),
        "all_towns": ALL_TOWNS,
        "types": FLAT_TYPES,
        "last_month": last.strftime("%Y-%m"),
        "since_month": since.strftime("%Y-%m"),
        "min_sales": MIN_SALES,
        "bands": BAND_LABELS,
        "price": by_year["price"], "psm": by_year["psm"],
        "lease_price": by_band["price"], "lease_psm": by_band["psm"],
    }


@functools.lru_cache(maxsize=1)
def load_trends() -> dict:
    """Built once per server process, then reused for every visitor."""
    return build_trends(pd.read_parquet(PARQUET, columns=COLUMNS))
