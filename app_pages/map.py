"""Use case 1: Town Safari. Every number comes from runway.cpf_rules; the LLM only explains (Why?)."""

import folium
import streamlit as st
from streamlit_folium import st_folium

from runway.cpf_rules import HDB_LTV, ASSUMED_HDB_RATE, flat_money
from runway.map_data import AMENITIES, LINE_COLOURS, blocks, nearest_block, town_label
from runway.ui import (
    LEGEND, buyer_ages, diamond_icon, llm, map_layers, money, retriever, sales, sources_list, town_premiums,
    verdict_card, verdict_sentence,
)

ONEMAP_TILES = "https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png"
ONEMAP_ATTRIBUTION = (
    '<img src="https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png" style="height:20px;width:20px;"/>'
    '&nbsp;<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a>'
    '&nbsp;&copy;&nbsp;contributors&nbsp;&#124;&nbsp;<a href="https://www.sla.gov.sg/" target="_blank" '
    'rel="noopener noreferrer">Singapore Land Authority</a>'
)

if "details" not in st.session_state:
    st.switch_page("app_pages/details.py")

if toast := st.session_state.pop("toast", None):
    st.toast(toast, icon=":material/kid_star:")

details = st.session_state["details"]
ages = buyer_ages()
youngest = min(ages)
town = details["town"]

all_sales = sales()
town_sales = all_sales[all_sales["town"] == town]
block_rows = blocks(town_sales, youngest)
if st.session_state.get("blocks_town") != town:  # new town: clear the old selection
    st.session_state.update(blocks_town=town, selected_block=None)

# ---- Town card -------------------------------------------------------------------------------------
premium = town_premiums().get(town_label(town))
if premium is None or not premium.reliable or premium.pct_per_year <= 0:
    meter, effect = "", "Not enough sales here to say how much lease changes the price."
else:
    pct = premium.pct_per_year
    filled = 1 if pct < 0.8 else 2 if pct < 1.3 else 3
    meter = "&#9670;" * filled + '<span style="color:#D9D4CC">' + "&#9670;" * (3 - filled) + "</span>"
    ten_years = 1 - (1 + pct / 100) ** -10
    effect = f"10 fewer years of lease &asymp; {ten_years:.0%} lower price here"

card, chips = st.columns([3, 2], vertical_alignment="center")
card.markdown(f'<div class="rw-card"><p class="rw-town">{town_label(town)}</p>'
              f'<span class="rw-meter">{meter}</span> {effect}</div>', unsafe_allow_html=True)
with chips:
    st.page_link("app_pages/details.py", label=f"Youngest buyer: {youngest} · Change town", icon=":material/person:")
    st.page_link("app_pages/about.py", label="Notice", icon=":material/info:")

# ---- Map -------------------------------------------------------------------------------------------
centre = [town_sales["lat"].median(), town_sales["lng"].median()]
m = folium.Map(location=centre, zoom_start=16, min_zoom=11, max_zoom=19, tiles=None, control_scale=True)
folium.TileLayer(ONEMAP_TILES, attr=ONEMAP_ATTRIBUTION, name="OneMap", min_zoom=11, max_zoom=19).add_to(m)

lines, stations, amenities = map_layers()
rail = folium.FeatureGroup(name="MRT and LRT")
for feature in lines:
    geom = feature["geometry"]
    parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
    coords = [[(lat, lng) for lng, lat in part] for part in parts]
    folium.PolyLine(coords, color=LINE_COLOURS.get(feature["properties"]["c"], "#748477"), weight=5, opacity=0.8,
                    tooltip=feature["properties"]["n"]).add_to(rail)
lat_lo, lat_hi = town_sales["lat"].min() - 0.01, town_sales["lat"].max() + 0.01
lng_lo, lng_hi = town_sales["lng"].min() - 0.01, town_sales["lng"].max() + 0.01
near = lambda df: df[df["lat"].between(lat_lo, lat_hi) & df["lng"].between(lng_lo, lng_hi)]  # noqa: E731
for row in near(stations).itertuples():
    folium.CircleMarker((row.lat, row.lng), radius=6, color="#111", weight=2, fill=True, fill_color="#fff",
                        fill_opacity=1, tooltip=f"{row.name} {row.codes}").add_to(rail)
