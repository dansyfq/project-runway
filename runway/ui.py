"""Shared Streamlit helpers: Runway brand theme, cached resources and reusable HTML components.

Design tokens and type follow design/DESIGN_SPEC.md from the hand-off (rust, paper, Source Serif 4,
IBM Plex Sans, Anton for the wordmark only; 18px base text with a 21px Large option).
"""

from __future__ import annotations

from html import escape

import streamlit as st

from runway.cpf_rules import FlatMoney
from runway.lease_data import load_meta, load_transactions, premiums_by_town
from runway.llm import LLM
from runway.map_data import (
    ALL_TOWNS, load_amenities, load_rail_lines, load_sales, load_stations, town_label, town_photo,
)
from runway.rag import Retriever, load_chunks

DISCLAIMER = """
**IMPORTANT NOTICE:** This web application is a prototype developed for **educational purposes only.**
The information provided here is **NOT intended for real-world usage** and should not be relied upon
for making any decisions, especially those related to financial, legal, or healthcare matters.

**Furthermore, please be aware that the LLM may generate inaccurate or incorrect information.
You assume full responsibility for how you use any generated output.**

Always consult with qualified professionals for accurate and personalised advice.
"""

MARK = (
    '<svg viewBox="0 0 100 100" aria-hidden="true" class="rw-mark"><g fill="{fg}">'
    '<path d="M50 3 97 50 50 97 3 50Z" fill="none" stroke="{fg}" stroke-width="2.5"/>'
    '<path d="M50 15 85 50 50 85 15 50Z"/><path d="M50 25 73 48 73 62 50 85 27 62 27 48Z" fill="{bg}"/>'
    '<path d="M31 52 38 48 38 73 31 66Z"/><path d="M41 46 48.5 42 48.5 83.5 41 76Z"/>'
    '<path d="M51.5 40 59 44 59 76 51.5 83.5Z"/><path d="M62 50 69 54 69 66 62 73Z"/></g></svg>'
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
:root {
  --rust:#7A2E1D; --rust-dark:#5C2215; --rust-soft:#F4E7E2; --ink:#111111; --body:#1C1C1C; --slate:#3A3A3A;
  --stone:#666666; --sand:#D9D4CC; --paper:#F6F3EE; --ok:#2C6845; --ok-soft:#E2EFE6; --part:#8F5509;
  --part-soft:#F8EAD4; --no:#3A3A3A; --no-soft:#ECEAE6; --plate:#F2C230;
}
html { font-size: __BASE__px; }
html, body, [data-testid="stAppViewContainer"], .stMarkdown, p, li, input, textarea {
  font-family: 'Source Serif 4', Georgia, serif; color: var(--body);
}
h1, h2, h3, h4 { font-family: 'Source Serif 4', Georgia, serif !important; color: var(--ink) !important; font-weight: 700 !important; }
h1 { font-size: 1.8rem !important; }
label, button p, [data-testid="stWidgetLabel"] p, [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"],
[data-testid="stSidebarNav"] a span:not([data-testid="stIconMaterial"]), .stTabs button p, table, th, td {
  font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
}
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] { height: 3.4rem !important; max-width: 100%; }
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a {
  min-height: 56px; border-radius: 12px; border-width: 2px; font-weight: 600; font-size: 1rem;
}
button[kind="primary"], button[kind="primary"] p, button[kind="primaryFormSubmit"], button[kind="primaryFormSubmit"] p {
  color: #fff !important; }
button[kind="primary"]:disabled, button[kind="primary"]:disabled p { color: var(--slate) !important; }
.stButton button[kind="secondary"], .stDownloadButton button { border-color: var(--rust); color: var(--rust); background: #fff; }
[data-testid="stSidebar"] { background: var(--paper); border-right: 1px solid var(--sand); }
[data-testid="stSidebarNav"] a { min-height: 52px; border-radius: 12px; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: #fff; box-shadow: inset 4px 0 0 var(--rust); }
[data-testid="stSidebarNav"] a span:not([data-testid="stIconMaterial"]) { font-size: 1.05rem; color: var(--ink); }
[data-testid="stChatMessage"] { background: var(--paper); border-radius: 14px; }

.rw-wm { font-family:'Anton', sans-serif; font-size:1.9rem; letter-spacing:.04em; line-height:1; color:var(--rust); }
.rw-tg { font-family:'IBM Plex Sans', sans-serif; font-size:.6rem; letter-spacing:.16em; color:var(--slate); text-transform:uppercase; }
.rw-signin { background:var(--rust); border-radius:18px; padding:2.2rem 1.4rem 1.6rem; text-align:center; margin-bottom:1rem; }
.rw-signin .rw-mark { width:5rem; height:5rem; }
.rw-signin .rw-wm { color:#fff; font-size:3.2rem; display:block; margin-top:.6rem; }
.rw-signin .rw-tg { color:#fff; font-size:.8rem; display:block; margin-top:.5rem; }
.rw-label { font-family:'IBM Plex Sans', sans-serif; font-size:.72rem; font-weight:600; letter-spacing:.12em; text-transform:uppercase; color:var(--slate); }
.rw-card { border:2px solid var(--sand); border-radius:14px; padding:1rem 1.1rem; background:#fff; }
.rw-paper { background:var(--paper); border-radius:14px; padding:1rem 1.1rem; }
.rw-town { font-size:1.45rem; font-weight:700; color:var(--ink); margin:0; }
.rw-meter { color:var(--rust); letter-spacing:.05em; font-size:1rem; }
.rw-hint { background:var(--ink); color:#fff; border-radius:12px; padding:.7rem 1rem; font-family:'IBM Plex Sans', sans-serif; font-size:.95rem; }
.rw-legend { font-family:'IBM Plex Sans', sans-serif; font-size:.85rem; display:flex; gap:1rem; flex-wrap:wrap; margin:.4rem 0; }
.rw-legend svg { width:.9rem; height:.9rem; vertical-align:-2px; margin-right:.3rem; }
.rw-plate { display:inline-block; background:var(--ink); color:var(--plate); font-family:'IBM Plex Sans', sans-serif;
  font-weight:600; letter-spacing:.08em; padding:.2rem .6rem; border-radius:4px; font-size:1.1rem; }
.rw-street { font-size:1.35rem; font-weight:700; color:var(--ink); margin:.3rem 0 0; }
.rw-sub { font-family:'IBM Plex Sans', sans-serif; color:var(--slate); font-size:.92rem; }
.rw-price { font-size:1.7rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums; }
.rw-leasebar { height:.75rem; border-radius:999px; background:#fff; border:2px solid var(--sand); overflow:hidden; }
.rw-leasebar div { height:100%; background:var(--rust); }
.rw-verdict { border:2px solid; border-radius:16px; padding:1rem 1.1rem; margin:.8rem 0; }
.rw-verdict.full { border-color:var(--ok); background:var(--ok-soft); }
.rw-verdict.part { border-color:var(--part); background:var(--part-soft); }
.rw-verdict.none { border-color:var(--no); background:var(--no-soft); }
.rw-stamp { display:inline-block; font-family:'IBM Plex Sans', sans-serif; font-weight:600; font-size:1.05rem; padding:.25rem .8rem;
  border:3px solid currentColor; border-radius:8px; transform:rotate(-3deg); background:#fff; }
.rw-verdict.full .rw-stamp { color:var(--ok); } .rw-verdict.part .rw-stamp { color:var(--part); } .rw-verdict.none .rw-stamp { color:var(--no); }
.rw-sentence { font-size:1.08rem; margin:.7rem 0; }
.rw-runway { position:relative; height:1.4rem; background:var(--ink); border-radius:3px; margin:1rem 0 .3rem; overflow:hidden; }
.rw-runway .dash { position:absolute; top:50%; left:2%; height:3px; margin-top:-1.5px;
  background:repeating-linear-gradient(90deg, var(--plate) 0 14px, transparent 14px 26px); }
.rw-runway .gap { position:absolute; top:0; bottom:0; right:0;
  background:repeating-linear-gradient(45deg, #fff 0 6px, var(--sand) 6px 12px); }
.rw-runway .plane { position:absolute; top:50%; transform:translate(-100%,-50%); color:var(--plate); font-size:1.2rem; line-height:1; }
.rw-runway-ends { display:flex; justify-content:space-between; font-family:'IBM Plex Sans', sans-serif; font-size:.8rem; color:var(--slate); }
.rw-tiles { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; margin-top:.8rem; }
.rw-tile { background:#fff; border-radius:12px; padding:.7rem .8rem; }
.rw-tile .big { font-size:1.3rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums; }
.rw-tile .small { font-family:'IBM Plex Sans', sans-serif; font-size:.8rem; color:var(--slate); }
.rw-stamps { display:grid; grid-template-columns:repeat(auto-fill, minmax(6.5rem, 1fr)); gap:.8rem; }
.rw-stampcell { text-align:center; font-family:'IBM Plex Sans', sans-serif; font-size:.75rem; color:var(--slate); }
.rw-coin { width:5rem; height:5rem; margin:0 auto .3rem; border-radius:50%; border:2px dashed var(--sand); overflow:hidden;
  display:flex; align-items:center; justify-content:center; background:#fff; }
.rw-coin.earned { border:3px solid var(--rust); background:var(--rust-soft); transform:rotate(-6deg); }
.rw-coin img { width:100%; height:100%; object-fit:cover; }
.rw-coin svg { width:2.4rem; height:2.4rem; }
.rw-notice-link { font-family:'IBM Plex Sans', sans-serif; font-size:.85rem; }
@media (prefers-reduced-motion: no-preference) {
  .rw-verdict .rw-stamp { animation: rw-drop .35s ease-out; }
  @keyframes rw-drop { from { transform: rotate(-12deg) scale(1.3); opacity:0; } to { transform: rotate(-3deg) scale(1); opacity:1; } }
}
@media (max-width: 700px) { .rw-tiles { grid-template-columns:1fr; } .rw-signin .rw-wm { font-size:2.6rem; } }
</style>
"""

DIAMOND_COLOURS = {"full": "#2C6845", "part": "#8F5509", "none": "#3A3A3A"}
VERDICT_LABEL = {"full": "CPF: full use", "part": "CPF: part only", "none": "CPF: not allowed"}
LEGEND = (
    '<div class="rw-legend">'
    '<span><svg viewBox="0 0 20 20"><path d="M10 1 19 10 10 19 1 10Z" fill="#2C6845"/></svg>Full CPF</span>'
    '<span><svg viewBox="0 0 20 20"><defs><clipPath id="lgc"><rect x="0" y="10" width="20" height="10"/></clipPath></defs>'
    '<path d="M10 1 19 10 10 19 1 10Z" fill="#fff" stroke="#8F5509" stroke-width="2"/>'
    '<path d="M10 1 19 10 10 19 1 10Z" fill="#8F5509" clip-path="url(#lgc)"/></svg>Part CPF</span>'
    '<span><svg viewBox="0 0 20 20"><path d="M10 2 18 10 10 18 2 10Z" fill="#fff" stroke="#3A3A3A" stroke-width="2"/></svg>No CPF</span>'
    "</div>"
)


def inject_css() -> None:
    base = 21 if st.session_state.get("large_text") else 18
    st.markdown(CSS.replace("__BASE__", str(base)), unsafe_allow_html=True)


def signin_banner() -> str:
    return (f'<div class="rw-signin">{MARK.format(fg="#fff", bg="#7A2E1D")}<span class="rw-wm">RUNWAY</span>'
            '<span class="rw-tg">How much lease you have left</span></div>')


def money(x: float) -> str:
    return f"${x:,.0f}"


def diamond_icon(verdict: str, coverage: float, label: str, count: int = 1, faded: bool = False) -> str:
    """Map marker: diamond filled from the bottom by CPF coverage, coloured by verdict."""
    colour = DIAMOND_COLOURS[verdict]
    fill_from = 20 - 20 * (1.0 if verdict == "full" else coverage)
    badge = (f'<text x="25" y="7" font-size="8" fill="#fff" text-anchor="middle" font-family="sans-serif">{count}</text>'
             if count > 1 else "")
    badge_bg = '<circle cx="25" cy="5" r="5" fill="#111"/>' if count > 1 else ""
    cross = '<path d="M7 7l6 6M13 7l-6 6" stroke="#3A3A3A" stroke-width="2"/>' if verdict == "none" else ""
    uid = f"c{abs(hash((verdict, round(coverage, 2))))}"
    return (
        f'<div style="opacity:{0.28 if faded else 1};text-align:center;width:56px;margin-left:-14px">'
        f'<svg width="30" height="30" viewBox="-2 -2 32 24"><defs><clipPath id="{uid}">'
        f'<rect x="0" y="{fill_from:.1f}" width="20" height="20"/></clipPath></defs>'
        f'<path d="M10 1 19 10 10 19 1 10Z" fill="#fff" stroke="{colour}" stroke-width="2"/>'
        f'<path d="M10 1 19 10 10 19 1 10Z" fill="{colour}" clip-path="url(#{uid})"/>{cross}{badge_bg}{badge}</svg>'
        f'<div style="font:600 11px IBM Plex Sans,sans-serif;background:#fff;border-radius:4px;padding:0 3px;'
        f'display:inline-block;color:#111">{escape(label)}</div></div>'
    )


def runway_bar(youngest_age: int, remaining_lease: float) -> str:
    """Black runway from now to age 95; dashes until the lease ends, hatched gap after it."""
    span = max(95 - youngest_age, remaining_lease)
    end_pct = min(100.0, 100 * remaining_lease / span)
    gap = "" if end_pct >= 100 else f'<div class="gap" style="width:{100 - end_pct:.1f}%"></div>'
    ends_at = youngest_age + remaining_lease
    return (
        f'<div class="rw-runway"><div class="dash" style="width:{max(end_pct - 4, 0):.1f}%"></div>{gap}'
        f'<div class="plane" style="left:{end_pct:.1f}%">&#9992;</div></div>'
        f'<div class="rw-runway-ends"><span>Now {youngest_age}</span>'
        f'<span>Lease ends at {ends_at:.0f}{"" if end_pct >= 100 else " · 95"}</span></div>'
    )


def verdict_card(m: FlatMoney, sentence: str) -> str:
    v = "none" if not m.check.cpf_allowed else ("full" if m.check.covers_95 else "part")
    if v == "full":
        cash_big, cash_small = "$0 extra", "CPF is not cut"
        cpf_small = "full amount"
    else:
        cash_big, cash_small = f"at least {money(m.cash_on_top)}", "on top of CPF"
        cpf_small = f"{m.check.cpf_share:.0%} of the price" if v == "part" else "lease is 20 years or less"
    return (
        f'<div class="rw-verdict {v}"><span class="rw-stamp">{VERDICT_LABEL[v]}</span>'
        f'<p class="rw-sentence">{escape(sentence)}</p>'
        f'{runway_bar(m.check.youngest_age, m.check.remaining_lease)}'
        f'<div class="rw-tiles"><div class="rw-tile"><div class="small">CPF you can use</div>'
        f'<div class="big">up to {money(m.cpf_cap)}</div><div class="small">{cpf_small}</div></div>'
        f'<div class="rw-tile"><div class="small">Cash you need</div><div class="big">{cash_big}</div>'
        f'<div class="small">{cash_small}</div></div></div></div>'
    )


def verdict_sentence(youngest_age: int, remaining_lease: float, cpf_allowed: bool, covers_95: bool) -> str:
    """Brand reference: 'This flat has 58 years left. Your youngest buyer is 28, so the lease runs out ...'"""
    lease = round(remaining_lease)
    if not cpf_allowed:
        return f"This flat has {lease} years left. CPF and HDB loans cannot be used when 20 years or less remain."
    if covers_95:
        return f"This flat has {lease} years left. Your youngest buyer is {youngest_age}, so the lease lasts past age 95."
    short = round(95 - youngest_age - remaining_lease)
    return (f"This flat has {lease} years left. Your youngest buyer is {youngest_age}, so the lease runs out "
            f"{short} years before age 95 and your CPF use is reduced.")


def stamps_grid(earned: set[str]) -> str:
    cells = []
    for town in ALL_TOWNS:
        got = town in earned
        photo = town_photo(town) if got else None
        inner = (f'<img src="data:image/jpeg;base64,{_b64(photo)}" alt="">' if photo
                 else MARK.format(fg="#7A2E1D" if got else "#D9D4CC", bg="#fff"))
        cells.append(f'<div class="rw-stampcell"><div class="rw-coin{" earned" if got else ""}">{inner}</div>'
                     f'{escape(town_label(town))}</div>')
    return f'<div class="rw-stamps">{"".join(cells)}</div>'


def _b64(path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode()


def details_card() -> None:
    d = st.session_state.get("details")
    if not d:
        return
    other = f"Other buyer {d['other_age']}" if d.get("other_age") else "Buying alone"
    st.markdown(
        f'<div class="rw-card"><div class="rw-label">Your details</div>'
        f'<div style="font-weight:700;font-size:1.05rem">Youngest buyer {d["youngest"]}</div>'
        f'<div class="rw-sub">{other} · CPF {money(d["cpf_oa"])}</div></div>',
        unsafe_allow_html=True,
    )


def buyer_ages() -> list[int]:
    d = st.session_state["details"]
    return [d["youngest"]] + ([d["other_age"]] if d.get("other_age") else [])


# ---- cached data ----------------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading resale transactions...")
def transactions():
    return load_transactions()


@st.cache_data
def dataset_meta() -> dict:
    return load_meta()


@st.cache_data
def sales():
    return load_sales()


@st.cache_data
def map_layers():
    return load_rail_lines(), load_stations(), load_amenities()


@st.cache_data
def town_premiums() -> dict[str, object]:
    """Lease premium per town, 4-room flats sold since Jan 2024 (the proposal's Table 1 method)."""
    return {p.town: p for p in premiums_by_town(transactions(), "4 ROOM", "2024-01-01")}


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


def sources_list(chunks) -> None:
    for i, c in enumerate(chunks, start=1):
        label = f"[{i}] {c.title}, {c.publisher}"
        st.markdown(f"- [{label}]({c.url})" + (f": *{c.heading}*" if c.heading else ""))
