"""Runway: how much lease you have left, and what it buys you.

Entry point for the multi-page Streamlit app. Every page sits behind the login.
Run locally with:  streamlit run app.py
"""

import time

import streamlit as st

from runway.auth import check_login
from runway.ui import inject_css

st.set_page_config(page_title="Runway", page_icon="🛫", layout="wide")
inject_css()

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


def configured_users() -> dict[str, str]:
    try:
        return {k.lower(): v for k, v in st.secrets["auth"]["users"].items()}
    except (KeyError, FileNotFoundError):
        return {}


def login_page() -> None:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div class='rw-brand'>RUNWAY</div>", unsafe_allow_html=True)
        st.markdown("#### How much lease you have left, and what it buys you")
        st.caption("A learning prototype for the AI Champions Bootcamp. Please sign in to continue.")

        users = configured_users()
        if not users:
            st.error("Sign-in isn't set up yet. The app owner needs to add accounts to the app's secrets.")
            st.stop()

        locked_until = st.session_state.get("locked_until", 0)
        if time.time() < locked_until:
            st.warning(f"Too many attempts. Try again in {int(locked_until - time.time())} seconds.")
            st.stop()

        with st.form("login"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            if check_login(username, password, users):
                st.session_state.update(user=username.strip().lower(), attempts=0)
                st.rerun()
            attempts = st.session_state.get("attempts", 0) + 1
            st.session_state["attempts"] = attempts
            if attempts >= MAX_ATTEMPTS:
                st.session_state.update(locked_until=time.time() + LOCKOUT_SECONDS, attempts=0)
            st.error("That username and password don't match.")


if "user" not in st.session_state:
    login_page()
    st.stop()

pages = {
    "Runway": [st.Page("app_pages/home.py", title="Home", icon=":material/flight_takeoff:", default=True)],
    "Use cases": [
        st.Page("app_pages/lease_explorer.py", title="Lease Explorer", icon=":material/insights:"),
        st.Page("app_pages/ask_runway.py", title="Ask Runway", icon=":material/forum:"),
    ],
    "About this project": [
        st.Page("app_pages/about.py", title="About Us", icon=":material/info:"),
        st.Page("app_pages/methodology.py", title="Methodology", icon=":material/account_tree:"),
    ],
}

with st.sidebar:
    st.caption(f"Signed in as **{st.session_state['user']}**")
    if st.button("Sign out", width="stretch"):
        st.session_state.clear()
        st.rerun()

st.navigation(pages).run()
