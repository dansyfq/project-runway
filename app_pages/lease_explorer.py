"""Use case 1: Lease Explorer. All figures come from code; the LLM only explains them."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from runway.cpf_rules import HDB_LTV, check_lease, cpf_share, lease_needed_for_full_cpf, max_loan_tenure
from runway.lease_data import premium_table, premiums_by_town, recent_sales
from runway.ui import disclaimer, footer, llm, retriever, sources_list, transactions

FLAT_TYPES = ["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
WINDOWS = {"Since Jan 2024": "2024-01-01", "Since Jan 2022": "2022-01-01", "Last 12 months": None}

st.title("Lease Explorer")
st.caption("Will the lease last until your youngest buyer turns 95, and what does a shorter lease cost in your towns?")
disclaimer()

df = transactions()
all_towns = sorted(df["town"].cat.categories.tolist())
last_month = df["month"].max()

with st.form("inputs"):
    a, b, c = st.columns([2, 1, 1])
    towns = a.multiselect("Towns you're considering (up to 5)", all_towns, default=["Clementi", "Yishun"], max_selections=5)
    flat_type = b.selectbox("Flat type", FLAT_TYPES, index=2)
    window_label = c.selectbox("Sales to compare", list(WINDOWS), index=0)

    d, e, f, g = st.columns(4)
    youngest = d.number_input("Youngest buyer's age", min_value=21, max_value=90, value=28, step=1)
    other = e.number_input("Other buyer's age (0 if buying alone)", min_value=0, max_value=90, value=30, step=1)
    lease = f.slider("Remaining lease of the flat (years)", min_value=21, max_value=99, value=58)
    price = g.number_input("Price or valuation, whichever is lower ($)", min_value=50_000, max_value=2_000_000,
                           value=550_000, step=10_000, help="CPF and loan limits are based on the lower of the two.")
    st.form_submit_button("Show my result", type="primary")

if 0 < other < 21:
    st.error("Buyers must be at least 21. Enter 0 for the other buyer's age if you're buying alone.")
    st.stop()
if other and other < youngest:
    st.info(f"The other buyer ({other}) is younger, so the rules use **{other}** as the youngest buyer's age.")
    youngest, other = other, youngest
ages = [youngest] + ([other] if other else [])

result = check_lease(int(youngest), float(lease))
tenure = max_loan_tenure(ages, float(lease))
cpf_amount = price * result.cpf_share
loan_amount = price * result.ltv_share

# ---- 1. The age-95 test ---------------------------------------------------------------------------
st.subheader("1. Does the lease cover your youngest buyer to age 95?")
if not result.cpf_allowed:
    css, verdict = "rw-bad", f"With {lease} years left, CPF can't be used at all: the lease must be more than 20 years."
elif result.covers_95:
    css, verdict = "rw-ok", (f"Yes. The lease runs until your youngest buyer is <b>{result.covers_to_age:.0f}</b>, past 95, "
                             "so CPF can pay up to the full Valuation Limit.")
else:
    css, verdict = "rw-warn", (f"No. The lease runs out when your youngest buyer is <b>{result.covers_to_age:.0f}</b>, "
                               f"<b>{result.years_short:.0f} years short</b> of 95. CPF use and the HDB loan are both scaled down.")
st.markdown(f"<div class='rw-verdict {css}'>{verdict}</div>", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("CPF you can use", f"{result.cpf_share:.1%}")
m1.caption(f"\\${cpf_amount:,.0f} of \\${price:,.0f} Valuation Limit")
m2.metric("HDB loan limit", f"{result.ltv_share:.1%}")
m2.caption(f"\\${loan_amount:,.0f}; the full limit is 75%")
m3.metric("Longest HDB loan", f"{tenure:.0f} years")
m3.caption("Shortest of 25, 65 minus average age, lease minus 20")
needed = lease_needed_for_full_cpf(youngest)
m4.metric("Full-CPF lease", f"{needed} years")
m4.caption(f"Lease needed for full CPF at age {youngest}; this flat has {lease}")

ages_axis = np.arange(21, 66)
curve = pd.DataFrame({"Youngest buyer's age": ages_axis, "CPF share": [cpf_share(int(x), lease) * 100 for x in ages_axis]})
fig = px.line(curve, x="Youngest buyer's age", y="CPF share", markers=False,
              labels={"CPF share": "CPF usable (% of Valuation Limit)"})
fig.add_scatter(x=[youngest], y=[result.cpf_share * 100], mode="markers", marker=dict(size=12, color="#E09F3E"),
                name="You")
fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                  title=f"Same flat ({lease} years left), different buyer ages", yaxis_range=[0, 105])
st.plotly_chart(fig, width="stretch")

# ---- 2. Lease premium by town --------------------------------------------------------------------
st.subheader("2. What does each year of lease cost in your towns?")
since = WINDOWS[window_label] or (last_month - pd.DateOffset(months=11)).strftime("%Y-%m-01")
if not towns:
    st.info("Pick at least one town above.")
    premiums = []
else:
    premiums = premiums_by_town(df, flat_type, since, towns)

if towns and not premiums:
    st.warning(f"Not enough {flat_type.lower()} sales in these towns for this period.")
elif premiums:
    table = premium_table(premiums)
    bar = go.Figure(go.Bar(
        x=[p.pct_per_year for p in premiums], y=[p.town for p in premiums], orientation="h",
        error_x=dict(type="data", symmetric=False,
                     array=[p.ci_high - p.pct_per_year for p in premiums],
                     arrayminus=[p.pct_per_year - p.ci_low for p in premiums]),
        marker_color=["#0F4C5C" if p.reliable else "#9aa5ad" for p in premiums],
        text=[f"{p.pct_per_year:.2f}%" for p in premiums], textposition="inside", insidetextanchor="start",
    ))
    bar.update_layout(height=80 + 45 * len(premiums), margin=dict(l=10, r=40, t=10, b=10),
                      xaxis_title="Extra price per sqm for each extra year of lease (%)")
    st.plotly_chart(bar, width="stretch")

    reliable = [p for p in premiums if p.reliable]
    if len(reliable) >= 2 and reliable[0].pct_per_year > 0:
        lo, hi = reliable[0], reliable[-1]
        st.markdown(f"In **{hi.town}**, each missing year of lease knocks about **{hi.pct_per_year:.2f}%** off the price "
                    f"per sqm: **{hi.pct_per_year / lo.pct_per_year:.1f}×** the {lo.pct_per_year:.2f}% in **{lo.town}**.")
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download this table (CSV)", table.to_csv(index=False), file_name="runway_lease_premium.csv",
                       mime="text/csv")

    sales = recent_sales(df, flat_type, since)
    sales = sales[sales["town"].isin(towns)]
    sample = sales.sample(min(len(sales), 4000), random_state=0)
    palette = dict(zip(towns, px.colors.qualitative.Bold))
    scatter = px.scatter(sample, x="remaining_lease", y="price_psm", color="town", opacity=0.3,
                         color_discrete_map=palette,
                         labels={"remaining_lease": "Remaining lease at sale (years)", "price_psm": "Price per sqm ($)"})
    xs = np.linspace(min(p.lease_min for p in premiums), max(p.lease_max for p in premiums), 50)
    for p in premiums:
        scatter.add_scatter(x=xs, y=[p.predicted_psm(x) for x in xs], mode="lines", name=f"{p.town} trend",
                            line=dict(width=3, color=palette[p.town]))
    scatter.add_vline(x=lease, line_dash="dash", annotation_text=f"your flat: {lease} yrs")
    scatter.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(scatter, width="stretch")
    st.caption(f"{len(sales):,} {flat_type.lower()} sales, {pd.Timestamp(since):%b %Y} to {last_month:%b %Y}"
               + (f" ({len(sample):,} shown)." if len(sample) < len(sales) else ".")
               + " A pattern, not a cause: it doesn't adjust for floor level, size, model or condition.")

# ---- 3. Plain-English explanation ----------------------------------------------------------------
st.subheader("3. What this means, in plain English")
facts = {
    "Youngest buyer age": f"{youngest}",
    "Remaining lease (years)": f"{lease}",
    "Youngest buyer is this old when lease ends": f"{result.covers_to_age:.0f}",
    "Lease covers youngest buyer to age 95": "yes" if result.covers_95 else "no",
    "Years short of age 95": f"{result.years_short:.0f}",
    "CPF can be used": "yes" if result.cpf_allowed else "no",
    "CPF usable (% of Valuation Limit)": f"{result.cpf_share * 100:.1f}",
    "HDB loan limit (% of price or value)": f"{result.ltv_share * 100:.1f}",
    "Full HDB loan limit (%)": f"{HDB_LTV * 100:.0f}",
    "Lease needed for full CPF (years)": f"{needed}",
    "Longest HDB loan (years)": f"{tenure:.0f}",
}
if premiums:
    facts["Lease premium by town"] = "; ".join(f"{p.town} {p.pct_per_year:.2f}% per year" for p in premiums)

if st.button("Explain my result", type="primary"):
    query = ("remaining lease does not cover youngest buyer to age 95 pro-rated CPF usage valuation limit loan-to-value"
             if not result.covers_95 else "lease covers youngest buyer to age 95 CPF up to valuation limit")
    sources = retriever().search(query, k=4)
    with st.spinner("Writing your explanation..."):
        text, used_llm = llm().explain(facts, sources)
    st.session_state["explanation"] = (text, used_llm, sources, facts)

st.session_state["explorer_facts"] = facts  # Ask Runway reads this, so save it on every run
saved = st.session_state.get("explanation")
if saved and saved[3] == facts:  # hide an explanation written for different inputs
    text, used_llm, sources, _ = saved
    st.markdown(text)
    if not used_llm:
        st.caption("Written from a fixed template using only the computed figures (AI explainer offline, "
                   "or its draft contained a figure we didn't compute).")
    with st.expander("Rules this explanation relies on"):
        sources_list(sources)
    st.page_link("app_pages/ask_runway.py", label="Ask a follow-up question about your result", icon=":material/forum:")

footer()