rail.add_to(m)
for category, (label, colour) in AMENITIES.items():
    group = folium.FeatureGroup(name=label, show=category in {"hawker", "clinic", "mall"})
    for row in near(amenities[amenities["category"] == category]).itertuples():
        folium.CircleMarker((row.lat, row.lng), radius=7, color="#fff", weight=2, fill=True, fill_color=colour,
                            fill_opacity=1, tooltip=f"{label[:-1] if label.endswith('s') else label}: {row.name}").add_to(group)
    group.add_to(m)

flats = folium.FeatureGroup(name="Flats sold")
for row in block_rows.itertuples():
    icon = folium.DivIcon(html=diamond_icon(row.verdict, row.coverage, f"{row.lease:.0f} yrs", row.n_sales),
                          icon_size=(56, 46), icon_anchor=(14, 15))
    folium.Marker((row.lat, row.lng), icon=icon,
                  tooltip=f"Blk {row.block_id} · {row.n_sales} sale{'s' if row.n_sales > 1 else ''}").add_to(flats)
flats.add_to(m)
folium.LayerControl(collapsed=True, position="topright").add_to(m)

selected = st.session_state.get("selected_block")
map_col, panel_col = st.columns([3, 2]) if selected else (st.container(), None)
with map_col:
    clicked = st_folium(m, height=600, use_container_width=True, returned_objects=["last_object_clicked"],
                        key=f"map_{town}")
    st.markdown(LEGEND, unsafe_allow_html=True)
    st.markdown(f'<div class="rw-hint">{len(town_sales)} sales here in Jul&ndash;Sep 2026. '
                "Drag to look around, tap a diamond.</div>", unsafe_allow_html=True)

hit = (clicked or {}).get("last_object_clicked")
if hit:
    block_id = nearest_block(block_rows, hit["lat"], hit["lng"])
    if block_id and block_id != st.session_state.get("last_click"):
        st.session_state.update(selected_block=block_id, last_click=block_id, sale_idx=0)
        st.rerun()

if not selected:
    st.stop()

