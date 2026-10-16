import pytest

from runway.cpf_rules import flat_money, monthly_instalment
from runway.map_data import (
    ALL_TOWNS, blocks, load_amenities, load_rail_lines, load_sales, load_stations, nearest_block, town_label,
    verdict,
)


def test_cpf_board_example_in_dollars():
    """Design hand-off test T1: two 25-year-olds, 65 years left, $550,000 -> CPF up to $495,000."""
    money = flat_money(550_000, 65, [25, 25])
    assert money.cpf_cap == pytest.approx(495_000)
    assert money.cash_on_top == pytest.approx(55_000)
    assert money.loan_max == pytest.approx(550_000 * 0.675)


def test_short_lease_means_all_cash():
    money = flat_money(300_000, 20, [30])
    assert money.cpf_cap == 0 and money.loan_max == 0
    assert money.cash_at_start == 300_000


def test_cash_at_start_uses_oa_up_to_the_downpayment():
    money = flat_money(500_000, 80, [30, 32], cpf_oa=1_000_000)
    assert money.loan_max == pytest.approx(375_000)
    assert money.cash_at_start == pytest.approx(0)


def test_monthly_instalment():
    assert monthly_instalment(0, 25) == 0
    assert monthly_instalment(375_000, 25) == pytest.approx(1701, abs=2)  # standard annuity at 2.6%


@pytest.mark.parametrize(("age", "lease", "expected"), [(30, 70, "full"), (28, 58, "part"), (30, 20, "none")])
def test_verdict(age, lease, expected):
    assert verdict(age, lease) == expected


def test_map_files_load_and_cover_every_town():
    sales = load_sales()
    assert set(sales["town"]) == set(ALL_TOWNS)
    assert sales[["lat", "lng"]].notna().all().all()
    assert len(load_rail_lines()) > 5 and len(load_stations()) > 100 and len(load_amenities()) > 400


def test_blocks_group_sales_and_find_clicked_block():
    sales = load_sales()
    town = sales[sales["town"] == "CLEMENTI"]
    rows = blocks(town, 30)
    assert rows["n_sales"].sum() == len(town)
    first = rows.iloc[0]
    assert nearest_block(rows, first["lat"], first["lng"]) == first["block_id"]
    assert nearest_block(rows, 0.0, 0.0) is None


def test_town_label_matches_dataset_spelling():
    assert town_label("KALLANG/WHAMPOA") == "Kallang / Whampoa"
