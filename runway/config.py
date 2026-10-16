"""Read settings from Streamlit secrets first, then environment variables."""

from __future__ import annotations

import os

RULES_LAST_CHECKED = "16 Oct 2026"
DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"


def get_setting(name: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets file, or not running under Streamlit
        pass
    return os.environ.get(name, default)
