"""Use case 2: Ask Runway, a RAG assistant over official CPF, HDB and MND documents."""

import streamlit as st

from runway.ui import disclaimer, footer, llm, retriever, sources_list

SUGGESTIONS = [
    "Why is my CPF use reduced if the lease doesn't cover me to 95?",
    "What changes if my partner is the younger buyer?",
    "What does the 20-year minimum lease mean?",
    "Can I use CPF to pay cash over valuation?",
    "How long is the HFE letter valid, and when do I need it?",
    "What is the Proximity Housing Grant?",
]

st.title("Ask Runway")
st.caption("Plain-English answers from official CPF Board, HDB and Ministry documents, with the source each time.")
disclaimer()

bot, index = llm(), retriever()
status = f"Search: {index.mode}. " + ("AI answers on." if bot.available else "AI answers offline: showing source passages only.")
if getattr(index, "embed_error", None):
    status += " (Embeddings unavailable, using keyword search.)"
st.caption(status)

facts = st.session_state.get("explorer_facts")
use_facts = False
if facts:
    use_facts = st.toggle(
        f"Use my Lease Explorer result (youngest buyer {facts['Youngest buyer age']}, "
        f"{facts['Remaining lease (years)']} years left)",
        value=True,
    )

history = st.session_state.setdefault("chat", [])
for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("sources"):
            with st.expander("Sources"):
                sources_list(turn["sources"])

if not history:
    st.markdown("**Try one of these:**")
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTIONS):
        if cols[i % 2].button(q, key=f"s{i}", width="stretch"):
            st.session_state["pending"] = q
            st.rerun()

question = st.chat_input("Ask about CPF, lease, HDB loans, grants or the resale process") or st.session_state.pop("pending", None)
if question:
    question = question[:1000]
    with st.chat_message("user"):
        st.markdown(question)
    situation = "; ".join(f"{k}: {v}" for k, v in facts.items() if k != "Lease premium by town") if use_facts else ""
    # Retrieve on the question plus the last user turn, so short follow-ups keep their topic.
    previous = next((t["content"] for t in reversed(history) if t["role"] == "user"), "")
    sources = index.search(f"{previous} {question}", k=5)
    with st.chat_message("assistant"), st.spinner("Checking the official documents..."):
        answer = bot.answer(question, sources, history=[{"role": t["role"], "content": t["content"]} for t in history],
                            situation=situation)
        st.markdown(answer.text)
        offline = not bot.available or answer.error
        if answer.error:
            st.warning(f"The AI service didn't respond ({answer.error[:120]}), so here are the source passages.")
        if answer.sources:
            with st.expander("Sources", expanded=bool(offline)):
                sources_list(answer.sources)
                if offline:
                    for i, c in enumerate(answer.sources, start=1):
                        st.markdown(f"**[{i}]** {c.text}")
    history += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer.text, "sources": answer.sources},
    ]

if history and st.button("Clear conversation"):
    st.session_state["chat"] = []
    st.rerun()

footer()
