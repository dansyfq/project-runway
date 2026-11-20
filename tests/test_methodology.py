"""The Methodology page (/methodology, and its old address /how-it-works), the Ask chat download (one, merged from main's
and fix/methodology's) and question list, and the README's API and model usage section."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from runway import content
from runway.bridge import PAGES, handle
from runway.config import DEFAULT_CHAT_MODEL
from runway.agent import DEADLINE_SECONDS, MAX_STEPS
from runway.llm import AI_CALLS_PER_HOUR, EFFORT, MAX_TOKENS

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
NODE = shutil.which("node") or str(Path.home() / ".local/bin/node")
needs_node = pytest.mark.skipif(not (shutil.which("node") or Path(NODE).exists()), reason="needs Node.js")

# The items of the course brief (group of 4) the in-app requirements checklist answers, in order
BRIEF = ["RAG-based query", "Document management", "Vector store", "LangChain or similar", "Login with Admin and User roles",
         "Summarisation and export", "Question history", "Sample document set", "Public deployment",
         "API and model usage documented", "About Us and Methodology pages"]
# The earlier checklist's rows (main, before the merge) that are not one of the brief's items: kept, after them
EARLIER = ["Information from several official sources", "Personalised with non-identifying inputs",
           "Explanations and follow-up questions", "Text, tables, charts and forms", "At least two use cases", "Agent with tools",
           "Evaluation and monitoring", "One flowchart per use case", "Required disclaimer"]


def node_json(tmp_path, script):
    js = tmp_path / "methodology.js"
    js.write_text(script, encoding="utf-8")
    return json.loads(subprocess.run([NODE, str(js)], capture_output=True, text=True, check=True).stdout)


def js_function(name):
    start = GAME.index(f"function {name}(")
    return GAME[start:GAME.index("\n}\n", start) + 2]


def method_pages(tmp_path):
    """methodHtml() for a guest and for a logged-in user, run in Node with the page's own flowcharts and facts."""
    code = GAME[GAME.index("const FLOW_MAP = "):GAME.index("/* ---------- FAQ, Privacy Policy")]
    stubs = ("const SPAN='Jul–Sep 2026', NEWTAB=' (opens in a new tab)', S={age:30,avg:30};\n"
             "const calc=()=>({cap:495000}), exact=x=>'$'+x.toLocaleString('en-US');\nlet full=false; const FULL=()=>full;\n")
    return node_json(tmp_path, stubs + code + "\nconst guest=methodHtml(); full=true;\n"
                                              "console.log(JSON.stringify({guest, full: methodHtml()}));")


# ---------- /methodology and /how-it-works ----------

def test_both_addresses_are_pages_with_the_new_name():
    assert PAGES["methodology"] == "Methodology" and PAGES["how-it-works"] == "Methodology"
    table = GAME[GAME.index("RW.PATHS = {"):GAME.index("};", GAME.index("RW.PATHS = {"))]
    paths = dict(re.findall(r"'([^']*)': '([^']*)'", table))
    assert paths["methodology"] == paths["how-it-works"] == "more method"
    # Runway's own links use the first path for a screen, so /methodology must come first
    assert table.index("'methodology'") < table.index("'how-it-works'")
    # the old address stays in the address bar (an alias): no redirect, so Back never bounces back to it
    assert "RW.PATHS[RW.page] === key ? RW.page :" in GAME


@pytest.mark.parametrize("page", ["methodology", "how-it-works"])
def test_nav_accepts_both_addresses(page):
    assert handle({"id": "x", "type": "nav", "payload": {"page": page}}, {}, {}, None, None) == {"ok": True, "page": page}


@pytest.mark.parametrize("page", ["methodology", "how-it-works"])
def test_host_opens_both_addresses(monkeypatch, page):
    import streamlit as st
    import streamlit.components.v1 as components

    renders = []
    monkeypatch.setattr(st, "switch_page", lambda p: None)
    msg = {"id": "m-" + page, "type": "nav", "payload": {"page": page}}
    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: renders.append(kw) or msg)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert [r["page"] for r in renders] == ["", page]


def test_the_page_is_called_methodology_everywhere():
    assert "method:'Methodology'" in GAME  # SUBNAME: breadcrumbs
    assert "row('method','Methodology','How it works:" in GAME  # More, with the old name as its subtitle
    assert "['methodology', 'Methodology', 'how it works" in GAME  # site search finds it by either name
    assert 'data-go="methodology">Methodology</button>' in GAME  # landing page footer
    assert "data-go=\"how-it-works\"" not in GAME


def test_stored_edits_of_the_old_page_cannot_hide_the_new_one():
    """How it works was saved as method.full / method.brief; Methodology reads and saves new keys only."""
    assert "method:()=>'methodology.'+(FULL()?'full':'brief')" in GAME
    assert {"methodology.full", "methodology.brief"} <= content.PAGE_KEYS
    assert not {"method.full", "method.brief"} & content.PAGE_KEYS


# ---------- the page itself ----------

