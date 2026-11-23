"""Tools Ask Runway's AI can call: Runway's own calculators, so a question with the user's own numbers
("I'm 32 and the flat has 61 years left") gets a worked answer instead of a referral to the map, and a price lookup
that reads the same HDB resale-price figures as the Trends page (what a lease band did to price in a town).

The model never does the arithmetic. It picks a tool and its inputs; Python runs the calculator (runway.cpf_rules,
runway.costs) and hands back the figures, which the answer must quote as given (the number guard in runway.llm checks
every figure against the passages, the question and these tool results).
"""

from __future__ import annotations

import calendar
import json
import math

from runway.costs import stamp_duty
from runway.cpf_rules import HDB_LTV, check_lease, lease_needed_for_full_cpf, max_loan_tenure

CALCULATOR_SOURCE = "Runway's calculator (runway/cpf_rules.py, runway/costs.py)"
TRENDS_SOURCE = "HDB resale prices (data.gov.sg), the figures behind Runway's Trends page (runway/trends.py)"
MAX_STEPS = 3  # model turns per question: tool calls, then the answer; each one spends the shared hourly AI budget
DEADLINE_SECONDS = 75  # no new model turn after this: the page stops waiting at 90 s

TOOLS = [
    {
        "name": "cpf_lease_check",
        "description": (
            "Apply the lease-to-age-95 rule for one flat: whether the remaining lease covers the youngest buyer to "
            "age 95, how much of the Valuation Limit CPF can pay (percent), the HDB loan limit (percent of price or "
            "value), and the lease needed for full CPF use. Use it whenever the user gives an age and a remaining "
            "lease (or lease years left)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "youngest_age": {"type": "integer", "description": "Age of the youngest buyer, 21 to 85."},
                "remaining_lease_years": {"type": "number", "description": "Years of lease the flat has left, 0 to 99."},
            },
            "required": ["youngest_age", "remaining_lease_years"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "hdb_loan_tenure",
        "description": (
            "Longest HDB housing loan for the buyers: the shortest of 25 years, 65 minus the buyers' average age, "
            "and the remaining lease minus 20 years. Use it when the user asks how long their loan can be."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "buyer_ages": {"type": "array", "items": {"type": "integer"},
                               "description": "Age of every buyer, each 21 to 85 (1 to 6 buyers)."},
                "remaining_lease_years": {"type": "number", "description": "Years of lease the flat has left, 0 to 99."},
            },
            "required": ["buyer_ages", "remaining_lease_years"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "buyers_stamp_duty",
        "description": "Buyer's Stamp Duty in dollars for a residential purchase price (IRAS rates from 15 Feb 2023).",
        "input_schema": {
            "type": "object",
            "properties": {"price": {"type": "number", "description": "Purchase price in Singapore dollars."}},
            "required": ["price"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "price_by_lease",
        "description": (
            "Median resale price per square metre for one town and flat type, for flats in the same lease band as the "
            "user's remaining lease, and how that compares with the 80 to 89 band (or the 50 to 59 band when the lease "
            "is 80 years or more), from the last two years of HDB resale prices. Use it when the user asks what a "
            "shorter lease does to prices in a town. Call it only with a town, flat type and remaining lease the user "
            "gave; if one is missing, ask for it instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "town": {"type": "string", "description": "HDB town, for example Bedok or Ang Mo Kio."},
                "flat_type": {"type": "string", "enum": ["3-room", "4-room", "5-room", "Executive"]},
                "remaining_lease_years": {"type": "number", "description": "Years of lease the flat has left, 1 to 99."},
            },
            "required": ["town", "flat_type", "remaining_lease_years"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def figure(x: float) -> str:
    """One way to write a figure, so the answer can copy it exactly: whole numbers without a decimal point."""
    x = round(float(x), 1)
    return str(int(x)) if x == int(x) else str(x)


def input_numbers(args) -> set[str]:
    """Every number in a tool's input, written as the user would ("65", "61.5", "500000"), to check they typed it."""
    found: set[str] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            found.add(str(int(v)) if float(v).is_integer() else str(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(args)
    return found


def money(x: float) -> str:
    return f"${round(float(x)):,}"


def _age(v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 21 <= v <= 85:
        raise ValueError("ages must be whole numbers from 21 to 85")
    return v


def _lease(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 99:
        raise ValueError("remaining lease must be 0 to 99 years")
    return float(v)


def _month(ym: str) -> str:
    return f"{calendar.month_name[int(ym[5:7])]} {ym[:4]}"  # "2026-09" -> "September 2026"


def run(name: str, args) -> tuple[str, bool]:
    """Run one tool. Returns (JSON text for the model, is_error). Inputs come from the model: checked, never trusted."""
    source = CALCULATOR_SOURCE
    try:
        if not isinstance(args, dict):
            raise ValueError("inputs must be an object")
        if name == "cpf_lease_check":
            age, lease = _age(args.get("youngest_age")), _lease(args.get("remaining_lease_years"))
            c = check_lease(age, lease)
            out = {
                "lease_ends_when_youngest_is": figure(c.covers_to_age),
                "covers_youngest_to_95": c.covers_95,
                "years_short_of_95": figure(c.years_short),
                "cpf_can_be_used": c.cpf_allowed,
                "cpf_usable_percent_of_valuation_limit": figure(c.cpf_share * 100),
                "hdb_loan_limit_percent": figure(c.ltv_share * 100),
                "full_hdb_loan_limit_percent": figure(HDB_LTV * 100),
                "lease_needed_for_full_cpf": figure(lease_needed_for_full_cpf(age)),
            }
        elif name == "hdb_loan_tenure":
            ages = args.get("buyer_ages")
            if not isinstance(ages, list) or not 1 <= len(ages) <= 6:
                raise ValueError("give 1 to 6 buyer ages")
            ages = [_age(a) for a in ages]
            lease = _lease(args.get("remaining_lease_years"))
            out = {"average_age": figure(sum(ages) / len(ages)),
                   "longest_hdb_loan_years": figure(max_loan_tenure(ages, lease))}
        elif name == "buyers_stamp_duty":
            price = args.get("price")
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not 0 < price <= 10_000_000:
                raise ValueError("price must be between $1 and $10,000,000")
            out = {"buyers_stamp_duty": money(stamp_duty(price))}
        elif name == "price_by_lease":
            from runway import trends  # pandas loads on first use, as for the Trends page

            lease = _lease(args.get("remaining_lease_years"))
            if lease < 1:
                raise ValueError("remaining lease must be at least 1 year")
            r = trends.lease_price_gap(trends.load_trends(), args.get("town"), args.get("flat_type"), lease)
            if r["psm"] is None:
                raise ValueError(f"too few recent sales of {r['flat_type']} flats in {r['town']} with {r['band'].lower()} "
                                 "years of lease left to give a median")
            out = {"town": r["town"], "flat_type": r["flat_type"], "lease_band_years": r["band"],
                   "median_price_per_sqm_in_this_band": money(r["psm"]),
                   "sales_window": f"{_month(r['since'])} to {_month(r['last'])}"}
            if r["ref_psm"] is None:
                out["comparison"] = f"too few sales with {r['ref_band']} years of lease left to compare"
            else:
                gap = math.floor((r["ref_psm"] - r["psm"]) / r["ref_psm"] * 100 + 0.5)  # rounds halves up, as the page does
                out.update(compared_with_lease_band_years=r["ref_band"],
                           median_price_per_sqm_in_compared_band=money(r["ref_psm"]),
                           percent_difference=figure(abs(gap)),
                           this_band_price_is="lower" if gap > 0 else "higher" if gap < 0 else "the same")
            out["how_to_say_it"] = "a market pattern between different flats, not the lease alone"
            source = TRENDS_SOURCE
        else:
            raise ValueError(f"unknown tool {name}")
    except ValueError as exc:
        return json.dumps({"error": str(exc)}), True
    out["source"] = source
    return json.dumps(out), False
