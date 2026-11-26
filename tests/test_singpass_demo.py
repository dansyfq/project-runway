"""The Singpass demo (a mock-up): the made-up people, the age worked out from a date of birth, and what each
ticked item fills in. Runs the page's own code in Node, like the other interface tests."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node") or str(Path.home() / ".local/bin/node")
needs_node = pytest.mark.skipif(not (shutil.which("node") or Path(NODE).exists()), reason="needs Node.js")

# Today in the tests is fixed, so the ages do not drift as the calendar moves on.
TODAY = "new Date(2026, 10, 18)"  # 18 November 2026


def run(tmp_path, expression):
    code = GAME[GAME.index("const SPD=["):GAME.index("function spdApply(")]
    js = tmp_path / "spd.js"
    js.write_text(f"const exact = n => '$' + Math.round(n).toLocaleString('en-SG');\n{code}\n"
                  f"console.log(JSON.stringify({expression}));")
    return json.loads(subprocess.run([NODE, str(js)], capture_output=True, text=True, check=True).stdout)


@needs_node
def test_age_is_worked_out_from_the_date_of_birth(tmp_path):
    cases = {  # born 2 August 1990: 35 the day before the birthday, 36 on it
        "spdAge('1990-08-02', new Date(2026, 7, 1))": 35,
        "spdAge('1990-08-02', new Date(2026, 7, 2))": 36,
        "spdAge('1990-08-02', " + TODAY + ")": 36,
        "spdAge('1998-03-14', " + TODAY + ")": 28,
        "spdAge('1982-11-27', " + TODAY + ")": 43,  # birthday still nine days away
    }
    got = run(tmp_path, "[" + ",".join(cases) + "]")
    assert got == list(cases.values())


@needs_node
def test_every_ticked_item_fills_in_its_own_field(tmp_path):
    got = run(tmp_path, "SPD.map(p => spdFill(p, new Set(SPD_ITEMS.map(i => i.k)), " + TODAY + "))")
    a, b, c = got
    assert a["set"] == {"age": 28, "oa": 38500, "oaSet": True, "inc": 5200, "hh": "family", "first": "first", "cit": "sc"}
    assert b["set"] == {"age": 36, "oa": 142000, "oaSet": True, "inc": 7400, "hh": "single", "first": "first", "cit": "sc"}
    assert c["set"] == {"age": 43, "oa": 186000, "oaSet": True, "inc": 9800, "hh": "family", "first": "no", "cit": "sc"}
    assert [k for k, _ in a["got"]] == ["Youngest buyer", "CPF Ordinary Account", "Income a month", "Buying as",
                                         "Housing history", "Citizenship"]
    assert dict(c["got"])["Housing history"] == "Has owned an HDB flat before"


@needs_node
def test_unticked_items_are_left_alone(tmp_path):
    only_oa, nothing, no_income = run(tmp_path, "[spdFill(SPD[1], new Set(['oa']), " + TODAY + "),"
                                                " spdFill(SPD[1], new Set(), " + TODAY + "),"
                                                " spdFill(SPD[1], new Set(SPD_ITEMS.map(i => i.k).filter(k => k !== 'inc')), " + TODAY + ")]")
    assert only_oa["set"] == {"oa": 142000, "oaSet": True}
    assert nothing == {"set": {}, "got": []}
    assert "inc" not in no_income["set"] and no_income["set"]["age"] == 36


@needs_node
def test_a_single_under_35_is_not_given_the_singles_scheme(tmp_path):
    got = run(tmp_path, "spdFill({...SPD[1], dob: '1999-01-01'}, new Set(['marital']), " + TODAY + ")")
    assert got["set"] == {"hh": ""}
    assert dict(got["got"])["Buying as"].startswith("Not given")


@needs_node
def test_the_demo_people_are_made_up_and_carry_no_identity(tmp_path):
    people = run(tmp_path, "SPD")
    assert [p["label"] for p in people] == ["Demo person A", "Demo person B", "Demo person C"]
    assert len({p["id"] for p in people}) == 3
    assert not any(k in p for p in people for k in ("name", "nric", "uin", "address", "phone", "email"))
    # the consent list never offers what the app promises not to ask for
    wanted = " ".join(i["t"].lower() for i in run(tmp_path, "SPD_ITEMS"))
    for word in ("name", "nric", "address", "phone", "email"):
        assert word not in wanted


def test_the_demo_says_it_is_not_singpass():
    assert "Demonstration only." in GAME
    assert "not connected to it" in GAME and "It is not connected to Singpass." in GAME


def test_the_demo_is_open_to_everyone():
    """Anyone can use the labelled mock-up: the entry card does not depend on the reviewer login (FULL())."""
    card = GAME[GAME.index("const spdCard="):GAME.index("function spdAge(")]
    assert "FULL()" not in card
    # the two screens that show the card still cope with it being absent
    assert "if(spd) spd.onclick=openSingpassDemo" in GAME
    assert "else if(!$('#scrOnb').hidden) renderOnb();" in GAME  # logging in on the age step refreshes the card


def test_the_cpf_page_offers_the_demo_login_until_it_has_been_used():
    """The Map set-up's CPF page shows the Singpass demo card like the age page does, and hides it once the demo filled details in."""
    cpf_page = GAME[GAME.index("<h1>About how much CPF do you have?</h1>"):GAME.index("Which town first?")]
    assert "${S.spd?'':spdCard()}" in cpf_page
    assert "if(spd2) spd2.onclick=openSingpassDemo" in cpf_page
