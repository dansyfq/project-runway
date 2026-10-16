"""Runway: how much lease you have left.

Entry point for the multi-page Streamlit app. Every page sits behind the sign-in.
Run locally with:  streamlit run app.py
"""

import time

import streamlit as st

from runway.auth import check_login
from runway.ui import details_card, inject_css, signin_banner

st.set_page_config(page_title="Runway", layout="wide")
inject_css()

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


def configured_users() -> dict[str, str]:
    try:
        return {k.lower(): v for k, v in st.secrets["auth"]["users"].items()}
    except (KeyError, FileNotFoundError):
        return {}


def login_page() -> None:
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown(signin_banner(), unsafe_allow_html=True)
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
    "": [
        st.Page("app_pages/map.py", title="Map", icon=":material/location_on:", default=True),
        st.Page("app_pages/shortlist.py", title="Shortlist", icon=":material/kid_star:"),
        st.Page("app_pages/ask_runway.py", title="Ask", icon=":material/forum:"),
    ],
    "More": [
        st.Page("app_pages/details.py", title="Your details", icon=":material/person:"),
        st.Page("app_pages/about.py", title="About Us", icon=":material/info:"),
        st.Page("app_pages/methodology.py", title="How it works", icon=":material/account_tree:"),
    ],
}

st.logo("assets/runway_lockup.svg", size="large")
nav = st.navigation(pages)

with st.sidebar:
    details_card()
    st.toggle("Large text", key="large_text")
    if st.button("Sign out", width="stretch"):
        st.session_state.clear()
        st.rerun()

nav.run()
