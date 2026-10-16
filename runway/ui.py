"""Shared Streamlit helpers: styling, cached resources, the disclaimer and page footer."""

from __future__ import annotations

import streamlit as st

from runway.config import RULES_LAST_CHECKED
from runway.lease_data import load_meta, load_transactions
from runway.llm import LLM
from runway.rag import Retriever, load_chunks

DISCLAIMER = """
**IMPORTANT NOTICE:** This web application is a prototype developed for **educational purposes only**.
The information provided here is **NOT intended for real-world usage** and should not be relied upon
for making any decisions, especially those related to financial, legal, or healthcare matters.

**Furthermore, please be aware that the LLM may generate inaccurate or incorrect information.
You assume full responsibility for how you use any generated output.**

Always consult with qualified professionals for accurate and personalised advice.
"""

CSS = """
<style>
.rw-brand {font-weight: 800; letter-spacing: .32em; color: var(--primary-color); font-size: .9rem; margin-bottom: .25rem;}
.rw-hero h1 {font-size: 2.6rem; line-height: 1.1; margin-bottom: .4rem;}
.rw-lede {font-size: 1.15rem; color: #44505c; max-width: 46rem;}
.rw-card {border: 1px solid #dfe5ea; border-radius: 12px; padding: 1.1rem 1.2rem; background: #ffffff; height: 100%;}
.rw-card h4 {margin: 0 0 .35rem 0;}
.rw-verdict {border-left: 5px solid; border-radius: 8px; padding: .9rem 1.1rem; margin: .4rem 0 1rem 0; font-size: 1.05rem;}
.rw-ok {border-color: #2e7d5b; background: #eef7f2;}
.rw-warn {border-color: #c8811a; background: #fdf5e9;}
.rw-bad {border-color: #b3261e; background: #fbeceb;}
.rw-foot {color: #6b7680; font-size: .82rem; margin-top: 2rem; border-top: 1px solid #e6eaee; padding-top: .6rem;}
div[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading 986,090 resale transactions...")
def transactions():
    return load_transactions()


@st.cache_data
def dataset_meta() -> dict:
    return load_meta()


@st.cache_resource
def llm() -> LLM:
    return LLM()


@st.cache_resource(show_spinner="Indexing the official documents...")
def retriever() -> Retriever:
    chunks = load_chunks()
    bot = llm()
    if bot.available:
        try:
            return Retriever(chunks, embed=bot.embed)
        except Exception as exc:  # embeddings are an enhancement; keyword search still works
            fallback = Retriever(chunks)
            fallback.embed_error = f"{type(exc).__name__}: {exc}"
            print(f"[runway] embeddings failed, using keyword search: {fallback.embed_error}")
            return fallback
    return Retriever(chunks)


def disclaimer(expanded: bool = False) -> None:
    with st.expander("⚠️ IMPORTANT NOTICE: educational prototype, not for real-world decisions", expanded=expanded):
        st.markdown(DISCLAIMER)


def footer() -> None:
    meta = dataset_meta()
    st.markdown(
        f"<div class='rw-foot'>Rules last checked against CPF Board and HDB websites: {RULES_LAST_CHECKED}. "
        f"Transactions: {meta['rows']:,} HDB resale records, {meta['first_month']} to {meta['last_month']} "
        "(data.gov.sg). Educational prototype; confirm your position with CPF Board and your HFE letter.</div>",
        unsafe_allow_html=True,
    )


def sources_list(chunks) -> None:
    for i, c in enumerate(chunks, start=1):
        label = f"[{i}] {c.title}, {c.publisher}"
        st.markdown(f"- [{label}]({c.url})" + (f": *{c.heading}*" if c.heading else ""))
