"""The Streamlit host and the interface file."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from runway.cpf_rules import cpf_share, flat_money
from runway.game_data import load_game_data

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
DEMO_WORDS = ("demo sign-in", "mockup", "scripted", "try it now", "live app", "runway2026")


def test_host_runs_for_a_guest():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert "user" not in at.session_state


@pytest.mark.parametrize("msg", [["not", "a", "dict"], "text", {"id": ["unhashable"], "type": "ask"}])
def test_host_ignores_malformed_messages(monkeypatch, msg):
    import streamlit.components.v1 as components

    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: msg)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception


def test_host_always_replies_even_if_handle_fails(monkeypatch):
    """No reply means the interface waits 90 s; any unexpected error must still answer the message."""
    import streamlit.components.v1 as components

    import runway.bridge

    def boom(*_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: {"id": "m1", "type": "ask"})
    monkeypatch.setattr(runway.bridge, "handle", boom)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1] == {"id": "m1", "value": {"ok": False, "error": "Something went wrong. Try again."}}


def test_game_data_has_every_town_with_a_photo_and_credit():
    data = load_game_data()
    towns = {t["id"] for t in data["M"]["towns"]}
    assert len(towns) == 26 and set(data["PHOTOS"]) == towns
    assert all("Wikimedia Commons" in p["credit"] and p["img"].startswith("data:image/jpeg") for p in data["PHOTOS"].values())
    assert {"roads", "stops", "am"} <= set(data["F"])


def test_interface_has_no_mockup_wording_or_built_in_accounts():
    visible = re.sub(r"/\*.*?\*/", "", GAME, flags=re.S).lower()
    for word in DEMO_WORDS:
        assert word not in visible, word
    assert "USERS=" not in GAME


def test_landing_page_has_required_notice_and_entry_points():
    assert GAME.count("NOT intended for real-world usage") >= 2  # landing page (main page) and About Us
    assert 'id="scrLanding"' in GAME and 'data-go="map"' in GAME and "data-login" in GAME
    assert 'id="loginOverlay"' in GAME


@pytest.mark.skipif(not (shutil.which("node") or Path.home().joinpath(".local/bin/node").exists()),
                    reason="needs Node.js")
def test_interface_calculator_matches_python_rules(tmp_path):
    """The map's in-browser calculator must give the same numbers as runway/cpf_rules.py."""
    calc = GAME[GAME.index("function calc(price, lease){"):GAME.index("const VTXT = ")]
    landing = GAME[GAME.index("function landingShare(age, lease){"):GAME.index("window.landingShare")]
    cases = [(p, lease, age, avg) for p in (300_000, 550_000) for lease in (15, 20, 20.5, 21, 45, 58, 58.75, 65, 66.6, 74.99, 75, 95)
             for age, avg in ((21, 21), (25, 25), (28, 30), (45, 50), (70, 70), (74, 74))]
    script = (f"let S={{age:0,avg:0,oa:0,oaSet:false}};\n{calc}\n{landing}\n"
              f"const out={json.dumps(cases)}.map(([p,l,a,v])=>{{S.age=a;S.avg=v;const r=calc(p,l);"
              f"return [r.cap,r.loan,r.tenure,r.monthly,r.cashLife,landingShare(a,l)];}});\n"
              f"console.log(JSON.stringify(out));")
    js = tmp_path / "calc.js"
    js.write_text(script)
    node = shutil.which("node") or str(Path.home() / ".local/bin/node")
    results = json.loads(subprocess.run([node, str(js)], capture_output=True, text=True, check=True).stdout)
    for (price, lease, age, avg), (cap, loan, tenure, monthly, cash, share) in zip(cases, results):
        assert share == pytest.approx(cpf_share(age, lease)), ("landing", lease, age)
        m = flat_money(price, lease, [age, 2 * avg - age], 0)
        assert cap == pytest.approx(m.cpf_cap), (price, lease, age)
        assert loan == pytest.approx(m.loan_max), (price, lease, age)
        assert tenure == pytest.approx(m.tenure), (price, lease, age)
        assert monthly == pytest.approx(m.monthly, rel=1e-6), (price, lease, age)
        assert cash == pytest.approx(m.cash_on_top), (price, lease, age)
