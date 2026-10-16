"""Headless smoke tests of the Streamlit app (no browser or open port needed)."""

import pytest
from streamlit.testing.v1 import AppTest

from runway.auth import hash_password

USERS = {"tester": hash_password("Correct-Horse-1", iterations=1000)}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {"users": USERS}
    return at


def test_login_page_shows_no_credentials(app):
    app.run()
    text = " ".join(m.value for m in app.markdown) + " ".join(c.value for c in app.caption)
    assert "Sign in" in [b.label for b in app.button] or app.text_input
    assert "lecturer" not in text.lower() and "password:" not in text.lower()
    assert "user" not in app.session_state


def test_wrong_password_rejected(app):
    app.run()
    app.text_input[0].input("tester")
    app.text_input[1].input("wrong")
    app.button[0].click().run()
    assert "user" not in app.session_state
    assert any("don't match" in e.value for e in app.error)


def test_no_users_configured_fails_closed(monkeypatch):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {"users": {}}
    at.run()
    assert any("isn't set up" in e.value for e in at.error)


@pytest.mark.parametrize(
    "page", ["app_pages/home.py", "app_pages/lease_explorer.py", "app_pages/ask_runway.py",
             "app_pages/about.py", "app_pages/methodology.py"]
)
def test_every_page_renders_after_login(app, page):
    app.session_state["user"] = "tester"
    app.run()
    app.switch_page(page).run()
    assert not app.exception, app.exception
    expanders = [e.label for e in app.expander]
    assert any("IMPORTANT NOTICE" in label for label in expanders)


def test_lease_explorer_computes_submission_example(app):
    app.session_state["user"] = "tester"
    app.run()
    app.switch_page("app_pages/lease_explorer.py").run()
    values = {m.label: m.value for m in app.metric}
    assert values["CPF you can use"] == "80.9%"  # youngest 28, 58 years left
    assert values["HDB loan limit"] == "60.6%"
    assert values["Full-CPF lease"] == "67 years"


def test_ask_runway_declines_advice(app):
    app.session_state["user"] = "tester"
    app.run()
    app.switch_page("app_pages/ask_runway.py").run()
    app.chat_input[0].set_value("Should I buy a flat in Clementi?").run()
    assert not app.exception
    assert any("can't tell you whether to buy" in m.value for m in app.markdown)


def test_correct_password_signs_in(app):
    app.run()
    app.text_input[0].input("Tester")
    app.text_input[1].input("Correct-Horse-1")
    app.button[0].click().run()
    assert app.session_state["user"] == "tester"
    assert not app.exception


def test_ask_runway_offers_explorer_numbers_without_explain_click(app):
    app.session_state["user"] = "tester"
    app.run()
    app.switch_page("app_pages/lease_explorer.py").run()
    app.switch_page("app_pages/ask_runway.py").run()
    assert any("Use my Lease Explorer result" in t.label for t in app.toggle)


def test_other_buyer_under_21_is_rejected(app):
    app.session_state["user"] = "tester"
    app.run()
    app.switch_page("app_pages/lease_explorer.py").run()
    other = next(n for n in app.number_input if n.label.startswith("Other buyer"))
    other.set_value(5)
    app.button[0].click().run()
    assert any("at least 21" in e.value for e in app.error)
    assert not app.metric
