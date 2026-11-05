"""Price-trend numbers: medians, thin-cell suppression, lease bands and the bridge message."""

import pandas as pd

from runway.trends import ALL_TOWNS, BAND_LABELS, MIN_SALES, build_trends


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