@needs_node
def test_guests_see_the_rag_pipeline_and_the_flowcharts(tmp_path):
    guest = method_pages(tmp_path)["guest"]
    assert "<h1>Methodology</h1>" in guest and "How it works:" in guest
    for words in ["How Ask Runway answers", "32 official documents", "160 words", "40 words", "BM25", "vector store",
                  "weighted reciprocal rank fusion", "FAISS index of bge-small-en-v1.5 embeddings", "TF-IDF vectors stand in", "LangChain retriever", "Anthropic SDK",
                  "Calculator tools", "a tool result", "numbered citations", "PBKDF2-SHA256", "Number guard", "Fallback",
                  "Insights", "Flowchart · Use case 1: Map", "Flowchart · Use case 2: Ask Runway",
                  "Flowchart · Use case 3: Lease explorer", "AI calls Runway's calculator tools"]:
        assert words in guest, words
    roles = re.search(r"<h2>Accounts</h2>(.*?)</table>", guest, re.S).group(1)
    assert all(f"<td>{r}</td>" in roles for r in ("Admin", "User", "Guest"))
    assert "Requirements checklist" not in guest


@needs_node
def test_checklist_names_each_item_of_the_brief(tmp_path):
    full = method_pages(tmp_path)["full"]
    section = re.search(r"<h2>Requirements checklist</h2>(.*?)</table>", full, re.S).group(1)
    assert "for a group of 4" in section
    brief, more = re.findall(r"<tbody>(.*?)</tbody>", section, re.S)
    assert re.findall(r"<tr><td>(.*?)</td>", brief) == BRIEF
    assert re.findall(r"<tr><td>(.*?)</td>", more) == EARLIER  # one table: the brief first, then the rest
    for words in ["Download this chat", "a text file", "Save shortlist as a file", "Your questions", "runway-hdb.streamlit.app",
                  "#api-and-model-usage", "FAISS index of bge-small-en-v1.5 embeddings", "ChatPromptTemplates", "Admin:", "User:",
                  "opens Insights", "admin and user log-ins"]:
        assert words in brief, words
    for words in ["3 calculator tools", "Insights (admin only)", "Lease explorer", "Notice"]:
        assert words in more, words
    assert "Markdown" not in section and "LangChain is not used" not in section
    assert "How Ask Runway answers" in full and "Test cases" in full and "Flowchart" in full


def test_retrieval_and_roles_are_described_in_one_place():
    """Only METHOD_FACTS names the retrieval stack and says whether LangChain is used, so a change to either is one edit.
    """
    start, end = GAME.index("const METHOD_FACTS = {"), GAME.index("const README_API")
    facts = GAME[start:end]
    page = GAME[GAME.index("function methodHtml(){"):GAME.index("/* ---------- FAQ, Privacy Policy")]
    page += GAME[GAME.index("const methodPipeline"):GAME.index("function methodHtml(){")]
    for words in ["TF-IDF", "FAISS", "bge-small", "cosine", "reciprocal rank", "ChatPromptTemplate", "Anthropic SDK"]:
        assert words in facts and words not in page, words
    assert "retrieval: 'Hybrid search: BM25 keyword ranking plus a vector store, fused by weighted reciprocal rank fusion'" in facts
    assert "vectors: 'a FAISS index of bge-small-en-v1.5 embeddings" in facts and "langchain: 'Built on LangChain core" in facts
    assert "PENDING" not in facts


# ---------- Ask: download this chat, your questions ----------

SAMPLE_CHAT = [
    {"me": True, "html": "How many years of lease do I need?"},
    {"html": "<p>You need a lease that lasts until the youngest buyer is 95 [1].</p><ul><li>Age 30: 65 years [2]</li></ul>"
             "<p class=\"small\">Numbers from Runway's calculator, not the AI.</p>",
     "src": [{"title": "Using CPF for a short lease", "publisher": "CPF Board", "url": "https://www.cpf.gov.sg/a"},
             {"title": "Resale flat lease", "publisher": "HDB", "url": "https://www.hdb.gov.sg/b"},
             {"title": "Using CPF for a short lease", "publisher": "CPF Board", "url": "https://www.cpf.gov.sg/a"}]},
    {"me": True, "skip": True, "html": "My NRIC is S•••••••D, can I buy?"},
    {"warn": True, "skip": True, "html": "<p>Please remove your NRIC, phone number or email. Runway never needs them.</p>"},
    {"me": True, "skip": True, "html": "Uploaded <b>notes.txt</b>"},
    {"me": True, "html": "Is my loan cut too?"},
    {"typing": True, "html": "<p class=\"small\">Checking the official documents…</p>"},
    {"html": "<p>Yes, the HDB loan is pro-rated too.</p>", "src": [], "open": True},
    {"sum": True, "html": "<p><b>In short:</b></p><ul><li>Lease must reach 95.</li><li>Loan is pro-rated.</li></ul>"},
]

NOTICE_STUB = "<p><b>IMPORTANT NOTICE:</b> A prototype.</p><p>Always consult with qualified professionals.</p>"

