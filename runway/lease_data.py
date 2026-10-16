"""Lease premium by town, from HDB resale transactions.

Method (same as the proposal's Table 1): within one town and flat type, fit
    log(price per sqm) = a + b * remaining_lease
by least squares. exp(b) - 1 is the % change in price per sqm for one extra
year of lease. It is a market pattern, not a cause: it does not adjust for
floor level, size, model or condition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MIN_SALES = 100  # fewer sales than this and we do not report a premium
MIN_LEASE_SPREAD = 15  # years between the shortest and longest lease sold


@dataclass(frozen=True)
class TownPremium:
    town: str
    flat_type: str
    sales: int
    pct_per_year: float  # % change in price per sqm per extra year of lease
    ci_low: float
    ci_high: float
    intercept: float
    slope: float
    lease_min: float
    lease_max: float
    median_psm: float
    median_price: float
    reliable: bool
    note: str

    def predicted_psm(self, remaining_lease: float) -> float:
        return float(np.exp(self.intercept + self.slope * remaining_lease))


def load_transactions(path: Path = DATA_DIR / "resale.parquet") -> pd.DataFrame:
    return pd.read_parquet(path)


def load_meta(path: Path = DATA_DIR / "dataset_meta.json") -> dict:
    return json.loads(path.read_text())


def fit_premium(sales: pd.DataFrame, town: str, flat_type: str) -> TownPremium | None:
    """Fit the lease premium for one town and flat type, or None if there are too few sales."""
    n = len(sales)
    if n < 3:
        return None
    x = sales["remaining_lease"].to_numpy(dtype=float)
    y = np.log(sales["price_psm"].to_numpy(dtype=float))
    x_mean = x.mean()
    sxx = ((x - x_mean) ** 2).sum()
    if sxx == 0:
        return None
    slope = ((x - x_mean) * (y - y.mean())).sum() / sxx
    intercept = y.mean() - slope * x_mean
    resid = y - (intercept + slope * x)
    se = np.sqrt((resid**2).sum() / (n - 2) / sxx)

    spread = x.max() - x.min()
    notes = []
    if n < MIN_SALES:
        notes.append(f"only {n} sales")
    if spread < MIN_LEASE_SPREAD:
        notes.append(f"leases sold only span {spread:.0f} years")
    if slope <= 0:
        notes.append("shorter-lease flats here are not cheaper per sqm; other factors dominate")

    to_pct = lambda b: (np.exp(b) - 1) * 100  # noqa: E731
    return TownPremium(
        town=town,
        flat_type=flat_type,
        sales=n,
        pct_per_year=float(to_pct(slope)),
        ci_low=float(to_pct(slope - 1.96 * se)),
        ci_high=float(to_pct(slope + 1.96 * se)),
        intercept=float(intercept),
        slope=float(slope),
        lease_min=float(x.min()),
        lease_max=float(x.max()),
        median_psm=float(np.median(sales["price_psm"])),
        median_price=float(np.median(sales["resale_price"])),
        reliable=not notes,
        note="; ".join(notes),
    )


def recent_sales(df: pd.DataFrame, flat_type: str, since: str) -> pd.DataFrame:
    return df[(df["flat_type"] == flat_type) & (df["month"] >= pd.Timestamp(since))]


def premiums_by_town(df: pd.DataFrame, flat_type: str, since: str, towns: list[str] | None = None) -> list[TownPremium]:
    sales = recent_sales(df, flat_type, since)
    if towns:
        sales = sales[sales["town"].isin(towns)]
    out = []
    for town, group in sales.groupby("town", observed=True):
        premium = fit_premium(group, str(town), flat_type)
        if premium is not None:
            out.append(premium)
    return sorted(out, key=lambda p: p.pct_per_year)


def premium_table(premiums: list[TownPremium]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Town": [p.town for p in premiums],
            "Extra price per year of lease (%)": [round(p.pct_per_year, 2) for p in premiums],
            "95% range (%)": [f"{p.ci_low:.2f} to {p.ci_high:.2f}" for p in premiums],
            "Sales": [p.sales for p in premiums],
            "Leases sold (years)": [f"{p.lease_min:.0f}-{p.lease_max:.0f}" for p in premiums],
            "Median $/sqm": [round(p.median_psm) for p in premiums],
            "Caveat": [p.note or "-" for p in premiums],
        }
    )

