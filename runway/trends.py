"""Price-trend numbers for the public Trends screen.

Everything comes from the full HDB resale history in data/resale.parquet (1990 to the latest month).
Medians are shown only where a cell has at least MIN_SALES sales, so a thin town/flat-type/year is left
blank instead of looking precise. Prices are nominal (not adjusted for inflation).
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

PARQUET = Path(__file__).resolve().parent.parent / "data" / "resale.parquet"
COLUMNS = ["month", "town", "flat_type", "resale_price", "price_psm", "remaining_lease"]
FLAT_TYPES = ["3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
ALL_TOWNS = "All towns"
MIN_SALES = 10
RECENT_MONTHS = 24  # the lease chart looks at the latest two years of sales
BAND_EDGES = [0, 50, 60, 70, 80, 90, 1000]
BAND_LABELS = ["Under 50", "50 to 59", "60 to 69", "70 to 79", "80 to 89", "90 or more"]


def _clean(values, step: int) -> list[int | None]:
    return [None if pd.isna(v) else int(round(float(v) / step) * step) for v in values]


def _pivot(d: pd.DataFrame, across: str, labels: list, col: str, step: int) -> dict[str, list[int | None]]:
    """Median of `col` for each town (plus all towns) across `labels`; None where there are too few sales."""
    enough = lambda s: s["median"].where(s["size"] >= MIN_SALES)  # noqa: E731
    by_town = d.groupby(["town", across])[col].agg(["median", "size"])
    by_all = d.groupby(across)[col].agg(["median", "size"])
    wide = enough(by_town).unstack(across).reindex(columns=labels)
    out = {str(town): _clean(row, step) for town, row in wide.iterrows()}
    out[ALL_TOWNS] = _clean(enough(by_all).reindex(labels), step)
    return out


def build_trends(df: pd.DataFrame) -> dict:
    df = df[COLUMNS].copy()
    df["town"] = df["town"].astype(str)
    df["flat_type"] = df["flat_type"].astype(str)
    df["year"] = df["month"].dt.year
    years = list(range(int(df["year"].min()), int(df["year"].max()) + 1))
    last = df["month"].max()
    since = last - pd.DateOffset(months=RECENT_MONTHS - 1)
    recent = df[df["month"] >= since].copy()
    recent["band"] = pd.cut(recent["remaining_lease"], bins=BAND_EDGES, labels=BAND_LABELS, right=False)
    recent = recent[recent["band"].notna()]
    recent["band"] = recent["band"].astype(str)

    out: dict = {
        "years": years,
        "towns": sorted(df["town"].unique().tolist()),
        "all_towns": ALL_TOWNS,
        "types": FLAT_TYPES,
        "last_month": last.strftime("%Y-%m"),
        "since_month": since.strftime("%Y-%m"),
        "min_sales": MIN_SALES,
        "bands": BAND_LABELS,
        "price": {}, "psm": {}, "lease_price": {}, "lease_psm": {},
    }
    for flat_type in FLAT_TYPES:
        d, r = df[df["flat_type"] == flat_type], recent[recent["flat_type"] == flat_type]
        out["price"][flat_type] = _pivot(d, "year", years, "resale_price", 100) if len(d) else {}
        out["psm"][flat_type] = _pivot(d, "year", years, "price_psm", 1) if len(d) else {}
        out["lease_price"][flat_type] = _pivot(r, "band", BAND_LABELS, "resale_price", 100) if len(r) else {}
        out["lease_psm"][flat_type] = _pivot(r, "band", BAND_LABELS, "price_psm", 1) if len(r) else {}
    return out


@functools.lru_cache(maxsize=1)
def load_trends() -> dict:
    """Built once per server process (about a second for ~1M rows), then reused for every visitor."""
    return build_trends(pd.read_parquet(PARQUET, columns=COLUMNS))
