"""Messages between the Runway interface (runway_game/index.html) and Python.

The interface sends one message at a time: {"id", "type", "payload"}. `handle` returns the reply
value; the host sends it back keyed by id. Everyone can use Runway as a guest (the "demo" view);
logging in gives the reviewer view (full About Us and How it works). Passwords, the AI and the
documents stay server-side.
"""

from __future__ import annotations

import time
from collections.abc import MutableMapping

from runway.auth import check_login
from runway.llm import INVENTED_FIGURE, LLM, screen_question
from runway.rag import Chunk, Retriever

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
NUMBERS_NOTE = "Numbers from Runway's calculator, not the AI."
# The facts the interface's flatFacts() sends; the explanation template needs the first five.
REQUIRED_FACTS = {"Remaining lease (years)", "Youngest buyer is this old when lease ends", "Years short of age 95",
                  "CPF usable (% of Valuation Limit)", "HDB loan limit (% of price or value)"}
FACT_KEYS = REQUIRED_FACTS | {"Youngest buyer age", "Lease covers youngest buyer to age 95", "CPF can be used",
                              "Full HDB loan limit (%)", "Lease premium by town"}
WHY_QUERY = {
    True: "lease covers youngest buyer to age 95 CPF up to valuation limit",
    False: "remaining lease does not cover youngest buyer to age 95 pro-rated CPF usage valuation limit loan-to-value",
}


def source_view(chunks: list[Chunk]) -> list[dict]:
    return [{"title": c.title, "publisher": c.publisher, "url": c.url, "heading": c.heading,
             "text": c.text[:600]} for c in chunks]


def clean_history(raw, n: int) -> list[dict]:
    """Chat turns sent by the browser: keep the last n well-formed user/assistant turns, trimmed.
    Turns that were declined (NRIC/phone, injection) stay in the browser's chat, so drop them here."""
    turns = raw[-n:] if isinstance(raw, list) else []
    turns = [{"role": h["role"], "content": str(h.get("content", ""))[:2000]}
             for h in turns if isinstance(h, dict) and h.get("role") in {"user", "assistant"}]
    return [h for h in turns if screen_question(h["content"]) not in {"personal", "injection"}]


def handle(msg: dict, state: MutableMapping, users: dict[str, str], bot: LLM, index: Retriever) -> dict:
    kind, payload = msg.get("type"), msg.get("payload")
    if not isinstance(payload, dict):  # the browser is untrusted
        payload = {}

    if kind == "login":
        if not users:
            return {"ok": False, "error": "Sign-in isn't set up yet. The app owner needs to add accounts."}
        if time.time() < state.get("locked_until", 0):
            return {"ok": False, "error": "Too many attempts. Wait a minute and try again."}
        user = str(payload.get("u", "")).strip().lower()
        if check_login(user, str(payload.get("p", "")), users):
            state.update(user=user, role="full", attempts=0)
            return {"ok": True, "user": user, "role": "full"}
        state["attempts"] = state.get("attempts", 0) + 1
        if state["attempts"] >= MAX_ATTEMPTS:
            state.update(locked_until=time.time() + LOCKOUT_SECONDS, attempts=0)
        return {"ok": False, "error": "That username and password don't match."}

    if kind == "logout":
        state.pop("user", None)
        state["role"] = "brief"
        state.get("replies", []).clear()  # in place: the host appends this reply to the same list
        return {"ok": True, "role": "brief"}

    if kind == "booted":
        state["data_sent"] = True
        return {"ok": True}
    if kind == "need_data":
        state.update(want_data=True, data_sent=False)
        return {"ok": True}

    if kind == "ask":
        question = str(payload.get("q", ""))[:1000]
        facts = payload.get("facts")
        if facts:  # "Why?" for one flat: explain Runway's own numbers, never new ones
            if not isinstance(facts, dict) or not REQUIRED_FACTS <= facts.keys():
                return {"ok": False, "error": "bad facts"}
            facts = {k: str(facts[k])[:60] for k in FACT_KEYS if k in facts}  # only known keys reach the AI
            sources = index.search(WHY_QUERY[facts.get("Lease covers youngest buyer to age 95") == "yes"], k=4)
            text, used_llm = bot.explain(facts, sources)
            return {"text": text, "sources": source_view(sources), "offline": False,
                    "note": NUMBERS_NOTE if used_llm else NUMBERS_NOTE + " Written from a fixed template."}
        history = clean_history(payload.get("history"), 6)
        previous = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
        sources = index.search(f"{previous} {question}", k=5)
        answer = bot.answer(question, sources, history=history)
        why = "used a figure not in the documents" if answer.error == INVENTED_FIGURE else "service didn't respond"
        note = f"The AI {why}, so here are the official passages." if answer.error else None
        offline = bool(answer.error) or (not bot.available and not answer.blocked)
        return {"text": answer.text, "sources": source_view(answer.sources), "blocked": answer.blocked,
                "offline": offline, "note": note}

    if kind == "summary":
        return {"text": bot.summarise(clean_history(payload.get("history"), 12))}

    return {"ok": False, "error": f"unknown message: {kind}"}
