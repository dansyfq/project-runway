"""The CPF rule must reproduce every worked example published by the Government."""

import pytest

from runway.cpf_rules import (
    HDB_LTV_2019,
    check_lease,
    cpf_share,
    max_loan_tenure,
    lease_needed_for_full_cpf,
)


@pytest.mark.parametrize(
    ("age", "lease", "expected"),
    [
        (25, 85, 1.00),  # MND Annex B example 1 (Sammy and Devi)
        (45, 50, 1.00),  # MND Annex B example 2 (Jane)
        (25, 65, 0.90),  # MND Annex B example 3 and CPF FAQ ($495k of $550k)
        (25, 55, 0.70),  # MND Annex B sensitivity table
        (25, 75, 1.00),  # MND Annex B sensitivity table
    ],
)
def test_official_examples(age, lease, expected):
    assert cpf_share(age, lease) == pytest.approx(expected)


def test_annex_b_ltv_pro_rating_from_90_percent():
    # 2019 examples pro-rate the 90% LTV: 65 years -> 81%, 55 years -> 63%
    assert check_lease(25, 65, ltv_cap=HDB_LTV_2019).ltv_share == pytest.approx(0.81)
    assert check_lease(25, 55, ltv_cap=HDB_LTV_2019).ltv_share == pytest.approx(0.63)


def test_current_hdb_ltv_pro_rates_from_75_percent():
    assert check_lease(25, 65).ltv_share == pytest.approx(0.675)
    assert check_lease(30, 70).ltv_share == pytest.approx(0.75)


def test_submission_example_58_years_age_28():
    result = check_lease(28, 58)
    assert result.years_short == pytest.approx(9)
    assert result.cpf_share == pytest.approx(38 / 47)  # about 81%


def test_proposal_example_age_40_with_50_years_left():
    # (50 - 20) / (55 - 20) = 85.7% (the proposal's simpler 50/55 ratio is not the official formula)
    assert cpf_share(40, 50) == pytest.approx(30 / 35)


@pytest.mark.parametrize("lease", [0, 10, 20])
def test_no_cpf_at_or_below_20_years(lease):
    result = check_lease(30, lease)
    assert result.cpf_share == 0
    assert not result.cpf_allowed


def test_share_is_monotonic_in_lease_and_age():
    shares = [cpf_share(30, lease) for lease in range(21, 70)]
    assert shares == sorted(shares)
    by_age = [cpf_share(age, 50) for age in range(21, 60)]
    assert by_age == sorted(by_age)


def test_older_buyer_reaches_full_cpf():
    assert cpf_share(75, 21) == 1.0
    assert lease_needed_for_full_cpf(28) == 67


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        cpf_share(-1, 50)


def test_loan_tenure_caps():
    assert max_loan_tenure([30, 32], 80) == 25  # 25-year cap
    assert max_loan_tenure([50, 52], 80) == 14  # 65 - average age 51
    assert max_loan_tenure([30], 40) == 20  # lease - 20
    assert max_loan_tenure([70], 80) == 0
    with pytest.raises(ValueError):
        max_loan_tenure([], 80)
