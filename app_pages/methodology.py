import json
from pathlib import Path

import pandas as pd
import streamlit as st

from runway.config import DEFAULT_CHAT_MODEL, DEFAULT_EMBED_MODEL
from runway.ui import disclaimer, footer

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval_results.json"

st.title("Methodology")
disclaimer()

st.markdown(
    """
### Overall data flow
Two kinds of data feed Runway, and they are kept apart on purpose: **numbers** come from transaction records and
ordinary arithmetic; **words** (rules and explanations) come from official documents through the LLM.
"""
)
st.graphviz_chart(
    """
digraph {
  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#f3f6f8", color="#9aa5ad", fontname="Helvetica"];
  csv [label="5 HDB resale CSVs\\n(data.gov.sg, 1990-2026)"]; build [label="build_dataset.py\\nclean, combine,\\nremaining lease"];
  pq [label="resale.parquet\\n986,090 rows", fillcolor="#e3eef1"];
  web [label="32 official pages\\nCPF, HDB, MND, IRAS"]; corpus [label="data/corpus/*.md\\nwith source URL"];
  chunks [label="349 passages\\nBM25 + embeddings", fillcolor="#e3eef1"];
  le [label="Lease Explorer", fillcolor="#fdf1df"]; ask [label="Ask Runway", fillcolor="#fdf1df"];
  csv -> build -> pq -> le; web -> corpus -> chunks -> ask; chunks -> le [label="rule passages"];
}
"""
)

st.markdown("### Use case 1: Lease Explorer")
st.graphviz_chart(
    """
digraph {
  node [shape=box, style="rounded,filled", fillcolor="#f3f6f8", color="#9aa5ad", fontname="Helvetica"];
  in [label="User inputs\\ntowns, flat type, buyer ages,\\nremaining lease, price", shape=parallelogram, fillcolor="#fdf1df"];
  rule [label="cpf_rules.py\\nlease + age >= 95?"]; full [label="CPF up to 100% of\\nValuation Limit"];
  pro [label="Pro-rate:\\n(lease - 20) / (95 - age - 20)"]; none [label="Lease <= 20 years:\\nno CPF"];
  ltv [label="HDB loan limit = 75% x share\\nTenure = min(25, 65 - avg age, lease - 20)"];
  fit [label="lease_data.py\\nper town: log($/sqm) ~ lease\\n(OLS, 95% range)"];
  charts [label="Verdict, metrics,\\nbar chart, scatter, CSV"];
  facts [label="Facts dictionary\\n(only computed numbers)"];
  ret [label="Retrieve rule passages"]; gpt [label="LLM explains\\n(temperature 0)"];
  guard [label="Number guard:\\nany figure not in facts?", shape=diamond];
  out [label="Explanation\\nwith citations", fillcolor="#e3eef1"]; tmpl [label="Template explanation\\nfrom facts only", fillcolor="#e3eef1"];
  in -> rule; rule -> full [label="yes"]; rule -> pro [label="no, lease > 20"]; rule -> none [label="lease <= 20"];
  full -> ltv; pro -> ltv; none -> charts; ltv -> charts; in -> fit -> charts;
  ltv -> facts; fit -> facts; facts -> gpt; ret -> gpt; gpt -> guard;
  guard -> out [label="no"]; guard -> tmpl [label="yes"];
}
"""
)

st.markdown("### Use case 2: Ask Runway")
st.graphviz_chart(
    """
digraph {
  node [shape=box, style="rounded,filled", fillcolor="#f3f6f8", color="#9aa5ad", fontname="Helvetica"];
  q [label="User question\\n(+ optional Lease Explorer facts)", shape=parallelogram, fillcolor="#fdf1df"];
  screen [label="Screen question", shape=diamond];
  dec [label="Polite decline + where\\nto get help (CPF / HDB)", fillcolor="#fbeceb"];
  search [label="Hybrid search over 349 passages\\nBM25 + embeddings, fused by RRF\\n(question + previous turn)"];
  top [label="Top 5 passages\\nnumbered [1]-[5]"];
  gpt [label="LLM answers ONLY from passages,\\ncites [n], no new figures,\\nlast 3 exchanges as memory"];
  out [label="Answer + expandable\\nsource links", fillcolor="#e3eef1"];
  q -> screen; screen -> dec [label="advice / injection /\\noff-topic"]; screen -> search [label="in scope"];
  search -> top -> gpt -> out;
}
"""
)

