"""CPF usage and HDB loan limits under the lease-to-age-95 rule.

Plain arithmetic only: the LLM never calculates, it only explains these results.

Sources (in data/corpus):
- MND/MOM joint press release, 9 May 2019, Annexes A and B (the rule and worked examples)
- CPF Board FAQ: lease not covering youngest buyer to age 95 (25-year-olds, 65 years -> 90%)
- HDB, Housing Loan from HDB: LTV up to 75%, pro-rated when lease < age 95; loan tenure cap
"""

from __future__ import annotations

from dataclasses import dataclass

COVER_TO_AGE = 95
MIN_LEASE = 20  # CPF cannot be used at or below 20 years of remaining lease
HDB_LTV = 0.75  # HDB loans, resale applications from 20 Aug 2024
HDB_LTV_2019 = 0.90  # value used in the May 2019 worked examples
MAX_TENURE = 25
TENURE_AGE_CAP = 65


@dataclass(frozen=True)
class LeaseCheck:
    youngest_age: int
    remaining_lease: float
    covers_to_age: float  # age of the youngest buyer when the lease runs out
    covers_95: bool
    cpf_allowed: bool
    cpf_share: float  # fraction of the Valuation Limit that CPF can pay for
    ltv_share: float  # HDB loan-to-value limit as a fraction
    years_short: float  # how many years the lease falls short of age 95


def cpf_share(youngest_age: int, remaining_lease: float) -> float:
    """Fraction of the Valuation Limit payable with CPF.

    Full use if the lease covers the youngest buyer to 95. Otherwise pro-rated:
        (remaining lease - 20) / (95 - youngest age - 20)
    which reproduces every official example (e.g. age 25, 65 years -> 90%).
    """
    if youngest_age < 0 or remaining_lease < 0:
        raise ValueError("age and remaining lease must be non-negative")
    if remaining_lease <= MIN_LEASE:
        return 0.0
    if youngest_age + remaining_lease >= COVER_TO_AGE:
        return 1.0
    needed = COVER_TO_AGE - youngest_age - MIN_LEASE
    return (remaining_lease - MIN_LEASE) / needed


def check_lease(youngest_age: int, remaining_lease: float, ltv_cap: float = HDB_LTV) -> LeaseCheck:
    share = cpf_share(youngest_age, remaining_lease)
    covers_to = youngest_age + remaining_lease
    return LeaseCheck(
        youngest_age=youngest_age,
        remaining_lease=remaining_lease,
        covers_to_age=covers_to,
        covers_95=covers_to >= COVER_TO_AGE,
        cpf_allowed=share > 0,
        cpf_share=share,
        ltv_share=ltv_cap * share,
        years_short=max(0.0, COVER_TO_AGE - covers_to),
    )


def max_loan_tenure(buyer_ages: list[int], remaining_lease: float) -> float:
    """HDB loan tenure: shortest of 25 years, 65 - average age, remaining lease - 20."""
    if not buyer_ages:
        raise ValueError("need at least one buyer age")
    avg_age = sum(buyer_ages) / len(buyer_ages)
    return max(0.0, min(MAX_TENURE, TENURE_AGE_CAP - avg_age, remaining_lease - MIN_LEASE))


ASSUMED_HDB_RATE = 0.026  # illustration only: 0.1% above the CPF OA rate of 2.5%


@dataclass(frozen=True)
class FlatMoney:
    check: LeaseCheck
    cpf_cap: float  # most CPF usable for this flat
    cash_on_top: float  # part of the price CPF can never pay (interest ignored)
    loan_max: float
    tenure: float
    monthly: float  # illustration at ASSUMED_HDB_RATE over the full tenure
    cash_at_start: float  # price - loan - CPF OA used now


def monthly_instalment(principal: float, years: float, rate: float = ASSUMED_HDB_RATE) -> float:
    if principal <= 0 or years <= 0:
        return 0.0
    i, n = rate / 12, years * 12
    return principal * i / (1 - (1 + i) ** -n)


def flat_money(price: float, remaining_lease: float, buyer_ages: list[int], cpf_oa: float = 0.0) -> FlatMoney:
    """Dollar figures for one flat. Valuation is taken as the price (no cash-over-valuation)."""
    lease_check = check_lease(min(buyer_ages), remaining_lease)
    cap = price * lease_check.cpf_share
    tenure = max_loan_tenure(buyer_ages, remaining_lease)
    loan = price * lease_check.ltv_share if tenure > 0 else 0.0
    oa_now = min(cpf_oa, cap, price - loan)
    return FlatMoney(
        check=lease_check, cpf_cap=cap, cash_on_top=price - cap, loan_max=loan, tenure=tenure,
        monthly=monthly_instalment(loan, tenure), cash_at_start=price - loan - oa_now,
    )


def lease_needed_for_full_cpf(youngest_age: int) -> int:
    """Remaining lease that covers the youngest buyer to 95, so CPF can be used in full."""
    return COVER_TO_AGE - youngest_age
