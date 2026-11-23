"""Price-trend numbers: medians, thin-cell suppression, lease bands and the bridge message."""

import pandas as pd

import numpy as np
import pytest

from runway.trends import ALL_TOWNS, BAND_LABELS, BAND_STARTS, MIN_SALES, build_trends, lease_band, lease_price_gap


def sales(town, flat_type, year, n, price, lease=70.0, month=1):
    return pd.DataFrame({
        "month": [pd.Timestamp(year=year, month=month, day=1)] * n,
        "town": [town] * n, "flat_type": [flat_type] * n,
        "resale_price": [float(price)] * n, "price_psm": [float(price) / 100] * n,
        "remaining_lease": [lease] * n,
    })


def frame():
    return pd.concat([
        sales("Bishan", "4 ROOM", 2020, MIN_SALES, 500_000),
        sales("Bishan", "4 ROOM", 2021, MIN_SALES, 600_000),
        sales("Bishan", "4 ROOM", 2022, MIN_SALES - 1, 700_000),  # too few: left blank
        sales("Clementi", "4 ROOM", 2020, MIN_SALES, 400_000),
        sales("Clementi", "4 ROOM", 2021, MIN_SALES, 440_000),
        sales("Clementi", "4 ROOM", 2022, MIN_SALES, 480_000, lease=45.0, month=12),
    ], ignore_index=True)


def test_yearly_medians_per_town_and_overall():
    t = build_trends(frame())
    assert t["years"] == [2020, 2021, 2022]
    assert t["towns"] == ["Bishan", "Clementi"]
    price = t["price"]["4 ROOM"]
    assert price["Bishan"][:2] == [500_000, 600_000]
    assert price["Clementi"] == [400_000, 440_000, 480_000]
    assert price[ALL_TOWNS][0] == 450_000  # median of 10 x 500k and 10 x 400k


def test_thin_cells_are_blank_not_guessed():
    t = build_trends(frame())
    assert t["price"]["4 ROOM"]["Bishan"][2] is None


def test_lease_bands_use_the_latest_two_years():
    t = build_trends(frame())
    assert t["bands"] == BAND_LABELS
    row = t["lease_price"]["4 ROOM"]["Clementi"]
    assert row[BAND_LABELS.index("Under 50")] == 480_000  # only the Dec 2022 sales have 45 years left
    # Window is Jan 2021 to Dec 2022: the 2021 sales count, the 2020 ones don't (a median with them would be 420k).
    assert row[BAND_LABELS.index("70 to 79")] == 440_000


def test_flat_types_without_sales_come_back_empty():
    t = build_trends(frame())
    assert t["price"]["3 ROOM"] == {}


def test_trends_message_returns_the_data(monkeypatch):
    import runway.bridge as bridge

    monkeypatch.setattr(bridge, "load_trends", lambda: {"years": [2020]})
    reply = bridge.handle({"id": "x", "type": "trends", "payload": {}}, {}, {}, None, None)  # needs no AI or documents
    assert reply == {"ok": True, "data": {"years": [2020]}}


def test_trends_message_reports_a_failure_instead_of_crashing(monkeypatch):
    import runway.bridge as bridge

    def boom():
        raise ValueError("bad data")

    monkeypatch.setattr(bridge, "load_trends", boom)
    reply = bridge.handle({"id": "x", "type": "trends", "payload": {}}, {}, {}, None, None)
    assert reply == {"ok": False, "error": "ValueError: bad data"}


def test_lease_band_matches_how_sales_are_banded():
    for lease in (1, 49.9, 50, 59.9, 60, 79.99, 80, 89.9, 90, 99):
        assert lease_band(lease) == int(np.searchsorted(BAND_STARTS, lease, side="right"))


def test_lease_price_gap_compares_with_the_far_band():
    t = build_trends(pd.concat([
        sales("Bedok", "4 ROOM", 2026, MIN_SALES, 500_000, lease=55.0, month=8),
        sales("Bedok", "4 ROOM", 2026, MIN_SALES, 800_000, lease=85.0, month=9),
        sales("Bedok", "4 ROOM", 2026, MIN_SALES - 1, 650_000, lease=70.0, month=9),
    ], ignore_index=True))
    short = lease_price_gap(t, "bedok", "4-room", 55.0)  # case and the hyphen do not matter
    assert (short["band"], short["psm"], short["ref_band"], short["ref_psm"]) == ("50 to 59", 5000, "80 to 89", 8000)
    assert (short["town"], short["flat_type"]) == ("Bedok", "4-room")
    long_ = lease_price_gap(t, "Bedok", "4 ROOM", 85.0)  # a lease of 80 or more is compared with the 50 to 59 band
    assert (long_["band"], long_["psm"], long_["ref_band"], long_["ref_psm"]) == ("80 to 89", 8000, "50 to 59", 5000)
    assert lease_price_gap(t, "Bedok", "4-room", 70.0)["psm"] is None  # too few sales: no median, never a guess
    assert (short["since"], short["last"]) == (t["since_month"], t["last_month"])


def test_lease_price_gap_rejects_unknown_towns_and_flat_types():
    t = build_trends(frame())
    with pytest.raises(ValueError, match="unknown town"):
        lease_price_gap(t, "Nowhere", "4-room", 60.0)
    with pytest.raises(ValueError, match="unknown flat type"):
        lease_price_gap(t, "Bishan", "2-room", 60.0)
