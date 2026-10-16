import pandas as pd
import streamlit as st

from runway.rag import CORPUS_DIR, parse_doc
from runway.ui import dataset_meta, disclaimer, footer

meta = dataset_meta()

st.title("About Us")
disclaimer()

st.markdown(
    """
### Project scope
Runway is a capstone project for the AI Champions Bootcamp 2026 (Project Type 2: an interactive LLM-powered
solution for citizens). It covers one government transaction: **buying an HDB flat on the resale market**, and
the part of it that most often catches buyers out: how the flat's **remaining lease** and the buyers' **ages**
decide how much CPF (Central Provident Fund) savings and HDB loan they can use.

### The problem
Buyers can already get a number from HDB's and CPF Board's calculators. What they can't get is an explanation
of *why* the number changes with lease and age. Since 10 May 2019, CPF use is scaled down when a flat's lease won't
last until the youngest buyer turns 95. The same flat can be fully financeable for a 35-year-old and need extra cash
from a 25-year-old. A shorter lease also costs very different amounts in different towns: in mature towns like
Clementi, each year of lease is worth about three times as much per square metre as in Yishun.

### Objectives
1. **Consolidate** the scattered rules from CPF Board, HDB and the Ministry of National Development into one place.
2. **Personalise** the result: buyers enter only generic details (towns, flat type, ages, lease, price). No names,
   NRIC numbers or account data are asked for or stored.
3. **Explain**, not just calculate: plain-English explanations and follow-up answers, each citing the exact rule.
4. **Present** it effectively: a verdict, metrics, charts, a downloadable table and a chat interface.

### Features
| Feature | What it does |
|---|---|
| **Lease Explorer** (use case 1) | Age-95 test, CPF share, HDB loan limit and loan tenure for your inputs; the lease premium in each shortlisted town with a chart, scatter plot and CSV export; an AI explanation of your specific result. |
| **Ask Runway** (use case 2) | A retrieval-augmented assistant over 32 official documents. Cites passages, declines advice and prompt-injection attempts, and can use your Lease Explorer numbers as context. |
| **Safeguards** | The AI never calculates: figures come from code, and explanations containing a number the code didn't produce are rejected. Password-protected access. |
"""
)

st.markdown("### Data sources")
st.markdown(
    f"**Transactions:** {meta['rows']:,} HDB resale records, {meta['first_month']} to {meta['last_month']}, "
    "published by HDB on [data.gov.sg](https://data.gov.sg/collections/189/view) under the Singapore Open Data "
    "Licence (five files, combined by the team)."
)
rows = []
for path in sorted(CORPUS_DIR.glob("*.md")):
    doc_meta, _ = parse_doc(path)
    rows.append({"Document": doc_meta["title"], "Publisher": doc_meta["publisher"], "Link": doc_meta["url"],
                 "Retrieved": doc_meta["retrieved"]})
docs = pd.DataFrame(rows).sort_values(["Publisher", "Document"])
st.markdown(f"**Rules library for Ask Runway:** {len(docs)} official and government documents.")
st.dataframe(docs, hide_index=True, width="stretch",
             column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")})

st.markdown(
    """
### Team Runway
Lynn Koh · Leong Soon Poh · Danish Syafiq · Max How

Runway is a Bootcamp learning project, not a financial service. Buyers should confirm their position with
CPF Board and their HDB Flat Eligibility (HFE) letter.
"""
)
footer()
