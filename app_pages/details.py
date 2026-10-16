"""Your details: the only personal inputs Runway uses. Also the first-run setup before the map."""

import streamlit as st

from runway.map_data import REGIONS, town_label

AGE_CHIPS = [25, 30, 35, 40, 50, 60]
CPF_CHIPS = {"Not sure": 0, "$50,000": 50_000, "$100,000": 100_000, "$150,000": 150_000, "$200,000": 200_000}

current = st.session_state.get("details", {})
first_run = not current

st.title("Your details" if not first_run else "Before you start")
st.markdown("Runway only needs ages and a rough CPF figure. No names, NRIC or contact details.")

st.markdown('<div class="rw-label">Youngest buyer\'s age</div>', unsafe_allow_html=True)
chip = st.pills("Quick pick", AGE_CHIPS, default=None, label_visibility="collapsed", key="age_chip")
youngest = st.number_input("Youngest buyer's age", min_value=21, max_value=90, step=1,
                           value=chip or current.get("youngest", 30), label_visibility="collapsed")

other = st.number_input("Other buyer's age (0 if you're buying alone)", min_value=0, max_value=90, step=1,
                        value=current.get("other_age", 0))

st.markdown('<div class="rw-label">Rough CPF Ordinary Account savings, all buyers</div>', unsafe_allow_html=True)
cpf_default = next((k for k, v in CPF_CHIPS.items() if v == current.get("cpf_oa", 0)), "Not sure")
cpf_label = st.pills("CPF savings", list(CPF_CHIPS), default=cpf_default, label_visibility="collapsed")

st.markdown('<div class="rw-label">Town to look at first</div>', unsafe_allow_html=True)
current_town = current.get("town", "CLEMENTI")
region_default = next(r for r, towns in REGIONS.items() if current_town in towns)
region = st.pills("Region", list(REGIONS), default=region_default, label_visibility="collapsed") or region_default
towns = REGIONS[region]
town = st.pills("Town", towns, default=current_town if current_town in towns else towns[0],
                format_func=town_label, label_visibility="collapsed") or towns[0]

if 0 < other < 21:
    st.error("Buyers must be at least 21. Enter 0 if you're buying alone.")
elif st.button("Show me the map" if first_run else "Save my details", type="primary", width="stretch"):
    st.session_state["details"] = {
        "youngest": int(min(youngest, other) if other else youngest),
        "other_age": int(max(youngest, other)) if other else 0,
        "cpf_oa": CPF_CHIPS[cpf_label or "Not sure"],
        "town": town,
    }
    st.session_state.pop("selected_block", None)
    st.switch_page("app_pages/map.py")
