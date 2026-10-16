"""Map data for Town Safari: recent geocoded sales, MRT lines and stations, amenities.

Files in data/map/ come from the design hand-off (HDB resale data geocoded with OneMap,
MRT from OpenStreetMap via sgraildata, amenities from data.gov.sg / OneMap).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from runway.cpf_rules import check_lease

MAP_DIR = Path(__file__).resolve().parent.parent / "data" / "map"
PHOTO_DIR = Path(__file__).resolve().parent.parent / "data" / "photos"

REGIONS = {
    "North": ["SEMBAWANG", "WOODLANDS", "YISHUN"],
    "North-East": ["ANG MO KIO", "HOUGANG", "PUNGGOL", "SENGKANG", "SERANGOON"],
    "East": ["BEDOK", "PASIR RIS", "TAMPINES"],
    "West": ["BUKIT BATOK", "BUKIT PANJANG", "CHOA CHU KANG", "CLEMENTI", "JURONG EAST", "JURONG WEST"],
    "Central": ["BISHAN", "BUKIT MERAH", "BUKIT TIMAH", "CENTRAL AREA", "GEYLANG", "KALLANG/WHAMPOA",
                "MARINE PARADE", "QUEENSTOWN", "TOA PAYOH"],
}
ALL_TOWNS = [t for towns in REGIONS.values() for t in towns]

# sgraildata colour names -> official line colours (design spec)
LINE_COLOURS = {
    "orangered": "#D42E12", "mediumseagreen": "#009645", "darkmagenta": "#9900AA", "orange": "#FA9E0D",
    "darkslateblue": "#005EC4", "saddlebrown": "#9D5B25", "gray": "#748477",
}
AMENITIES = {  # category -> (label, colour)
    "hawker": ("Hawker centres", "#9A5B0C"),
    "clinic": ("Polyclinics", "#B3261E"),
    "mall": ("Shopping malls", "#6B4C9A"),
    "school": ("Primary schools", "#2B5C8A"),
    "cc": ("Community clubs", "#2C6845"),
}


def town_label(town: str) -> str:
    """'KALLANG/WHAMPOA' -> 'Kallang / Whampoa' (the spelling resale.parquet uses)."""
    return town.title().replace("/", " / ")


def load_sales() -> pd.DataFrame:
    df = pd.read_csv(MAP_DIR / "recent_sales_2026Q3.csv")
    df["block_id"] = df["block"].astype(str) + " " + df["street_name"]
    return df


def load_rail_lines() -> list[dict]:
    return json.loads((MAP_DIR / "rail_lines.geojson").read_text())["features"]


def load_stations() -> pd.DataFrame:
    return pd.read_csv(MAP_DIR / "rail_stations.csv")


def load_amenities() -> pd.DataFrame:
    return pd.read_csv(MAP_DIR / "amenities.csv")


def town_photo(town: str) -> Path | None:
    path = PHOTO_DIR / f"{town.lower().replace(' ', '_').replace('/', '_')}.jpg"
    return path if path.exists() else None


def verdict(youngest_age: int, remaining_lease: float) -> str:
    """'full', 'part' or 'none' CPF use for this buyer and lease."""
    result = check_lease(youngest_age, remaining_lease)
    if not result.cpf_allowed:
        return "none"
    return "full" if result.covers_95 else "part"


def blocks(sales: pd.DataFrame, youngest_age: int) -> pd.DataFrame:
    """One row per block: position, number of sales, and the shortest lease's verdict and coverage."""
    grouped = sales.groupby(["block_id", "lat", "lng"], as_index=False).agg(
        n_sales=("resale_price", "size"), lease=("remaining_lease_years", "min"))
    grouped["verdict"] = [verdict(youngest_age, lease) for lease in grouped["lease"]]
    grouped["coverage"] = [check_lease(youngest_age, lease).cpf_share for lease in grouped["lease"]]
    return grouped


def nearest_block(block_rows: pd.DataFrame, lat: float, lng: float) -> str | None:
    """Map a clicked marker position back to its block (markers sit exactly on block coordinates)."""
    if block_rows.empty:
        return None
    dist = (block_rows["lat"] - lat) ** 2 + (block_rows["lng"] - lng) ** 2
    idx = dist.idxmin()
    return block_rows.at[idx, "block_id"] if dist[idx] < 1e-8 else None
