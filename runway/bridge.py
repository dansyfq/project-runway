"""Messages between the Runway interface (runway_game/index.html) and Python.

The interface sends one message at a time: {"id", "type", "payload"}. `handle` returns the reply
value; the host sends it back keyed by id. Everyone can use Runway as a guest (role "brief");
logging in as a user (role "user") shows the full About Us and How it works, and as an admin (role "admin") also
gives the admin tools: upload Ask documents and edit pages and the FAQ (runway/content.py). Roles: runway/auth.py.
Passwords, the AI and the documents stay server-side.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections.abc import MutableMapping
from pathlib import Path

from runway.auth import check_login
from runway.game_data import load_towns, recent_months, town_photo
from runway.llm import AI_BUSY, INVENTED_FIGURE, LLM, language, screen_question
from runway.rag import Chunk, Retriever

# Every screen's URL path and its name. app.py makes one page per entry; the interface (RW.PATHS) uses the same paths.
PAGES = {"": "Runway — HDB CPF age-95 checker", "map": "Map", "shortlist": "Shortlist", "trends": "Trends", "ask": "Ask",
         "more": "More", "details": "Your details", "text-size": "Text size", "about": "About Us",
         "how-it-works": "How it works", "sources": "Sources and credits", "privacy": "Privacy Policy", "terms": "Terms",
         "faq": "FAQ", "case-study": "Case study", "timeline": "Buying timeline"}
ADMIN_ONLY = {"docs", "upload_doc", "save_page", "save_faq"}  # runway/content.py; role "admin" only
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
# username -> (failed attempts, locked until). Module-level, so a page reload (a new session) can't reset it.
LOCKS: dict[str, tuple[int, float]] = {}
LOCKS_LOCK = threading.Lock()  # each session runs in its own thread
NUMBERS_NOTE = "Numbers from Runway's calculator, not the AI."
FEEDBACK_FILE = Path(__file__).resolve().parent.parent / "data" / "feedback.jsonl"
MAX_FEEDBACK_QUESTION = 300
MAX_TTS = 150  # per session, so a script can't use the server as a free speech service
MAX_VOTES = 30  # per session; a changed vote counts again
# The facts the interface's flatFacts() sends; the explanation template needs the first five.
REQUIRED_FACTS = {"Remaining lease (years)", "Youngest buyer is this old when lease ends", "Years short of age 95",
                  "CPF usable (% of Valuation Limit)", "HDB loan limit (% of price or value)"}
FACT_KEYS = REQUIRED_FACTS | {"Youngest buyer age", "Lease covers youngest buyer to age 95", "CPF can be used",
                              "Full HDB loan limit (%)", "Lease premium by town"}
WHY_QUERY = {
    True: "lease covers youngest buyer to age 95 CPF up to valuation limit",
    False: "remaining lease does not cover youngest buyer to age 95 pro-rated CPF usage valuation limit loan-to-value",
}


def load_trends() -> dict:
    """pandas costs ~0.35 s to import, so it loads on the first Trends request, not on every cold start."""
    from runway.trends import load_trends as load

    return load()


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


def situation_from(age) -> str:
    """The youngest buyer's age the user already gave the interface, so the AI needn't ask again."""
    if isinstance(age, int) and not isinstance(age, bool) and 21 <= age <= 85:
        return f"Youngest buyer age: {age}"
    return ""


def handle(msg: dict, state: MutableMapping, users: dict, bot: LLM, index: Retriever) -> dict:
    kind, payload = msg.get("type"), msg.get("payload")
    if not isinstance(kind, str):  # the browser is untrusted
        return {"ok": False, "error": "bad message"}
    if not isinstance(payload, dict):
        payload = {}

    if kind == "login":
        if not users:
            return {"ok": False, "error": "Sign-in isn't set up yet. The app owner needs to add accounts."}
        user = str(payload.get("u", ""))[:64].strip().lower()
        with LOCKS_LOCK:  # count the attempt before the slow password check, so parallel guesses can't all read 0
            attempts, locked_until = LOCKS.get(user, (0, 0.0))
            if time.time() < locked_until:
                return {"ok": False, "error": "Too many attempts. Wait a minute and try again."}
            if len(LOCKS) > 10_000:  # shortcut: forgets all counts if flooded with made-up usernames; fine for one process
                LOCKS.clear()
            attempts += 1
            LOCKS[user] = (0, time.time() + LOCKOUT_SECONDS) if attempts >= MAX_ATTEMPTS else (attempts, 0.0)
        role = check_login(user, str(payload.get("p", ""))[:256], users)  # "admin" or "user"; None if wrong
        if role:
            LOCKS.pop(user, None)
            state.update(user=user, role=role)
            return {"ok": True, "user": user, "role": role}
        return {"ok": False, "error": "That username and password don't match."}

    if kind == "logout":
        state.pop("user", None)
        state["role"] = "brief"
        state.get("replies", []).clear()  # in place: the host appends this reply to the same list
        return {"ok": True, "role": "brief"}

    if kind in ADMIN_ONLY:  # checked here, not just hidden in the interface: the browser is untrusted
        if state.get("role") != "admin":  # a logged-in "user" is refused too
            return {"ok": False, "error": "Log in as an admin first."}
        from runway import content

        if kind == "docs":
            return {"ok": True, "docs": content.list_docs()}
        if kind == "upload_doc":
            return content.add_doc(payload)
        if kind == "save_page":
            return content.save_page(str(payload.get("key", "")), payload.get("html", ""))
        return content.save_faq(payload.get("items"))

    if kind == "nav":  # the address bar follows the screen; only page names, never anything the user typed
        page = payload.get("page")
        return {"ok": True, "page": page} if isinstance(page, str) and page in PAGES else {"ok": False, "error": "unknown page"}

    if kind == "booted":
        state["data_sent"] = True
        return {"ok": True}
    if kind == "need_data":
        state.update(want_data=True, data_sent=False)
        return {"ok": True}

    if kind == "ask":
        question = str(payload.get("q", ""))[:1000]
        lang = language(payload.get("lang"))
        facts = payload.get("facts")
        if facts:  # "Why?" for one flat: explain Runway's own numbers, never new ones
            if not isinstance(facts, dict) or not REQUIRED_FACTS <= facts.keys():
                return {"ok": False, "error": "bad facts"}
            facts = {k: str(facts[k])[:60] for k in FACT_KEYS if k in facts}  # only known keys reach the AI
            sources = index.search(WHY_QUERY[facts.get("Lease covers youngest buyer to age 95") == "yes"], k=4)
            text, used_llm = bot.explain(facts, sources, lang=lang)
            return {"text": text, "sources": source_view(sources), "offline": False, "lang": lang if used_llm else "en",
                    "note": NUMBERS_NOTE if used_llm else NUMBERS_NOTE + " Written from a fixed template."}
        history = clean_history(payload.get("history"), 6)
        previous = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
        # A question that will be declined must not spend an AI call on the search (the hourly budget is shared).
        sources = [] if screen_question(question) else index.search(bot.search_query(f"{previous} {question}", lang), k=5)
        answer = bot.answer(question, sources, history=history, situation=situation_from(payload.get("age")), lang=lang)
        offline = bool(answer.error) or (not bot.available and not answer.blocked)
        why = {INVENTED_FIGURE: "used a figure not in the documents", AI_BUSY: "has reached its limit for this hour",
               None: "explainer is offline"}.get(answer.error, "service didn't respond")
        note = f"The AI {why}, so here are the official pages." if offline else None  # the text itself is neutral
        return {"text": answer.text, "sources": source_view(answer.sources), "blocked": answer.blocked,
                "offline": offline, "note": note, "lang": "en" if offline or answer.blocked else lang}

    if kind in {"trends", "towns", "town_photo"}:  # public price and town data: no login, no personal details
        try:
            if kind == "trends":
                return {"ok": True, "data": load_trends()}
            if kind == "towns":
                return {"ok": True, "towns": load_towns(), "months": recent_months()}
            photo = town_photo(payload.get("id"))
            return {"ok": True, **photo} if photo else {"ok": False, "error": "no photo"}
        except Exception as exc:  # say what failed, in the log and on the page, so it can be fixed fast
            traceback.print_exc()
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    if kind == "price_check":  # one public sale from the map (town, street, type, size, lease, price), nothing the user typed
        try:
            from runway.price_check import price_check  # pandas loads on first use, as for Trends

            return {"ok": True, **price_check(payload)}
        except ValueError:
            return {"ok": False, "error": "bad flat"}
        except Exception as exc:  # as for trends: say what failed, in the log and on the page
            traceback.print_exc()
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    if kind == "tts":  # read-aloud in the Singapore voice pack (runway/voicepack.py); only text the page already shows
        n = state.get("tts", 0)
        if n >= MAX_TTS:
            return {"ok": False, "error": "too many read-alouds"}
        state["tts"] = n + 1
        from runway import voicepack

        audio = voicepack.speak(str(payload.get("text", "")), language(payload.get("lang")))
        return {"ok": True, "audio": audio} if audio else {"ok": False, "error": "voice unavailable"}

    if kind == "summary":
        return {"text": bot.summarise(clean_history(payload.get("history"), 12))}

    if kind == "feedback":  # Helpful / Not helpful on one answer: no AI call, no search
        rating, question = payload.get("rating"), payload.get("q", "")
        if rating not in ("up", "down") or not isinstance(question, str) or len(question) > MAX_FEEDBACK_QUESTION:
            return {"ok": False, "error": "bad feedback"}
        votes = state.get("votes", 0)
        if votes >= MAX_VOTES:
            return {"ok": False, "error": "too many votes"}
        state["votes"] = votes + 1
        question = question.strip()
        # Shaped like an eval/questions.json case; the question is kept only if screening passes it (no NRIC, phone, email).
        line = json.dumps({"type": "retrieval", "question": "" if screen_question(question) else question,
                           "expect_docs": [], "expect_words": [], "rating": rating,
                           "lang": language(payload.get("lang")), "date": time.strftime("%Y-%m-%d")}, ensure_ascii=False)
        print(f"[runway] feedback {line}", flush=True)  # Streamlit Community Cloud has no lasting disk: the log is the record
        try:
            with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        from runway import store

        if store.db_enabled():  # the lasting record (Neon); the log line above stays the fallback
            try:
                store.add_vote(json.loads(line))
            except Exception as exc:
                print(f"[runway] saving the vote to the database failed: {type(exc).__name__}: {exc}", flush=True)
        return {"ok": True}

    return {"ok": False, "error": f"unknown message: {kind}"}
