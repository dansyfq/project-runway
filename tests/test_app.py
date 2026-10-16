"""The Streamlit host and the interface file."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from runway.cpf_rules import flat_money
from runway.game_data import load_game_data

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
DEMO_WORDS = ("demo", "mockup", "scripted", "prototype", "try it now", "live app")


def test_host_runs_and_withholds_data_before_sign_in():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert "user" not in at.session_state


def test_host_sends_data_once_signed_in():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["user"], at.session_state["role"] = "demo", "brief"
    at.run()
    assert not at.exception


def test_game_data_has_every_town_with_a_photo_and_credit():
    data = load_game_data()
    towns = {t["id"] for t in data["M"]["towns"]}
    assert len(towns) == 26 and set(data["PHOTOS"]) == towns
    assert all("Wikimedia Commons" in p["credit"] and p["img"].startswith("data:image/jpeg") for p in data["PHOTOS"].values())
    assert {"roads", "stops", "am"} <= set(data["F"])


def test_interface_has_no_demo_wording_or_built_in_accounts():
    notice = GAME[GAME.index("const NOTICE = `"):GAME.index("`;", GAME.index("const NOTICE = `"))]  # required, word for word
    visible = re.sub(r"/\*.*?\*/", "", GAME.replace(notice, ""), flags=re.S).lower()
    for word in DEMO_WORDS:
        assert word not in visible, word
    assert "runway2026" not in GAME and "USERS=" not in GAME
    assert "IMPORTANT NOTICE" in GAME and "NOT intended for real-world usage" in GAME


@pytest.mark.skipif(not (shutil.which("node") or Path.home().joinpath(".local/bin/node").exists()),
                    reason="needs Node.js")
def test_interface_calculator_matches_python_rules(tmp_path):
    """The map's in-browser calculator must give the same numbers as runway/cpf_rules.py."""
    calc = GAME[GAME.index("function calc(price, lease){"):GAME.index("const VTXT = ")]
    cases = [(p, lease, age, avg) for p in (300_000, 550_000) for lease in (15, 20, 21, 45, 58, 65, 75, 95)
             for age, avg in ((25, 25), (28, 30), (45, 50), (70, 70))]
    script = (f"let S={{age:0,avg:0,oa:0,oaSet:false}};\n{calc}\n"
              f"const out={json.dumps(cases)}.map(([p,l,a,v])=>{{S.age=a;S.avg=v;const r=calc(p,l);"
              f"return [r.cap,r.loan,r.tenure,r.monthly,r.cashLife];}});\nconsole.log(JSON.stringify(out));")
    js = tmp_path / "calc.js"
    js.write_text(script)
    node = shutil.which("node") or str(Path.home() / ".local/bin/node")
    results = json.loads(subprocess.run([node, str(js)], capture_output=True, text=True, check=True).stdout)
    for (price, lease, age, avg), (cap, loan, tenure, monthly, cash) in zip(cases, results):
        m = flat_money(price, lease, [age, 2 * avg - age], 0)
        assert cap == pytest.approx(m.cpf_cap), (price, lease, age)
        assert loan == pytest.approx(m.loan_max), (price, lease, age)
        assert tenure == pytest.approx(m.tenure), (price, lease, age)
        assert monthly == pytest.approx(m.monthly, rel=1e-6), (price, lease, age)
        assert cash == pytest.approx(m.cash_on_top), (price, lease, age)
