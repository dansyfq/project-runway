import streamlit as st

from runway.ui import dataset_meta, disclaimer, footer

meta = dataset_meta()

st.markdown("<div class='rw-brand'>RUNWAY</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='rw-hero'><h1>How much lease you have left,<br>and what it buys you.</h1></div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p class='rw-lede'>Buying an HDB resale flat? Your age and the flat's remaining lease together decide how much "
    "CPF you can put towards it. A shorter lease also costs more in some towns than others. Runway works out "
    "both from the official rules and almost a million real resale sales, then explains what it means for you.</p>",
    unsafe_allow_html=True,
)

disclaimer(expanded=True)

st.markdown("### Two ways to use Runway")
left, right = st.columns(2)
with left:
    st.markdown(
        "<div class='rw-card'><h4>📈 Lease Explorer</h4>"
        "Enter your shortlisted towns, flat type and the youngest buyer's age. See whether the lease lasts until "
        "that buyer turns 95, how much CPF and HDB loan you could use, and what each missing year of lease "
        "costs in each town.</div>",
        unsafe_allow_html=True,
    )
    st.page_link("app_pages/lease_explorer.py", label="Open Lease Explorer", icon=":material/arrow_forward:")
with right:
    st.markdown(
        "<div class='rw-card'><h4>💬 Ask Runway</h4>"
        "Ask follow-up questions in plain English, like <i>what if my partner is the younger buyer?</i> "
        "Answers come only from official CPF Board, HDB and Ministry documents, with the source shown each time.</div>",
        unsafe_allow_html=True,
    )
    st.page_link("app_pages/ask_runway.py", label="Open Ask Runway", icon=":material/arrow_forward:")

st.markdown("### The rule most buyers miss")
st.markdown(
    "Since May 2019, CPF use for a flat depends on one test: **will the lease still be running when the youngest "
    "buyer turns 95?** If yes, CPF can pay up to the full Valuation Limit (the lower of the price and HDB's "
    "valuation). If not, but the lease has more than 20 years left, CPF use is scaled down:"
)
st.latex(r"\text{CPF share} = \frac{\text{remaining lease} - 20}{95 - \text{youngest buyer's age} - 20}")
st.markdown(
    "The HDB loan limit (75%) is scaled down by the same share, so a short lease bites twice. "
    "The same flat can be fully financeable for a 35-year-old and need extra cash from a 25-year-old."
)

c1, c2, c3 = st.columns(3)
c1.metric("Resale transactions analysed", f"{meta['rows']:,}")
c2.metric("Period covered", f"{meta['first_month'][:4]} to {meta['last_month'][:4]}")
c3.metric("Official documents", "32")

footer()
