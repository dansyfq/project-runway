"""Headless smoke tests of the Streamlit app (no browser or open port needed)."""

import pytest
from streamlit.testing.v1 import AppTest

from runway.auth import hash_password
from runway.map_data import blocks, load_sales

USERS = {"tester": hash_password("Correct-Horse-1", iterations=1000)}
DETAILS = {"youngest": 28, "other_age": 30, "cpf_oa": 100_000, "town": "CLEMENTI"}
PAGES = ["app_pages/map.py", "app_pages/shortlist.py", "app_pages/ask_runway.py", "app_pages/details.py",
         "app_pages/about.py", "app_pages/methodology.py"]
DEMO_WORDS = ("demo", "prototype", "educational", "learning project")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {"users": USERS}
    return at


def signed_in(app, details=True):
    app.session_state["user"] = "tester"
    if details:
        app.session_state["details"] = dict(DETAILS)
    return app


def page_text(app) -> str:
    parts = [m.value for m in app.markdown] + [c.value for c in app.caption] + [t.value for t in app.title]
    return " ".join(parts).lower()


def test_login_page_shows_no_credentials_or_demo_wording(app):
    app.run()
    text = page_text(app)
    assert app.text_input and "user" not in app.session_state
    assert "lecturer" not in text and "password:" not in text
    assert not any(word in text for word in DEMO_WORDS)


def test_wrong_password_rejected(app):
    app.run()
    app.text_input[0].input("tester")
    app.text_input[1].input("wrong")
    app.button[0].click().run()
    assert "user" not in app.session_state
    assert any("don't match" in e.value for e in app.error)


def test_correct_password_signs_in(app):
    app.run()
    app.text_input[0].input("Tester")
    app.text_input[1].input("Correct-Horse-1")
    app.button[0].click().run()
    assert app.session_state["user"] == "tester"
    assert not app.exception


def test_no_users_configured_fails_closed():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {"users": {}}
    at.run()
    assert any("isn't set up" in e.value for e in at.error)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(app, page):
    signed_in(app).run()
    app.switch_page(page).run()
    assert not app.exception, app.exception


@pytest.mark.parametrize("page", [p for p in PAGES if not p.endswith("about.py")])
def test_prototype_wording_only_on_about(app, page):
    signed_in(app).run()
    app.switch_page(page).run()
    assert not any(word in page_text(app) for word in DEMO_WORDS), page


def test_about_has_required_disclaimer(app):
    signed_in(app).run()
    app.switch_page("app_pages/about.py").run()
    text = " ".join(m.value for m in app.markdown)
    assert "IMPORTANT NOTICE" in text and "NOT intended for real-world usage" in text


def test_map_asks_for_details_first(app):
    signed_in(app, details=False).run()
    assert any("Before you start" in t.value for t in app.title)


def test_flat_panel_shows_verdict_for_selected_block(app):
    sales = load_sales()
    rows = blocks(sales[sales["town"] == "CLEMENTI"], 28)
    short = rows[rows["verdict"] == "part"].iloc[0]
    signed_in(app)
    app.session_state["blocks_town"] = "CLEMENTI"
    app.session_state["selected_block"] = short["block_id"]
    app.run()
    assert not app.exception, app.exception
    html = " ".join(m.value for m in app.markdown)
    assert "CPF you can use" in html and "Cash you need" in html
    assert "CPF: part only" in html or "CPF: full use" in html
    assert "your CPF use is reduced" in html or "lasts past age 95" in html
    assert app.session_state["explorer_facts"]["Youngest buyer age"] == "28"


def test_shortlist_offers_csv(app):
    sale = load_sales().iloc[0].to_dict()
    signed_in(app)
    app.session_state["shortlist"] = [sale]
    app.run()
    app.switch_page("app_pages/shortlist.py").run()
    assert not app.exception
    assert any("1 of 26" in m.value for m in app.markdown)


def test_ask_runway_declines_advice(app):
    signed_in(app).run()
    app.switch_page("app_pages/ask_runway.py").run()
    app.chat_input[0].set_value("Should I buy a flat in Clementi?").run()
    assert not app.exception
    assert any("can't tell you whether to buy" in m.value for m in app.markdown)


def test_ask_runway_offers_the_flat_being_viewed(app):
    signed_in(app)
    app.session_state["explorer_facts"] = {"Youngest buyer age": "28", "Remaining lease (years)": "58"}
    app.run()
    app.switch_page("app_pages/ask_runway.py").run()
    assert any("Use the flat I'm looking at" in t.label for t in app.toggle)


def test_details_rejects_other_buyer_under_21(app):
    signed_in(app).run()
    app.switch_page("app_pages/details.py").run()
    other = next(n for n in app.number_input if n.label.startswith("Other buyer"))
    other.set_value(5).run()
    assert any("at least 21" in e.value for e in app.error)
