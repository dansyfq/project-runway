"""More > Insights: the admin's view of Ask Runway's documents, quality, feedback and AI use."""

import json

import pytest

from runway import insights
from tests.test_bridge import USERS, send  # noqa: F401  (fixtures below)
from runway.llm import LLM
from runway.rag import Retriever, load_chunks


@pytest.fixture(scope="module")
def index():
    return Retriever(load_chunks())


@pytest.fixture
def bot(monkeypatch):
    import runway.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_setting", lambda name, default=None: default)
    return LLM()


def test_insights_needs_the_admin_role(bot, index):
    refused = {"ok": False, "error": "Log in as an admin first."}
    assert send("insights", {}, bot, index) == refused  # a guest
    assert send("insights", {"user": "user", "role": "user"}, bot, index) == refused  # the user account: no Insights
    assert send("insights", {"user": "reviewer", "role": "full"}, bot, index) == refused  # the old role name


def test_insights_for_the_admin(bot, index, tmp_path, monkeypatch):
    import runway.bridge

    log = tmp_path / "feedback.jsonl"
    log.write_text("\n".join(json.dumps(v) for v in [
        {"rating": "up", "question": "How long can my loan be?", "lang": "en", "date": "2026-11-01"},
        {"rating": "down", "question": "Can I rent out a room?", "lang": "en", "date": "2026-11-02"},
        {"rating": "down", "question": "Can I rent out a room?", "lang": "zh", "date": "2026-11-03"},
        {"rating": "down", "question": "", "lang": "ms", "date": "2026-11-04"},  # screened out: no question kept
    ]) + "\nnot json\n")
    monkeypatch.setattr(runway.bridge, "FEEDBACK_FILE", log)
    r = send("insights", {"user": "admin", "role": "admin"}, bot, index)
    assert r["ok"]
    d = r["data"]
    assert d["corpus"]["docs"] >= 30 and d["corpus"]["passages"] == len(index.chunks) and "vector" in d["corpus"]["mode"]
    assert sum(x["passages"] for x in d["corpus"]["list"]) == len(index.chunks)
    fb = d["feedback"]
    assert (fb["total"], fb["up"], fb["down"], fb["helpful_pct"]) == (4, 1, 3, 25)
    assert fb["low_rated"] == [{"q": "Can I rent out a room?", "date": "2026-11-03"}]  # newest first, once
    assert fb["by_lang"] == {"en": 2, "zh": 1, "ms": 1}
    assert d["ai"] == {"on": False, "model": None, "calls_last_hour": d["ai"]["calls_last_hour"], "cap": 300}
    ev = d["eval"]
    assert set(ev["by_mode"]) == {"keyword", "vector", "hybrid"} and ev["checks"][0][2] >= 19


def test_feedback_summary_with_no_votes(tmp_path):
    votes, where = insights.read_votes(tmp_path / "missing.jsonl")
    assert votes == [] and where == "none yet"
    assert insights.feedback_summary([])["helpful_pct"] is None


def test_odd_vote_rows_are_not_counted():
    s = insights.feedback_summary([{"rating": "up"}, {"rating": "meh"}, "junk", {"rating": "down", "question": "x"}])
    assert (s["total"], s["up"], s["down"]) == (2, 1, 1)
