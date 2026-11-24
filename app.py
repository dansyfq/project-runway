"""Runway: how much lease you have left.

The interface (runway_game/index.html, built from the approved design) runs full-window as a
Streamlit component: landing page, map game, Ask and More. Visitors use it as guests; the `user` and
`admin` accounts see the full About Us and How it works, and `admin` also manages documents and pages.
Python checks logins and answers questions from the official documents (runway/bridge.py).
Run locally with:  streamlit run app.py
"""

import hashlib
import sys
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
# Streamlit Community Cloud keeps the process running across a redeploy, so the runway.* modules imported by an earlier
# run would stay in memory and keep answering with the old code (only a reboot cleared them). The newest file time
# changes on a redeploy: forget the old modules, so the imports below load the new ones, and key the caches on it.
CODE = max(p.stat().st_mtime for p in (HERE / "runway").glob("*.py"))
_seen = getattr(st, "_runway_code", None)
if _seen is not None and _seen != CODE:  # not on the first run: nothing is stale yet
    for _name in [n for n in sys.modules if n == "runway" or n.startswith("runway.")]:
        del sys.modules[_name]
st._runway_code = CODE

from runway.auth import load_users  # noqa: E402  (after the module purge above)
from runway.bridge import PAGES, handle
from runway.config import get_setting
from runway.content import load_content
from runway.game_data import load_game_data
from runway.llm import LLM
from runway.rag import Retriever, load_chunks

# One URL per screen. The pages are empty: the one interface below stays mounted and is told which page is open.
pages = {path: st.Page(lambda: None, title=f"{name} · Runway" if path else name, url_path=path, default=not path)
         for path, name in PAGES.items()}
pg = st.navigation(list(pages.values()), position="hidden")
st.set_page_config(page_title=pg.title, page_icon=str(HERE / "runway_game" / "assets" / "favicon.svg"), layout="wide",
                   initial_sidebar_state="collapsed")
pg.run()
st.markdown(
    """<style>
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stStatusWidget"], footer {display: none !important;}
    [data-testid="stMainBlockContainer"], .block-container {padding: 0 !important; max-width: 100% !important;}
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {padding: 0 !important; overflow: hidden;}
    [data-testid="stVerticalBlock"] {gap: 0 !important;}
    iframe {display: block; border: 0; width: 100vw; height: 100dvh !important;}
    html, body {overflow: hidden;}
    /* Streamlit's own "Page not found" dialog for an unknown address: its box sits behind the full-window interface while
       its backdrop blocks every click. Runway shows its own notice instead (missing_page); the app uses no other dialog. */
    [data-testid="stDialog"] {display: none !important;}
    </style>""",
    unsafe_allow_html=True,
)

runway_game = components.declare_component("runway_game", path=str(HERE / "runway_game"))


@st.cache_data(show_spinner=False)
def game_data() -> dict:
    return load_game_data()


# CODE (top of this file) is part of each cache key, so a redeploy builds new objects instead of reusing old-code ones.


@st.cache_resource(show_spinner=False, max_entries=1)
def llm(code: float, key: str) -> LLM:
    return LLM()


def key_id() -> str:
    """Saving a new API key in Secrets doesn't restart the process, so a client built without one would stay "offline".
    The key's hash is part of the cache key: adding or changing the key builds a new client (the key itself isn't cached)."""
    key = get_setting("ANTHROPIC_API_KEY") or ""
    return hashlib.sha256(key.encode()).hexdigest()[:12] if key else ""


@st.cache_resource(show_spinner=False, max_entries=1)
def retriever(code: float) -> Retriever:
    return Retriever(load_chunks())


def switch_page(page) -> None:
    """st.switch_page without its query-parameter reset. That reset makes the browser record the current address
    a second time, so every page change would need two presses of Back (Streamlit 1.58)."""
    try:
        from streamlit.runtime.scriptrunner import RerunData, get_script_run_ctx

        ctx = get_script_run_ctx()
        ctx.script_requests.request_rerun(RerunData(  # the same request st.switch_page makes
            query_string=ctx.query_string, page_script_hash=page._script_hash,
            cached_message_hashes=ctx.cached_message_hashes, context_info=ctx.context_info))
    except Exception:  # Streamlit internals changed: the public call still works, with the extra history entry
        st.switch_page(page)
    st.empty()  # hands control to the rerun just requested, as st.switch_page does


def configured_users() -> dict[str, tuple[str, str]]:
    """The built-in admin and user accounts, then any in Secrets [auth.users] (same name: Secrets wins). runway/auth.py"""
    try:
        secret = st.secrets["auth"]["users"]
    except (KeyError, FileNotFoundError):
        secret = {}
    return load_users(secret, get_setting("BUILTIN_ACCOUNTS", "admin,user"))


state = st.session_state
replies = state.setdefault("replies", [])
handled = state.setdefault("handled", set())
me = {"user": state.get("user"), "role": state.get("role", "brief")}
# The landing page shows at once; the map data (2.5 MB) follows when the page asks for it.
data = None
if state.get("want_data") and not state.get("data_sent") and state.get("pushes", 0) < 8:
    data = game_data()
    state["pushes"] = state.get("pushes", 0) + 1  # a session needs it once; the cap stops a script asking in a loop



def missing_page() -> bool:
    """An unknown address such as /nope: Streamlit runs the home page and changes the address to /, but the first run
    still sees the address that was asked for (st.context.url). Community Cloud serves the app under /~/+/."""
    try:
        asked = [p for p in urlparse(st.context.url).path.split("/") if p not in ("", "~", "+")]
    except Exception:  # no context (tests) or Streamlit changed: no notice rather than a wrong one
        return False
    return pg.url_path == "" and bool(asked) and asked[-1] not in PAGES


msg = runway_game(me=me, data=data, content=load_content(), replies=replies[-5:], page=pg.url_path, missing=missing_page(), key="runway", default=None)

if isinstance(msg, dict) and isinstance(msg.get("id"), str) and len(msg["id"]) <= 64 and msg["id"] not in handled:  # untrusted
    if len(handled) > 500:  # only the latest message is ever delivered again, so old ids can go
        handled.clear()
    handled.add(msg["id"])
    try:
        reply = handle(msg, state, configured_users(), llm(CODE, key_id()), retriever(CODE))
    except Exception as exc:  # always answer: without a reply the interface waits 90 s
        print(f"[runway] {str(msg.get('type'))[:40]!r} failed: {type(exc).__name__}: {exc}")
        reply = {"ok": False, "error": "Something went wrong. Try again."}
    if msg.get("type") == "upload_doc" and reply.get("ok"):
        retriever.clear()  # the next question searches the new document too
    for r in replies:  # audio was delivered once; resending it with every rerun would be megabytes
        r["value"].pop("audio", None)
    replies.append({"id": msg["id"], "value": reply})
    del replies[:-5]  # only the last five are ever sent; in place, so logout's clear() still reaches this list
    if msg.get("type") == "nav" and reply.get("ok") and reply["page"] != pg.url_path:
        switch_page(pages[reply["page"]])
    st.rerun()
