"""Use case 2: Ask Runway, a RAG assistant over official CPF, HDB and MND documents."""

import streamlit as st

from runway.ui import llm, retriever, sources_list

SUGGESTIONS = [
    "Can I still use CPF for an old flat?",
    "Is my HDB loan cut too?",
    "How long can my loan be?",
    "What changes if my partner is the younger buyer?",
    "What does the 20-year minimum lease mean?",
    "How long is the HFE letter valid?",
]

st.title("Ask Runway")
st.markdown("Plain answers from CPF Board, HDB and Ministry documents, with the source each time.")

bot, index = llm(), retriever()
if not bot.available:
    st.caption("AI answers are off. Runway shows the matching official passages instead.")
elif getattr(index, "embed_error", None):
    st.caption("Using keyword search for documents right now.")

facts = st.session_state.get("explorer_facts")
use_facts = False
if facts:
    use_facts = st.toggle(
        f"Use the flat I'm looking at (youngest buyer {facts['Youngest buyer age']}, "
        f"{facts['Remaining lease (years)']} years left)",
        value=True,
    )

history = st.session_state.setdefault("chat", [])
for turn in history:
    with st.chat_message(turn["role"], avatar=":material/person:" if turn["role"] == "user" else ":material/flight_takeoff:"):
        st.markdown(turn["content"])
        if turn.get("sources"):
            with st.expander(f"Where this comes from ({len(turn['sources'])})"):
                sources_list(turn["sources"])

cols = st.columns(2)
for i, q in enumerate(SUGGESTIONS if not history else SUGGESTIONS[:4]):
    if cols[i % 2].button(q, key=f"s{i}", width="stretch"):
        st.session_state["pending"] = q
        st.rerun()
if history and st.button("Sum up this chat", width="stretch", icon=":material/summarize:"):
    st.session_state["summary"] = bot.summarise(history)

if st.session_state.get("summary") and history:
    with st.container(border=True):
        st.markdown("**Summary of this chat**")
        st.markdown(st.session_state["summary"])

question = st.chat_input("Type your question") or st.session_state.pop("pending", None)
if question:
    question = question[:1000]
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(question)
    situation = "; ".join(f"{k}: {v}" for k, v in facts.items() if k != "Lease premium by town") if use_facts else ""
    # Retrieve on the question plus the last user turn, so short follow-ups keep their topic.
    previous = next((t["content"] for t in reversed(history) if t["role"] == "user"), "")
    sources = index.search(f"{previous} {question}", k=5)
    with st.chat_message("assistant", avatar=":material/flight_takeoff:"), st.spinner("Checking the official documents..."):
        answer = bot.answer(question, sources, history=[{"role": t["role"], "content": t["content"]} for t in history],
                            situation=situation)
        st.markdown(answer.text)
        offline = not bot.available or answer.error
        if answer.error:
            st.warning(f"The AI service didn't respond ({answer.error[:120]}), so here are the source passages.")
        if answer.sources:
            with st.expander(f"Where this comes from ({len(answer.sources)})", expanded=bool(offline)):
                sources_list(answer.sources)
                if offline:
                    for i, c in enumerate(answer.sources, start=1):
                        st.markdown(f"**[{i}]** {c.text}")
    history += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer.text, "sources": answer.sources},
    ]
    st.session_state.pop("summary", None)

if history and st.button("Clear conversation", icon=":material/delete:"):
    st.session_state["chat"] = []
    st.session_state.pop("summary", None)
