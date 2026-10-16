"""Combine the five HDB resale CSVs from data.gov.sg into one compact Parquet file.

Usage:
    python scripts/build_dataset.py <folder-with-the-5-csvs>

Output: data/resale.parquet (one row per transaction) and data/dataset_meta.json.

Remaining lease at sale is taken from the `remaining_lease` column when HDB
publishes it (2015 onwards). For older records it is worked out from the lease
start year: 99 - (sale year - lease commencement year), so it is accurate to
the year, not the month.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
LEASE_YEARS = 99

# Files dated by approval date (before Mar 2012) vs registration date (after).
APPROVAL_FILES = ("1990", "2000")


def parse_remaining_lease(value: object) -> float | None:
    """'61 years 04 months' -> 61.33; '70' -> 70.0; NaN -> None."""
    if pd.isna(value):
        return None
    text = str(value)
    years = re.search(r"(\d+)\s*year", text)
    months = re.search(r"(\d+)\s*month", text)
    if years:
        return int(years.group(1)) + (int(months.group(1)) / 12 if months else 0)
    try:
        return float(text)
    except ValueError:
        return None


def load_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date_basis"] = "approval" if any(k in path.name for k in APPROVAL_FILES) else "registration"
    return df


def build(src: Path) -> pd.DataFrame:
    files = sorted(src.glob("*.csv"))
    files = [f for f in files if "Median" not in f.name]
    if len(files) != 5:
        raise SystemExit(f"Expected 5 resale CSVs in {src}, found {len(files)}")
    df = pd.concat([load_file(f) for f in files], ignore_index=True)

    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")
    df["town"] = df["town"].str.title().str.replace("/", " / ", regex=False)
    df["flat_type"] = df["flat_type"].str.upper().str.replace("MULTI-GENERATION", "MULTI GENERATION")
    df["flat_model"] = df["flat_model"].str.title()
    lo_hi = df["storey_range"].str.extract(r"(\d+) TO (\d+)").astype(float)
    df["storey_mid"] = lo_hi.mean(axis=1)

    sale_year = df["month"].dt.year + (df["month"].dt.month - 1) / 12
    derived = LEASE_YEARS - (sale_year - df["lease_commence_date"])
    published = df["remaining_lease"].map(parse_remaining_lease) if "remaining_lease" in df else None
    df["remaining_lease"] = published.fillna(derived) if published is not None else derived
    df["remaining_lease"] = df["remaining_lease"].clip(lower=0).round(2)
    df["price_psm"] = (df["resale_price"] / df["floor_area_sqm"]).round(1)

    cols = [
        "month", "date_basis", "town", "flat_type", "flat_model", "storey_mid",
        "floor_area_sqm", "lease_commence_date", "remaining_lease", "resale_price", "price_psm",
    ]
    df = df[cols].sort_values("month").reset_index(drop=True)
    for col in ("date_basis", "town", "flat_type", "flat_model"):
        df[col] = df[col].astype("category")
    df["storey_mid"] = df["storey_mid"].astype("float32")
    df["floor_area_sqm"] = df["floor_area_sqm"].astype("float32")
    df["lease_commence_date"] = df["lease_commence_date"].astype("int16")
    df["remaining_lease"] = df["remaining_lease"].astype("float32")
    df["price_psm"] = df["price_psm"].astype("float32")
    df["resale_price"] = df["resale_price"].astype("float32")
    return df


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    df = build(Path(sys.argv[1]))
    OUT_DIR.mkdir(exist_ok=True)
    df.to_parquet(OUT_DIR / "resale.parquet", index=False, compression="zstd")
    meta = {
        "rows": int(len(df)),
        "first_month": df["month"].min().strftime("%Y-%m"),
        "last_month": df["month"].max().strftime("%Y-%m"),
        "towns": int(df["town"].nunique()),
        "source": "HDB resale flat prices, data.gov.sg (Singapore Open Data Licence)",
    }
    (OUT_DIR / "dataset_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
