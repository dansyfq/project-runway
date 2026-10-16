"""Runway: how much lease you have left.

The interface (runway_game/index.html, built from the approved design) runs full-window as a
Streamlit component: landing page, map game, Ask and More. Visitors use it as guests; reviewers
can log in for the full About Us and How it works. Python checks logins and answers questions
from the official documents (runway/bridge.py).
Run locally with:  streamlit run app.py
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from runway.bridge import handle
from runway.game_data import load_game_data
from runway.llm import LLM
from runway.rag import Retriever, load_chunks

st.set_page_config(page_title="Runway", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """<style>
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stStatusWidget"], footer {display: none !important;}
    [data-testid="stMainBlockContainer"], .block-container {padding: 0 !important; max-width: 100% !important;}
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {padding: 0 !important; overflow: hidden;}
    [data-testid="stVerticalBlock"] {gap: 0 !important;}
    iframe {display: block; border: 0; width: 100vw; height: 100dvh !important;}
    html, body {overflow: hidden;}
    </style>""",
    unsafe_allow_html=True,
)

runway_game = components.declare_component("runway_game", path=str(Path(__file__).parent / "runway_game"))


@st.cache_data(show_spinner=False)
def game_data() -> dict:
    return load_game_data()


@st.cache_resource(show_spinner=False)
def llm() -> LLM:
    return LLM()


@st.cache_resource(show_spinner=False)
def retriever() -> Retriever:
    chunks, bot = load_chunks(), llm()
    if bot.available:
        try:
            return Retriever(chunks, embed=bot.embed)
        except Exception as exc:  # embeddings are an enhancement; keyword search still works
            print(f"[runway] embeddings failed, using keyword search: {type(exc).__name__}: {exc}")
    return Retriever(chunks)


def configured_users() -> dict[str, str]:
    try:
        return {k.lower(): v for k, v in st.secrets["auth"]["users"].items()}
    except (KeyError, FileNotFoundError):
        return {}


state = st.session_state
replies = state.setdefault("replies", [])
handled = state.setdefault("handled", set())
me = {"user": state.get("user"), "role": state.get("role", "brief")}
# The landing page shows at once; the map data (2.5 MB) follows when the page asks for it.
data = game_data() if state.get("want_data") and not state.get("data_sent") else None

msg = runway_game(me=me, data=data, replies=replies[-5:], key="runway", default=None)

if isinstance(msg, dict) and isinstance(msg.get("id"), str) and msg["id"] not in handled:  # untrusted
    handled.add(msg["id"])
    reply = handle(msg, state, configured_users(), llm(), retriever())
    replies.append({"id": msg["id"], "value": reply})
    st.rerun()
