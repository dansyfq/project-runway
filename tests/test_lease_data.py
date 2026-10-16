import numpy as np
import pandas as pd
import pytest

from runway.lease_data import fit_premium, load_meta, load_transactions, premiums_by_town


def synthetic(pct_per_year: float, n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lease = rng.uniform(50, 95, n)
    psm = 5000 * (1 + pct_per_year / 100) ** (lease - 70) * np.exp(rng.normal(0, 0.01, n))
    return pd.DataFrame({"remaining_lease": lease, "price_psm": psm, "resale_price": psm * 90})


def test_recovers_known_premium():
    p = fit_premium(synthetic(1.2), "Test Town", "4 ROOM")
    assert p.pct_per_year == pytest.approx(1.2, abs=0.05)
    assert p.ci_low < 1.2 < p.ci_high
    assert p.reliable
    assert p.predicted_psm(70) == pytest.approx(5000, rel=0.02)


def test_flags_small_or_narrow_samples():
    narrow = synthetic(1.0, n=50)
    narrow["remaining_lease"] = narrow["remaining_lease"] / 10 + 60  # spread under 15 years
    p = fit_premium(narrow, "Tiny", "4 ROOM")
    assert not p.reliable
    assert "only 50 sales" in p.note
    assert "span" in p.note


def test_flags_negative_slope():
    p = fit_premium(synthetic(-0.5), "Odd", "4 ROOM")
    assert not p.reliable
    assert "not cheaper" in p.note


def test_degenerate_input_returns_none():
    df = pd.DataFrame({"remaining_lease": [70.0] * 5, "price_psm": [5000.0] * 5, "resale_price": [1.0] * 5})
    assert fit_premium(df, "Flat", "4 ROOM") is None


def test_real_data_reproduces_proposal_table():
    """Proposal Table 1: 4-room flats sold from 2024. Data now runs to Sep 2026, so allow 0.05pp drift."""
    df = load_transactions()
    assert load_meta()["rows"] == 986_090
    got = {p.town: p.pct_per_year for p in premiums_by_town(df, "4 ROOM", "2024-01-01")}
    expected = {"Yishun": 0.51, "Hougang": 0.65, "Tampines": 0.92, "Queenstown": 1.40,
                "Ang Mo Kio": 1.49, "Toa Payoh": 1.54, "Clementi": 1.62}
    for town, pct in expected.items():
        assert got[town] == pytest.approx(pct, abs=0.05), town
