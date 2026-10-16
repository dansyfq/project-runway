"""Shortlist: kept flats, recalculated for your current details, plus town stamps."""

import pandas as pd
import streamlit as st

from runway.cpf_rules import flat_money
from runway.map_data import ALL_TOWNS, town_label, verdict
from runway.ui import VERDICT_LABEL, buyer_ages, money, stamps_grid

st.title("Shortlist")

shortlist = st.session_state.get("shortlist", [])
if "details" not in st.session_state or not shortlist:
    st.markdown("Nothing kept yet. Tap a diamond on the map, then **Keep in shortlist**.")
    st.page_link("app_pages/map.py", label="Go to the map", icon=":material/location_on:")
else:
    ages, cpf_oa = buyer_ages(), st.session_state["details"]["cpf_oa"]
    st.caption(f"Worked out for a youngest buyer aged {min(ages)}. Change this in Your details.")
    rows = []
    for i, s in enumerate(shortlist):
        lease = float(s["remaining_lease_years"])
        m = flat_money(float(s["resale_price"]), lease, ages, cpf_oa)
        v = verdict(min(ages), lease)
        extra = "no extra cash" if v == "full" else f"+{money(m.cash_on_top)} cash"
        with st.container(border=True):
            left, right = st.columns([4, 1], vertical_alignment="center")
            left.markdown(
                f'<span class="rw-plate">BLK {s["block"]}</span> **{s["street_name"].title()}**<br>'
                f'<span class="rw-sub">{town_label(s["town"])} · {s["flat_type"].title()} · {lease:.0f} years left</span><br>'
                f'<span class="rw-verdict {v}" style="display:inline-block;padding:.1rem .6rem;margin:.3rem 0">'
                f'{VERDICT_LABEL[v]}</span> **{money(s["resale_price"])}** · {extra}',
                unsafe_allow_html=True,
            )
            if right.button("Remove", key=f"rm{i}", icon=":material/delete:"):
                shortlist.pop(i)
                st.rerun()
        rows.append({
            "Block": s["block"], "Street": s["street_name"], "Town": town_label(s["town"]), "Flat type": s["flat_type"],
            "Price": int(s["resale_price"]), "Lease left (years)": round(lease, 1), "Sold": s["month"],
            "CPF verdict": VERDICT_LABEL[v], "CPF you can use": round(m.cpf_cap), "Cash on top of CPF": round(m.cash_on_top),
        })
    st.download_button("Save shortlist as a file", pd.DataFrame(rows).to_csv(index=False),
                       file_name="runway_shortlist.csv", mime="text/csv", width="stretch", icon=":material/download:")

earned = {s["town"] for s in shortlist}
st.subheader("Town stamps")
st.markdown(f"**{len(earned)} of {len(ALL_TOWNS)}** towns. Keep a flat in a town to earn its stamp.")
st.markdown(stamps_grid(earned), unsafe_allow_html=True)
