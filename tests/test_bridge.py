"""Messages from the interface: guest use, reviewer login, ask, why, summary."""

import pytest

from runway.auth import hash_password
from runway.bridge import handle
from runway.llm import LLM, Answer
from runway.rag import Retriever, load_chunks

USERS = {"reviewer": hash_password("Review-pass-1", iterations=1000)}


@pytest.fixture(scope="module")
def index():
    return Retriever(load_chunks())


@pytest.fixture(autouse=True)
def no_lockouts():
    import runway.bridge

    runway.bridge.LOCKS.clear()  # the lockout is shared by every session in the process


@pytest.fixture
def bot(monkeypatch):
    import runway.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_setting", lambda name, default=None: default)
    return LLM()  # no API key: offline behaviour


def send(kind, state, bot, index, **payload):
    return handle({"id": "x", "type": kind, "payload": payload}, state, USERS, bot, index)


def test_reviewer_login_gives_full_view(bot, index):
    state = {}
    assert send("login", state, bot, index, u=" Reviewer ", p="Review-pass-1") == {
        "ok": True, "user": "reviewer", "role": "full"}
    assert state["user"] == "reviewer" and state["role"] == "full"


def test_wrong_password_and_lockout(bot, index):
    state = {}
    for _ in range(5):
        assert send("login", state, bot, index, u="reviewer", p="nope")["ok"] is False
    assert "Too many attempts" in send("login", state, bot, index, u="reviewer", p="Review-pass-1")["error"]
    assert "user" not in state


def test_lockout_survives_a_page_reload(bot, index):
    """A reload starts a new Streamlit session; the lockout must follow the username, not the session."""
    for _ in range(5):
        send("login", {}, bot, index, u="reviewer", p="nope")
    assert "Too many attempts" in send("login", {}, bot, index, u="reviewer", p="Review-pass-1")["error"]


def test_no_accounts_fails_closed(bot, index):
    reply = handle({"id": "x", "type": "login", "payload": {"u": "a", "p": "b"}}, {}, {}, bot, index)
    assert reply["ok"] is False and "isn't set up" in reply["error"]


def test_guests_can_ask_without_logging_in(bot, index):
    reply = send("ask", {}, bot, index, q="What is the HDB loan limit?", history=[])
    assert reply["sources"]


def test_data_flags_and_logout(bot, index):
    state = {"user": "reviewer", "role": "full"}
    send("booted", state, bot, index)
    assert state["data_sent"] is True
    send("need_data", state, bot, index)
    assert state["data_sent"] is False and state["want_data"] is True
    assert send("logout", state, bot, index) == {"ok": True, "role": "brief"}
    assert "user" not in state and state["role"] == "brief"


def test_ask_offline_returns_official_passages(bot, index):
    reply = send("ask", {}, bot, index, q="How long is the HFE letter valid?", history=[])
    assert reply["offline"] is True and reply["sources"]
    assert all(s["url"].startswith("https://") for s in reply["sources"])


def test_ask_blocks_nric(bot, index):
    reply = send("ask", {}, bot, index, q="My NRIC is S1234567D, can I use CPF?")
    assert reply["blocked"] == "personal" and reply["sources"] == []


def test_why_uses_only_calculator_numbers(bot, index):
    facts = {"Youngest buyer age": "28", "Remaining lease (years)": "58",
             "Youngest buyer is this old when lease ends": "86", "Lease covers youngest buyer to age 95": "no",
             "Years short of age 95": "9", "CPF can be used": "yes", "CPF usable (% of Valuation Limit)": "80.9",
             "HDB loan limit (% of price or value)": "60.6", "Full HDB loan limit (%)": "75"}
    reply = send("ask", {}, bot, index, q="Why is my CPF cut?", facts=facts)
    assert "80.9%" in reply["text"] and "9 years before age 95" in reply["text"]
    assert reply["note"].startswith("Numbers from Runway's calculator")


def test_summary_offline(bot, index):
    history = [{"role": "user", "content": "Is my HDB loan cut too?"}, {"role": "assistant", "content": "Yes."}]
from runway.bridge import handle
from runway.llm import LLM, Answer