st.markdown(
    f"""
### Implementation details
- **App:** multi-page Streamlit app, password-protected. Passwords are stored only as salted PBKDF2-SHA256 hashes in
  Streamlit secrets; the seed script that creates demo accounts keeps plain passwords in a gitignored file.
- **Transaction data:** five HDB files combined into one Parquet file. Remaining lease at sale comes from HDB's own
  column (2015 onwards) or, for older records, 99 minus years since lease start (accurate to the year).
- **Lease premium:** for each town and flat type in the chosen period, an ordinary least squares fit of
  log(price per sqm) on remaining lease; the slope is turned into "% per extra year", with a 95% range.
  Towns with fewer than 100 sales, leases spanning under 15 years, or a negative slope are flagged and greyed out.
  This reproduces the proposal's Table 1 (4-room flats sold from 2024, e.g. Yishun 0.51%, Clementi 1.62%).
- **CPF rule:** the formula reproduces every worked example published by MND (May 2019, Annex B) and CPF Board,
  checked by automated tests: age 25 with 55 / 65 / 75 years left gives 70% / 90% / 100%.
- **LLM:** OpenAI `{DEFAULT_CHAT_MODEL}` for answers and explanations; `{DEFAULT_EMBED_MODEL}` for embeddings.
  Prompt engineering: strict system prompts (answer only from passages, cite, no advice, ignore embedded
  instructions), low temperature, and prompt chaining (retrieve, then answer; compute, then explain).
- **Retrieval:** documents split by heading into 160-word passages with 40-word overlap; BM25 and embedding
  rankings merged by reciprocal rank fusion. If the AI is unavailable, keyword search still works and the app
  shows the passages themselves.
"""
)

st.markdown("### Quality checks")
if EVAL_FILE.exists():
    results = json.loads(EVAL_FILE.read_text())
    s = results["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Test questions", s["total"])
    c2.metric("Right source in top 5", f"{s['retrieval_hits']}/{s['retrieval_total']}")
    c3.metric("Calculator figures correct", f"{s['figure_pass']}/{s['figure_total']}")
    c4.metric("Out-of-scope / injection declined", f"{s['decline_pass']}/{s['decline_total']}")
    if s.get("llm_total"):
        st.metric("LLM answers with citation and expected content", f"{s['llm_pass']}/{s['llm_total']}")
    else:
        st.caption("LLM answer checks were not run for this snapshot (no API key at evaluation time).")
    st.caption(f"Last run: {results['run_at']}. Re-run with `python eval/run_eval.py`.")
    st.dataframe(pd.DataFrame(results["cases"]), hide_index=True, width="stretch")
else:
    st.info("Evaluation results not generated yet. Run `python eval/run_eval.py`.")

st.markdown(
    """
### Data caveats shown to users
- **A pattern, not a cause.** Town figures compare price against lease within each town and flat type, but don't
  adjust for floor level, flat size, model or condition. Older flats differ from newer ones in more than lease.
- **Singapore-wide averages mislead,** because newer towns (Punggol, Sengkang) simply have longer leases. Figures
  are always shown by town.
- **Two dating systems.** Sales before March 2012 are dated by approval, later ones by registration, so the periods
  aren't one continuous series. Lease Explorer uses recent sales only.
- **Remaining lease for older records** is worked out from the lease start year, accurate to the year.
- **Loan limits change.** The 2019 documents use a 90% HDB loan limit; for resale applications from 20 August 2024
  HDB uses 75%. Runway uses 75% and says so.
- **Sale prices, not asking prices.** Records show what flats actually sold for.
"""
)
footer()