# ---- Flat panel ------------------------------------------------------------------------------------
block_sales = town_sales[town_sales["block_id"] == selected].sort_values("resale_price").reset_index(drop=True)
with panel_col:
    top, close = st.columns([2, 1], vertical_alignment="bottom")
    if close.button("Close", icon=":material/close:", key="close_panel", width="stretch"):
        st.session_state["selected_block"] = None
        st.rerun()
    if len(block_sales) > 1:
        choice = top.selectbox(
            f"{len(block_sales)} sales in this block", range(len(block_sales)),
            format_func=lambda i: (f"{money(block_sales.at[i, 'resale_price'])} · {block_sales.at[i, 'flat_type'].title()}"
                                   f" · storey {block_sales.at[i, 'storey_range'].lower()}"),
            key=f"sale_{selected}")
    else:
        choice = 0
    sale = block_sales.iloc[choice]
    lease = float(sale["remaining_lease_years"])

    st.markdown(
        f'<span class="rw-plate">BLK {sale["block"]}</span><p class="rw-street">{sale["street_name"].title()}</p>'
        f'<div class="rw-sub">{sale["flat_type"].title()} · storey {sale["storey_range"].lower().replace(" to ", "–")}'
        f' · {sale["floor_area_sqm"]:.0f} sqm<br>Singapore {sale["postal"]} · {town_label(town)}</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:.8rem">'
        f'<span class="rw-price">{money(sale["resale_price"])}</span><span class="rw-sub">sold {sale["month"]}</span></div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:.6rem"><span class="rw-label">Lease left</span>'
        f'<span style="font-weight:700;font-size:1.3rem">{lease:.0f} years</span></div>'
        f'<div class="rw-leasebar"><div style="width:{lease / 99:.0%}"></div></div>'
        f'<div class="rw-sub">Started {sale["lease_commence_date"]}. Leases are 99 years.</div>',
        unsafe_allow_html=True,
    )

    money_ = flat_money(float(sale["resale_price"]), lease, ages, details["cpf_oa"])
    c = money_.check
    st.markdown(verdict_card(money_, verdict_sentence(youngest, lease, c.cpf_allowed, c.covers_95)),
                unsafe_allow_html=True)
    with st.expander("More numbers"):
        st.markdown(
            f"- HDB loan limit: **{money(money_.loan_max)}** ({c.ltv_share:.0%} of the price; the full limit is "
            f"{HDB_LTV:.0%})\n"
            f"- Longest HDB loan: **{money_.tenure:.0f} years**\n"
            f"- Monthly payment at an assumed {ASSUMED_HDB_RATE:.1%}: **{money(money_.monthly)}**\n"
            f"- Cash at the start, after your CPF: **{money(money_.cash_at_start)}**"
        )
        st.caption("Numbers from Runway's calculator, not the AI. HDB's valuation is taken as the sale price. "
                   "Bank loans, grants and cash over valuation are not included.")

    facts = {
        "Youngest buyer age": f"{youngest}",
        "Remaining lease (years)": f"{lease:.0f}",
        "Youngest buyer is this old when lease ends": f"{c.covers_to_age:.0f}",
        "Lease covers youngest buyer to age 95": "yes" if c.covers_95 else "no",
        "Years short of age 95": f"{c.years_short:.0f}",
        "CPF can be used": "yes" if c.cpf_allowed else "no",
        "CPF usable (% of Valuation Limit)": f"{c.cpf_share * 100:.1f}",
        "HDB loan limit (% of price or value)": f"{c.ltv_share * 100:.1f}",
        "Full HDB loan limit (%)": f"{HDB_LTV * 100:.0f}",
    }
    if premium is not None and premium.reliable:
        facts["Lease premium by town"] = f"{town_label(town)} {premium.pct_per_year:.2f}% per year"
    st.session_state["explorer_facts"] = facts  # Ask Runway can use the flat you're looking at

    shortlist = st.session_state.setdefault("shortlist", [])
    key = (sale["block_id"], sale["month"], int(sale["resale_price"]), sale["storey_range"])
    kept = any((s["block_id"], s["month"], int(s["resale_price"]), s["storey_range"]) == key for s in shortlist)
    if st.button("In your shortlist" if kept else "Keep in shortlist", type="primary", width="stretch",
                 disabled=kept, icon=":material/kid_star:"):
        new_town = town not in {s["town"] for s in shortlist}
        shortlist.append(sale.to_dict())
        if new_town:
            st.session_state["toast"] = f"New town stamp: {town_label(town)}"  # shown after the rerun
        st.rerun()

    why_col, next_col = st.columns(2)
    if why_col.button("Why?", width="stretch", icon=":material/help:"):
        query = ("remaining lease does not cover youngest buyer to age 95 pro-rated CPF usage valuation limit"
                 if not c.covers_95 else "lease covers youngest buyer to age 95 CPF up to valuation limit")
        sources = retriever().search(query, k=4)
        with st.spinner("Writing the explanation..."):
            text, used_llm = llm().explain(facts, sources)
        st.session_state["why"] = (key, text, used_llm, sources)
    if next_col.button("Next flat", width="stretch", icon=":material/arrow_forward:"):
        ids = list(block_rows["block_id"])
        st.session_state["selected_block"] = ids[(ids.index(selected) + 1) % len(ids)]
        st.rerun()

    why = st.session_state.get("why")
    if why and why[0] == key:
        _, text, used_llm, sources = why
        with st.container(border=True):
            st.markdown(text)  # LLM text: plain markdown, never raw HTML
        if not used_llm:
            st.caption("Written from a fixed template using only Runway's numbers.")
        with st.expander(f"Where this comes from ({len(sources)})"):
            sources_list(sources)
