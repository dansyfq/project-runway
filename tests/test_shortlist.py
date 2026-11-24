"""Shortlist: the compare table's figures and the printable summary."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from runway.cpf_rules import flat_money

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node") or str(Path.home() / ".local/bin/node")
needs_node = pytest.mark.skipif(not (shutil.which("node") or Path(NODE).exists()), reason="needs Node.js")

# full (lease covers 95), part (pro-rated), none (20 years or less)
FLATS = [{"price": 500_000, "lease": 70.4, "sqm": 90, "ft": "4 ROOM"},
         {"price": 450_000, "lease": 50.25, "sqm": 100, "ft": "5 ROOM"},
         {"price": 300_000, "lease": 18, "sqm": 68, "ft": "3 ROOM"}]


def between(start, end):
    i = GAME.index(start)
    return GAME[i:GAME.index(end, i)]


def compare(tmp_path, age, avg):
    code = "\n".join([
        f"let S={{age:{age},avg:{avg},oa:0,oaSet:false}};",
        between("const exact = ", "\n"),
        between("function calc(price, lease){", "const VTXT = "),
        between("const VTXT = ", "\n"),
        between("function compareRows(fs){", "/* end compareRows */"),
        f"console.log(JSON.stringify(compareRows({json.dumps(FLATS)})));",
    ])
    js = tmp_path / "cmp.js"
    js.write_text(code)
    return {r["h"]: r for r in json.loads(subprocess.run([NODE, str(js)], capture_output=True, text=True, check=True).stdout)}


@needs_node
@pytest.mark.parametrize("age,avg", [(30, 30), (35, 50), (60, 66)])
def test_compare_rows_match_python_rules(tmp_path, age, avg):
    rows = compare(tmp_path, age, avg)
    money = [flat_money(f["price"], f["lease"], [age, 2 * avg - age], 0) for f in FLATS]
    assert rows["CPF verdict"]["cells"][2] == "CPF: not allowed"
    for i, m in enumerate(money):
        assert rows["CPF you can use"]["v"][i] == pytest.approx(m.cpf_cap)
        assert rows["Cash on top of CPF"]["v"][i] == pytest.approx(m.cash_on_top)
        assert rows["HDB loan limit"]["v"][i] == pytest.approx(m.loan_max)
        assert rows["Loan length"]["v"][i] == pytest.approx(m.tenure)
        assert rows["Monthly instalment at 2.6%"]["v"][i] == pytest.approx(m.monthly, rel=1e-6)
        assert rows["CPF verdict"]["v"][i] == pytest.approx(m.check.cpf_share)
        assert rows["Youngest buyer’s age when the lease ends"]["v"][i] == int(m.check.covers_to_age)
        if m.loan_max == 0:
            assert rows["HDB loan limit"]["cells"][i] == "No HDB loan"


@needs_node
def test_compare_marks_best_with_text_only_where_flats_differ(tmp_path):
    rows = compare(tmp_path, 30, 30)
    assert rows["CPF verdict"]["cells"][:2] == ["CPF: full use", "CPF: part only (67%)"]
    assert rows["Price"]["best"] == [False, False, True]
    assert rows["Price per sqm"]["cells"] == ["$5,556", "$4,500", "$4,412"]
    assert rows["Flat type and floor area"]["best"] == [False, True, False]
    assert rows["Lease left"]["best"] == [True, False, False]
    assert rows["CPF verdict"]["best"] == [True, False, False]
    assert not any(rows["CPF you can use"]["best"])  # no "better" direction, so no mark
    assert 'class="cmpbest">Best</b>' in GAME
    assert '<th scope="row">' in GAME and "<caption>" in GAME


def test_compare_selection_is_capped_and_in_memory():
    assert "const CMP=new Set();" in GAME
    assert "You can compare up to three flats" in GAME and 'id="cmpMsg" role="status"' in GAME
    block = between("function renderList(){", "/* ---------- Ask KEY")
    assert "localStorage" not in block and "history." not in block and "location" not in block


def test_print_summary_has_stylesheet_and_notice():
    css = between("/* ---- shortlist compare and print ---- */", "</style>")
    print_css = css[css.index("@media print{"):]
    assert re.search(r"body:has\(> \.prsum\) > :not\(\.prsum\)\{display:none!important\}", print_css)
    assert "color:#000!important;background:#fff!important" in print_css
    handler = between("const pr=$('#prBtn');", "window.print();")
    assert "${NOTICE}" in handler and "not advice" in handler and "${esc(SPAN)}" in handler
    assert "toLocaleDateString" in handler and "S.oaSet" in handler
    assert 'id="prBtn">Print summary</button>' in GAME