EXPECTED_TXT = """Runway: Ask Runway chat
Saved 20 November 2026, 3:04 pm

IMPORTANT NOTICE: A prototype.
Always consult with qualified professionals.

Question 1: How many years of lease do I need?

Answer:
You need a lease that lasts until the youngest buyer is 95 [1].
- Age 30: 65 years [2]
Sources:
- [1][3] CPF Board · Using CPF for a short lease: https://www.cpf.gov.sg/a
- [2] HDB · Resale flat lease: https://www.hdb.gov.sg/b

Question 2: Is my loan cut too?

Answer:
Yes, the HDB loan is pro-rated too.

Summary:
- Lease must reach 95.
- Loan is pro-rated.
"""

# plainLines() needs a DOM; in Node a few regular expressions do the same for this sample
TEXT_STUB = r"""const text = h => h.replace(/<p class="small">.*?<\/p>/g,'').replace(/<li>/g,'- ').replace(/<\/(p|li)>/g,'\n')
  .replace(/<[^>]+>/g,'').split('\n').map(x=>x.trim()).filter(Boolean).join('\n');"""


@needs_node
def test_chat_download_has_date_notice_answers_sources_and_summary_without_personal_details(tmp_path):
    """One download (main's downloadChat / chatText, fix/methodology's content): the date, the required notice, each
    question and answer with that answer's sources and links, the summary; what history() leaves out is left out."""
    got = node_json(tmp_path, f"const S={{chat:[]}}, NOTICE='', plainLines=x=>x;\n{js_function('chatText')}\n{TEXT_STUB}\n"
                              f"console.log(JSON.stringify(chatText({json.dumps(SAMPLE_CHAT, ensure_ascii=False)}, "
                              f"'20 November 2026, 3:04 pm', text, {json.dumps(NOTICE_STUB)})));")
    assert got == EXPECTED_TXT
    assert "NRIC" not in got and "notes.txt" not in got and "Checking" not in got and "Please remove" not in got


def test_chat_download_defaults_to_the_open_chat_and_the_real_notice():
    head = js_function("chatText").split("\n", 1)[0]
    assert "chat=S.chat" in head and "text=plainLines" in head and "notice=NOTICE" in head and "toLocaleString('en-SG'" in head


def test_one_chat_download_made_in_the_browser_and_shown_once_there_is_a_question():
    save = js_function("downloadChat")
    assert "new Blob([chatText()],{type:'text/plain;charset=utf-8'})" in save and "RW.send" not in save
    assert "a.download=`runway_chat_${day}.txt`" in save
    chat = js_function("renderChat")
    assert 'qs.length?`<button class="chip" type="button" id="chatDl"' in chat and ">Download this chat</button>" in chat
    assert "const dl=$('#chatDl'); if(dl) dl.onclick=downloadChat;" in chat
    # one control and one implementation: the two branches' versions were merged, not both kept
    assert GAME.count('id="chatDl"') == 1 and GAME.count("Download chat<") == 0 and "dlBtn" not in GAME
    assert "function saveChat" not in GAME and "function chatMd" not in GAME and "type:'text/markdown" not in GAME
    assert "filter(([m])=>m.me&&!m.skip)" in chat  # the questions history() would send, no more
    assert "const history = (n=7) => S.chat.filter(m=>!m.typing&&!m.skip)" in GAME  # chatText skips exactly these
    assert "chat.filter(m=>!m.typing&&!m.skip)" in js_function("chatText")
    assert "pushBot({sum:true," in chat  # the summary is labelled in the file


def test_your_questions_list_opens_each_answer():
    markup = '<details class="more qhist" id="askHist" hidden><summary id="askHistSum">Your questions</summary>'
    assert markup in GAME
    chat = js_function("renderChat")
    assert 'id="cm${i}" tabindex="-1"' in chat and "data-hq" in chat and "t.focus({preventScroll:true})" in chat
    assert "`Your questions (${qs.length})`" in chat


def test_privacy_policy_says_the_download_stays_on_the_device():
    policy = GAME[GAME.index("function privacyHtml"):GAME.index("function termsHtml")]
    assert policy.count("Download this chat") == 1  # one bullet
    assert '"Download this chat" makes a text file' in policy and "Nothing is sent to Runway's server for it" in policy


# ---------- README ----------

def test_readme_documents_the_api_and_model_usage():
    section = README[README.index("## API and model usage"):]
    section = " ".join(section[:section.index("\n## ", 5)].split())
    for words in [f"`{DEFAULT_CHAT_MODEL}`", "`ANTHROPIC_API_KEY`", "`ANTHROPIC_MODEL`", f"`max_tokens` {MAX_TOKENS:,}",
                  f"effort `{EFFORT}`", f"{AI_CALLS_PER_HOUR} AI calls an hour", f"at most {MAX_STEPS} model turns",
                  f"after {DEADLINE_SECONDS} seconds", "3 calculator tools", "no API call", "edge-tts", "runway/llm.py",
                  "never talks to Anthropic"]:
        assert words in section, words
    assert "custom Streamlit component" in " ".join(README[:README.index("## What's in the app")].split())
