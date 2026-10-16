import pandas as pd
import streamlit as st

from runway.map_data import PHOTO_DIR
from runway.rag import CORPUS_DIR, parse_doc
from runway.ui import DISCLAIMER, dataset_meta

meta = dataset_meta()

st.title("About Us")

st.markdown("### Notice")
with st.container(border=True):
    st.markdown(DISCLAIMER)
    st.markdown(
        "Runway is a learning project for the AI Champions Bootcamp 2026, not financial advice. Confirm your "
        "position with CPF Board and your HDB Flat Eligibility (HFE) letter."
    )

st.markdown(
    """
### What Runway does
Runway helps you buy an HDB resale flat with one rule in view: **how much lease you have left decides how much
CPF you can use**. Since 10 May 2019, CPF use depends on whether the flat's lease will last until the youngest
buyer turns 95. If it won't, CPF use and the HDB loan are both scaled down, and the rest has to be paid in cash.
The same flat can be fully financeable for a 35-year-old and need extra cash from a 25-year-old. A shorter lease
also costs very different amounts in different towns.

### Objectives
1. **Consolidate** the rules from CPF Board, HDB and the Ministry of National Development in one place.
2. **Personalise** the result with generic details only: ages, a rough CPF figure and a town. No names, NRIC
   numbers or account data are asked for or stored.
3. **Explain**, not just calculate: plain answers that cite the exact rule.
4. **Show** it clearly: a town map, verdict cards, a shortlist, a downloadable file and a chat.

### Features
| Feature | What it does |
|---|---|
| **Map** (use case 1) | Every flat sold in your town in Jul–Sep 2026, coloured by how much CPF you could use. Tap one for the verdict, the runway bar, CPF you can use and cash you need, plus HDB loan, loan length and monthly figures. |
| **Shortlist** | Keep flats, see them recalculated if your details change, save them as a file, and collect town stamps. |
| **Ask** (use case 2) | Questions answered from 32 official documents, with sources. Sums up the chat. Declines advice and attempts to change how it works. |
| **Safeguards** | The AI never calculates. Figures come from Runway's calculator, and an explanation containing a number the calculator didn't produce is replaced by a plain template. Password-protected access. |
"""
)

st.markdown("### Data sources")
st.markdown(
    f"- **Resale transactions:** {meta['rows']:,} HDB resale records, {meta['first_month']} to {meta['last_month']}, "
    "published by HDB on [data.gov.sg](https://data.gov.sg/collections/189/view) under the Singapore Open Data Licence.\n"
    "- **Map:** base map and addresses from [OneMap](https://www.onemap.gov.sg/), Singapore Land Authority. "
    "MRT and LRT lines © OpenStreetMap contributors via sgraildata. Amenities from data.gov.sg and OneMap.\n"
    "- **Rules library:** the official documents below, each with its link."
)
rows = []
for path in sorted(CORPUS_DIR.glob("*.md")):
    doc_meta, _ = parse_doc(path)
    rows.append({"Document": doc_meta["title"], "Publisher": doc_meta["publisher"], "Link": doc_meta["url"],
                 "Retrieved": doc_meta["retrieved"]})
docs = pd.DataFrame(rows).sort_values(["Publisher", "Document"])
st.dataframe(docs, hide_index=True, width="stretch",
             column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")})

photos = pd.read_csv(PHOTO_DIR / "landmarks.csv")
credits = photos[photos["status"] == "have"]
if not credits.empty:
    st.caption("Town stamp photos: " + "; ".join(f"{r.landmark} ({r.caption})" for r in credits.itertuples()))

st.markdown(
    """
### Team Runway
Lynn Koh · Leong Soon Poh · Danish Syafiq · Max How
"""
)
