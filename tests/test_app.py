"""The Streamlit host and the interface file."""

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from runway.cpf_rules import cpf_share, flat_money
from runway.game_data import load_game_data, load_towns
from runway.rag import parse_doc

ROOT = Path(__file__).resolve().parent.parent
GAME = (ROOT / "runway_game" / "index.html").read_text(encoding="utf-8")
MAP = json.loads((ROOT / "data" / "game" / "map.json").read_text())
NODE = shutil.which("node") or str(Path.home() / ".local/bin/node")
needs_node = pytest.mark.skipif(not (shutil.which("node") or Path(NODE).exists()), reason="needs Node.js")
DEMO_WORDS = ("demo sign-in", "mockup", "scripted", "try it now", "live app", "runway2026")


def fake_component(monkeypatch, msg):
    """Stand in for the interface: record the args of each render, send msg back."""
    import streamlit.components.v1 as components

    renders = []

    def render(**kw):
        renders.append(kw)
        return msg

    monkeypatch.setattr(components, "declare_component", lambda *a, **k: render)
    return renders


def test_host_runs_for_a_guest(monkeypatch):
    renders = fake_component(monkeypatch, None)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert "user" not in at.session_state
    assert [r["page"] for r in renders] == [""]  # the home page, and the interface is told so


def test_nav_message_switches_the_page(monkeypatch):
    """The reply is recorded and st.switch_page reruns on /ask; the same component is told the new page."""
    import streamlit as st

    public = []  # st.switch_page would add a second history entry
    monkeypatch.setattr(st, "switch_page", public.append)
    renders = fake_component(monkeypatch, {"id": "n1", "type": "nav", "payload": {"page": "ask"}})
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1] == {"id": "n1", "value": {"ok": True, "page": "ask"}}
    assert [r["page"] for r in renders] == ["", "ask"] and public == []
    assert {r["key"] for r in renders} == {"runway"}  # one key: the browser keeps the same interface


def test_nav_still_switches_if_streamlit_internals_change(monkeypatch):
    """app.switch_page falls back to st.switch_page when the rerun internals it borrows are gone."""
    import streamlit.runtime.scriptrunner as scriptrunner

    import streamlit as st

    monkeypatch.delattr(scriptrunner, "RerunData")
    used, public = [], st.switch_page
    monkeypatch.setattr(st, "switch_page", lambda page: used.append(page.url_path) or public(page))
    renders = fake_component(monkeypatch, {"id": "n3", "type": "nav", "payload": {"page": "about"}})
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert used == ["about"] and [r["page"] for r in renders] == ["", "about"]


def test_unknown_nav_page_stays_put(monkeypatch):
    renders = fake_component(monkeypatch, {"id": "n2", "type": "nav", "payload": {"page": "../secrets"}})
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1] == {"id": "n2", "value": {"ok": False, "error": "unknown page"}}
    assert {r["page"] for r in renders} == {""}


def test_interface_knows_every_page():
    """The interface's path table (RW.PATHS) has exactly the pages Python serves."""
    from runway.bridge import PAGES

    table = GAME[GAME.index("RW.PATHS = {"):GAME.index("};", GAME.index("RW.PATHS = {"))]
    assert re.findall(r"'([^']*)':", table) == list(PAGES)


@pytest.mark.parametrize("msg", [["not", "a", "dict"], "text", {"id": ["unhashable"], "type": "ask"}])
def test_host_ignores_malformed_messages(monkeypatch, msg):
    import streamlit.components.v1 as components

    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: msg)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception


def test_host_always_replies_even_if_handle_fails(monkeypatch):
    """No reply means the interface waits 90 s; any unexpected error must still answer the message."""
    import streamlit.components.v1 as components

    import runway.bridge

    def boom(*_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: {"id": "m1", "type": "ask"})
    monkeypatch.setattr(runway.bridge, "handle", boom)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1] == {"id": "m1", "value": {"ok": False, "error": "Something went wrong. Try again."}}


def test_game_data_has_every_town_with_a_photo_and_credit():
    data = load_game_data()
    towns = {t["id"] for t in data["M"]["towns"]}
    assert len(towns) == 26 and set(data["PHOTOS"]) == towns
    assert all("Wikimedia Commons" in p["credit"] and p["img"].startswith("data:image/jpeg") for p in data["PHOTOS"].values())
    assert all(p["url"].startswith("https://commons.wikimedia.org/wiki/File:") for p in data["PHOTOS"].values())  # Sources links each
    assert {"roads", "stops", "am"} <= set(data["F"])


def test_interface_has_no_mockup_wording_or_built_in_accounts():
    visible = re.sub(r"/\*.*?\*/", "", GAME, flags=re.S).lower()
    for word in DEMO_WORDS:
        assert word not in visible, word
    assert "USERS=" not in GAME


def test_landing_page_has_required_notice_and_entry_points():
    assert GAME.count("NOT intended for real-world usage") >= 2  # landing page (main page) and About Us
    assert 'id="scrLanding"' in GAME and 'data-go="map"' in GAME and "data-login" in GAME
    assert 'id="loginOverlay"' in GAME


@pytest.mark.skipif(not (shutil.which("node") or Path.home().joinpath(".local/bin/node").exists()),
                    reason="needs Node.js")
def test_interface_calculator_matches_python_rules(tmp_path):
    """The map's in-browser calculator must give the same numbers as runway/cpf_rules.py."""
    calc = GAME[GAME.index("function calc(price, lease){"):GAME.index("const VTXT = ")]
    landing = GAME[GAME.index("function landingShare(age, lease){"):GAME.index("window.landingShare")]
    cases = [(p, lease, age, avg) for p in (300_000, 550_000) for lease in (15, 20, 20.5, 21, 45, 58, 58.75, 65, 66.6, 74.99, 75, 95)
             for age, avg in ((21, 21), (25, 25), (28, 30), (45, 50), (70, 70), (74, 74))]
    script = (f"let S={{age:0,avg:0,oa:0,oaSet:false}};\n{calc}\n{landing}\n"
              f"const out={json.dumps(cases)}.map(([p,l,a,v])=>{{S.age=a;S.avg=v;const r=calc(p,l);"
              f"return [r.cap,r.loan,r.tenure,r.monthly,r.cashLife,landingShare(a,l)];}});\n"
              f"console.log(JSON.stringify(out));")
    js = tmp_path / "calc.js"
    js.write_text(script)
    node = shutil.which("node") or str(Path.home() / ".local/bin/node")
    results = json.loads(subprocess.run([node, str(js)], capture_output=True, text=True, check=True).stdout)
    for (price, lease, age, avg), (cap, loan, tenure, monthly, cash, share) in zip(cases, results):
        assert share == pytest.approx(cpf_share(age, lease)), ("landing", lease, age)
        m = flat_money(price, lease, [age, 2 * avg - age], 0)
        assert cap == pytest.approx(m.cpf_cap), (price, lease, age)
        assert loan == pytest.approx(m.loan_max), (price, lease, age)
        assert tenure == pytest.approx(m.tenure), (price, lease, age)
        assert monthly == pytest.approx(m.monthly, rel=1e-6), (price, lease, age)
        assert cash == pytest.approx(m.cash_on_top), (price, lease, age)


def node_json(tmp_path, script):
    js = tmp_path / "landing.js"
    js.write_text(script)
    return json.loads(subprocess.run([NODE, str(js)], capture_output=True, text=True, check=True).stdout)


def landing_verdicts(tmp_path, cases):
    code = GAME[GAME.index("function landingShare(age, lease){"):GAME.index("window.landingVerdict")]
    return node_json(tmp_path, f"const window={{}};\n{code}\n"
                               f"console.log(JSON.stringify({json.dumps(cases)}.map(([a,l])=>landingVerdict(a,l))));")


def years(n):
    return "1 year" if n == 1 else f"{n} years"


@needs_node
def test_landing_verdict_matches_python_rules(tmp_path):
    """Every age 21-85 and lease 1-99: the landing verdict gives runway/cpf_rules.py's numbers."""
    cases = [(age, lease) for age in range(21, 86) for lease in range(1, 100)]
    labels = {"none": "No CPF", "full": "Full CPF", "part": "CPF pro-rated"}
    for (age, lease), v in zip(cases, landing_verdicts(tmp_path, cases)):
        share, needed = cpf_share(age, lease), 95 - age
        status = "none" if share == 0 else "full" if share == 1 else "part"
        assert (v["status"], v["label"]) == (status, labels[status]), (age, lease)
        assert v["line"] == f"Remaining lease {years(lease)} · {years(needed)} to 95", (age, lease)
        # JS Math.round sends halves up; Python's round() sends them to the even number
        assert v["pct"] == math.floor(share * 100 + 0.5), (age, lease)
        assert v["loan"] == (0 if age >= 65 else math.floor(75 * share + 0.5)), (age, lease)
        assert v["cover"] == math.floor(min(lease / needed, 1) * 100 + 0.5), (age, lease)


@needs_node
def test_landing_verdict_sentences(tmp_path):
    no_loan = "An HDB loan is not possible from age 65, because it must be repaid by then."
    expected = {
        (52, 55): "The flat has 55 lease years left — the youngest buyer turns 95 in 43 years. With 12 years to spare, "
                  "CPF can be used up to the Valuation Limit, and the HDB loan is up to 75%.",
        (52, 44): "The flat has 44 lease years left — the youngest buyer turns 95 in 43 years. With 1 year to spare, "
                  "CPF can be used up to the Valuation Limit, and the HDB loan is up to 75%.",
        (28, 58): "The flat has 58 lease years left — the youngest buyer turns 95 in 67 years. It falls 9 years short, "
                  "so CPF use is cut to about 81% of the Valuation Limit and the HDB loan to about 61%. The rest is cash.",
        (52, 42): "The flat has 42 lease years left — the youngest buyer turns 95 in 43 years. It falls 1 year short, "
                  "so CPF use is cut to about 96% of the Valuation Limit and the HDB loan to about 72%. The rest is cash.",
        (40, 20): "With 20 years or less of lease left, CPF can't be used for this flat and a cash payment is required.",
        (70, 30): "The flat has 30 lease years left — the youngest buyer turns 95 in 25 years. With 5 years to spare, "
                  f"CPF can be used up to the Valuation Limit. {no_loan}",
        (70, 22): "The flat has 22 lease years left — the youngest buyer turns 95 in 25 years. It falls 3 years short, "
                  f"so CPF use is cut to about 40% of the Valuation Limit. {no_loan} The rest is cash.",
    }
    got = dict(zip(expected, landing_verdicts(tmp_path, list(expected))))
    for case, sentence in expected.items():
        assert got[case]["sentence"].replace("’", "'") == sentence, case
    assert got[(52, 55)]["line"] == "Remaining lease 55 years · 43 years to 95"
    assert (got[(28, 58)]["pct"], got[(28, 58)]["loan"]) == (81, 61)
    assert got[(70, 30)]["loan"] == got[(70, 22)]["loan"] == 0


@needs_node
def test_landing_answers_quote_their_documents(tmp_path):
    """The worked example on the landing page quotes the official document word for word."""
    start = GAME.index("const LANDING_QA = ")
    qa = node_json(tmp_path, GAME[start:GAME.index("/* end LANDING_QA */", start)] + "\nconsole.log(JSON.stringify(LANDING_QA));")
    assert [x["q"] for x in qa] == ["Why is your CPF usage reduced?"]
    for x in qa:
        path = ROOT / "data" / "corpus" / f"{x['doc']}.md"
        meta, _ = parse_doc(path)
        assert " ".join(x["quote"].split()) in " ".join(path.read_text(encoding="utf-8").split()), x["doc"]
        assert (x["title"], x["publisher"], x["url"]) == (meta["title"], meta["publisher"], meta["url"])
        assert x["a"].strip() and x["quote"].strip() and "[" not in x["a"] + x["quote"], x["q"]


def test_landing_calculator_dropdowns_match_the_data():
    def options(select_id):
        select = re.search(rf'<select[^>]*\bid="{select_id}"[^>]*>(.*?)</select>', GAME, re.S)
        assert select, select_id
        return re.findall(r'<option[^>]*\bvalue="([^"]*)"', select.group(1))

    towns = options("lTown")
    assert towns[0] == "" and sorted(towns[1:]) == sorted(t["id"] for t in MAP["towns"])
    assert options("lType") == ["4-room", "3-room", "5-room", "Executive"]
    assert set(options("lType")) <= {x[1] for r in MAP["recent"] for x in r["x"]}


def test_landing_town_cards_match_the_data():
    """The town cards' numbers are written into the page, so a data refresh must not leave them stale."""
    pct = {t["id"]: t["pct"] for t in MAP["towns"]}
    sales = {t["id"]: t["n"] for t in load_towns()}
    assert "−1.5% per missing year" in GAME and round(pct["TOA PAYOH"], 1) == 1.5
    assert "+0.9% per extra year" in GAME and round(pct["WOODLANDS"], 1) == 0.9
    assert "178 resales Jul–Sep 2026" in GAME and sales["SEMBAWANG"] == 178
    assert {x[0] for r in MAP["recent"] for x in r["x"]} == {"2026-07", "2026-08", "2026-09"}
    assert "≈ 11% lower price" in GAME and round((1 - (1 + pct["SEMBAWANG"] / 100) ** -10) * 100) == 11
    assert 2.5 < pct["TOA PAYOH"] / pct["YISHUN"] < 3.2  # "nearly three times"
    assert "23 more towns" in GAME and len(pct) - 3 == 23


def test_landing_look_and_copy():
    for text in ('data-photo="punggol.jpg"', 'data-photo="toapayoh.jpg"', "Less lease, less CPF:",
                 "what buyers need to know.", "not from the AI"):
        assert text in GAME, text
    # the closing "Have more questions?" band is gone: its "Start asking" only jumped back up to the hero's ask box
    for text in ("Have more questions? Ask KEY.", "Start asking", 'href="#lask"', "lband"):
        assert text not in GAME, text
    # the system font everywhere; Google Fonts loads only Anton, for the RUNWAY wordmark
    assert re.findall(r'href="https://fonts\.googleapis\.com/css2\?([^"]*)"', GAME) == ["family=Anton&display=swap"]
    for text in ("IBM Plex", "--rust", "Special:FilePath", "One flat, two buyers", "ordinary way", "Plus+Jakarta+Sans",
                 "Plus Jakarta", "Source+Serif", "Source Serif"):
        assert text not in GAME, text
    assert "7a2e1d" not in GAME.lower()


def test_landing_photos_are_local_jpegs():
    """The home photos are embedded in the page (the host does not serve image files from the component folder);
    the embedded copy must be the file in runway_game/assets, byte for byte."""
    import base64

    for name in ("punggol.jpg", "toapayoh.jpg"):
        data = (ROOT / "runway_game" / "assets" / name).read_bytes()
        assert data[:2] == b"\xff\xd8", name
        embedded = re.search(rf'data-photo="{name}" src="data:image/jpeg;base64,([A-Za-z0-9+/=]+)"', GAME)
        assert embedded and base64.b64decode(embedded.group(1)) == data, name
    assert not re.search(r'src="assets/[^"]+\.(jpg|jpeg|png|webp)"', GAME)


def test_hdb_loan_limit_line_matches_hdb_and_the_rules():
    """The line under the verdict tiles quotes today's HDB limit, from HDB's own page, and equals cpf_rules.HDB_LTV."""
    from runway.cpf_rules import HDB_LTV

    meta, _ = parse_doc(ROOT / "data" / "corpus" / "hdb-housing-loan-from-hdb.md")
    corpus = " ".join((ROOT / "data" / "corpus" / "hdb-housing-loan-from-hdb.md").read_text(encoding="utf-8").split())
    assert "The 75% LTV applies to complete resale applications received by HDB on or after 20 August 2024" in corpus
    line = re.search(r'<p class="lnote" id="lLtvNote">(.*?)</p>', GAME, re.S).group(1)
    assert re.findall(r"(\d+)%", line) == [str(round(HDB_LTV * 100))] and "20 August 2024" in line
    assert f'href="{meta["url"]}"' in line and 'target="_blank"' in line
    assert "normally 75%" not in GAME and ">Online<" not in GAME


@needs_node
def test_sales_window_label_comes_from_the_data(tmp_path):
    """Map labels say the window the data holds (e.g. Jul–Sep 2026), worked out from the sales' own months."""
    from runway.game_data import recent_months

    start = GAME.index("function monthSpan(months){")
    fn = GAME[start:GAME.index("\n}", start) + 2]
    cases = [recent_months(), ["2026-09"], ["2025-11", "2026-01", "2025-12"], []]
    got = node_json(tmp_path, f"{fn}\nconsole.log(JSON.stringify({json.dumps(cases)}.map(monthSpan)));")
    assert got == ["Jul–Sep 2026", "Sep 2026", "Nov 2025–Jan 2026", ""]
    assert recent_months() == sorted({x[0] for r in MAP["recent"] for x in r["x"]})
    app = GAME[GAME.index("function startRunway("):GAME.index("/* Public price trends")]
    assert "Jul–Sep" not in app and "Jul to Sep" not in app  # every map label uses SPAN


def test_landing_stats_match_the_dataset():
    meta = json.loads((ROOT / "data" / "dataset_meta.json").read_text())
    assert f"<b>{meta['rows']:,}</b><span>Resale records</span>" in GAME
    assert f"<b>{meta['first_month'][:4]}–{meta['last_month'][:4]}</b>" in GAME
    mon = "JanFebMarAprMayJunJulAugSepOctNovDec"[3 * int(meta["last_month"][5:]) - 3:][:3]  # scripts/refresh_data.py moves it
    assert f"{meta['rows']:,} sales from {meta['first_month'][:4]} to {mon} {meta['last_month'][:4]}" in GAME


def test_town_lease_effect_window_is_jan_2024_to_the_last_month():
    """map.json's per-town lease effect (pct) came from the design hand-off without its script. Refitting it shows the
    window the methodology states: same town, same flat type, same month, sales from Jan 2024 to the map's last month
    (map.json is not refreshed with resale.parquet, so the window ends where the map's own sales end)."""
    import numpy as np
    import pandas as pd

    df = pd.read_parquet(ROOT / "data" / "resale.parquet", columns=["month", "town", "flat_type", "remaining_lease", "price_psm"])
    end = pd.Timestamp(max(x[0] for r in MAP["recent"] for x in r["x"]))
    df = df[(df["month"] >= pd.Timestamp("2024-01-01")) & (df["month"] <= end)].copy()
    df["T"] = df["town"].astype(str).str.upper().str.replace(" / ", "/")
    df["y"], df["x"] = np.log(df["price_psm"].astype(float)), df["remaining_lease"].astype(float)
    g = df.groupby(["T", "month", df["flat_type"].astype(str)])
    df["yd"], df["xd"] = df["y"] - g["y"].transform("mean"), df["x"] - g["x"].transform("mean")
    fit = {t: (np.exp((s["xd"] * s["yd"]).sum() / (s["xd"] ** 2).sum()) - 1) * 100 for t, s in df.groupby("T")}
    for t in MAP["towns"]:
        assert fit[t["id"]] == pytest.approx(t["pct"], abs=0.006), t["id"]
    assert "same month (Jan 2024 to Sep 2026)" in GAME and "lease effect from Jan 2024 – Sep 2026 sales" in GAME


@needs_node
def test_faq_answers_rest_on_their_documents(tmp_path):
    """Each FAQ entry names a corpus document; its numbers come from that document or from cpf_rules."""
    from runway import cpf_rules

    start = GAME.index("const FAQ = ")
    faq = node_json(tmp_path, GAME[start:GAME.index("/* end FAQ */", start)] + "\nconsole.log(JSON.stringify(FAQ));")
    assert 8 <= len(faq) <= 10
    rules = {str(n) for n in (cpf_rules.COVER_TO_AGE, cpf_rules.MIN_LEASE, cpf_rules.MAX_TENURE, cpf_rules.TENURE_AGE_CAP,
                              round(cpf_rules.HDB_LTV * 100))}
    for x in faq:
        path = ROOT / "data" / "corpus" / f"{x['doc']}.md"
        meta, _ = parse_doc(path)
        assert (x["title"], x["publisher"], x["url"]) == (meta["title"], meta["publisher"], meta["url"]), x["q"]
        text = " ".join(path.read_text(encoding="utf-8").split())
        doc_numbers = {n.rstrip(",") for n in re.findall(r"\d[\d,]*", text)}
        for n in re.findall(r"\d[\d,]*", x["a"]):
            assert n.rstrip(",") in doc_numbers or n in rules, (x["q"], n)
        assert 2 <= len(re.findall(r"[.!?](\s|$)", x["a"])) <= 4, x["q"]  # 2 to 4 sentences
    by_q = {x["q"]: x for x in faq}
    worked = by_q["How is the pro-rated CPF amount worked out?"]
    assert all(f in worked["a"] for f in ("$550,000", "$495,000", "90%", "25-year-old", "65 years"))
    assert cpf_rules.cpf_share(25, 65) == pytest.approx(0.9) and 550_000 * cpf_rules.cpf_share(25, 65) == pytest.approx(495_000)
    loan = by_q["Is my HDB loan cut too?"]["a"]
    assert f"{round(cpf_rules.HDB_LTV * 100)}%" in loan and "20 August 2024" in loan
    assert "25 years, 65 minus the average age" in by_q["How long can my HDB loan be?"]["a"]
    assert "more than 20 years" in by_q["What is the 20-year minimum lease?"]["a"] and cpf_rules.cpf_share(30, 20) == 0
    assert len({x["q"] for x in faq}) == len(faq)


@needs_node
def test_upload_guard(tmp_path):
    start = GAME.index("const UPLOAD_TYPES")
    code = GAME[start:GAME.index("\n}", GAME.index("function uploadProblem", start)) + 2]
    cases = [["notes.txt", 100], ["HFE.PDF", 4_000_000], ["a.md", 5 * 1024 * 1024], ["b.text", 1], ["big.pdf", 5 * 1024 * 1024 + 1],
             ["photo.jpg", 10], ["noext", 10], ["x.pdf.exe", 10], ["sheet.docx", 10]]
    got = node_json(tmp_path, f"{code}\nconsole.log(JSON.stringify({json.dumps(cases)}.map(([n, s]) => uploadProblem(n, s))));")
    assert got[:4] == ["", "", "", ""]
    assert "5.0 MB" in got[4] and "up to 5 MB" in got[4]
    assert all("PDF, TXT, MD and TEXT files only" in m for m in got[5:])
    accept = re.search(r'<input type="file" id="upDoc" accept="([^"]+)"', GAME).group(1)
    assert accept.split(",") == [".pdf", ".txt", ".md", ".text"] and "up to 5 MB" in GAME
    assert "uploadProblem(f.name,f.size)" in GAME  # checked before the file is read


def js_function(name):
    """One top-level function from the page, from its first line to its closing brace."""
    start = GAME.index(f"function {name}(")
    return GAME[start:GAME.index("\n}\n", start) + 2]


@needs_node
def test_landing_faq_filter_matches_every_word_in_question_or_answer(tmp_path):
    cases = ["", "   ", "age-95", "LOAN 65", "loan zebra", "valuation limit", "partner younger"]
    got = node_json(tmp_path, f"{GAME[GAME.index('const FAQ = '):GAME.index('/* end FAQ */')]}\n{js_function('faqFilter')}\n"
                              f"console.log(JSON.stringify({json.dumps(cases)}.map(t => faqFilter(FAQ, t))));")
    faq = node_json(tmp_path, GAME[GAME.index("const FAQ = "):GAME.index("/* end FAQ */")] + "\nconsole.log(JSON.stringify(FAQ));")
    for text, hits in zip(cases, got):
        words = text.lower().split()
        assert hits == [i for i, x in enumerate(faq) if all(w in (x["q"] + " " + x["a"]).lower() for w in words)], text
    assert got[0] == list(range(len(faq))) and got[4] == [] and 0 < len(got[3]) < len(faq)


@needs_node
def test_landing_typed_cpf_amount_rounds_up_and_rejects_the_rest(tmp_path):
    cases = ["123,456.40", "123456", "$ 50,000", " 0 ", "2,000,000", "1999999.01", "2000000.01", "3000000",
             "", "abc", "-5", "1.2.3", "12e3", ".5", "100,000.00"]
    got = node_json(tmp_path, f"{js_function('oaAmount')}\nconsole.log(JSON.stringify({json.dumps(cases)}.map(oaAmount)));")
    assert got == [123457, 123456, 50000, 0, 2000000, 2000000, None, None, None, None, None, None, None, None, 100000]


def test_search_lists_every_page_by_its_name():
    from runway.bridge import PAGES

    block = GAME[GAME.index("const SEARCH = ["):GAME.index("const q = document.getElementById('navQ')")]
    found = re.findall(r"\['([^']*)', '([^']+)', '[^']*'\]", block)
    assert [p for p, _ in found] == [p for p in PAGES if p not in {"how-it-works", "ask"}]  # old addresses (Methodology, Ask KEY): aliases
    assert all(name == (PAGES[p] if p else "Home") for p, name in found)
    assert 'aria-label="Breadcrumb"' in GAME and "function crumbs(" in GAME


def test_home_numbers_reach_the_app_only_on_purpose():
    assert "RWLANDINGAGE" not in GAME  # no implicit hand-over; "See flats that pass" sends {town, ft, age}
    assert "RW.enter('map', {town: $('#lTown').value || null, ft: $('#lType').value, age: L.age})" in GAME
    assert 'id="lReset"' in GAME and 'id="dReset"' in GAME
    # the browser keeps two things, each under one key, and the Privacy Policy says so: Dark mode (local storage) and
    # this visit's details (session storage: age, CPF, town; never income or household)
    assert not re.search(r"indexedDB|document\.cookie", GAME)
    uses = re.findall(r"localStorage\.(\w+)\('([^']*)'", GAME)
    assert len(uses) == GAME.count("localStorage") == 2
    assert {k for _, k in uses} == {"runway-theme"} and {m for m, _ in uses} == {"getItem", "setItem"}
    suses = re.findall(r"sessionStorage\.(\w+)\('([^']*)'", GAME)
    assert len(suses) == GAME.count("sessionStorage") == 2
    assert {k for _, k in suses} == {"runway-details"} and {m for m, _ in suses} == {"getItem", "setItem"}
    assert "keeps two things in your browser" in GAME
    assert "under the name runway-theme" in GAME and "under the name runway-details" in GAME


def test_home_calculator_and_your_town_section_are_linked():
    # the calculator's town picker opens that town's card, and the town section repeats the calculator's numbers
    assert "sel.onchange = () => { if(sel.value) gotoTown(sel.value); else { syncHeart(); syncCompare(); } };" in GAME
    assert "async function gotoTown(id)" in GAME and "T.list.findIndex(t => t.id === id)" in GAME
    assert "if(window.RWYours) RWYours();" in GAME and "window.RWYours = syncYours;" in GAME
    assert 'id="lYours"' in GAME and "Your numbers from the calculator:" in GAME
    assert "landingVerdict(L.age, L.lease)" in GAME[GAME.index("function syncYours()"):GAME.index("window.RWYours = syncYours;")]
    # the two cards under the town on show compare the other towns with it, and the page says so
    assert 'id="lCmpHead"' in GAME and 'id="lCmpA"' in GAME and 'id="lCmpB"' in GAME
    assert "function syncCompare()" in GAME and "Compared with <b>${esc(cur.name)}</b>" in GAME
    assert "vs ${esc(cur.name)}" in GAME and "the town you picked" in GAME
    assert "syncHeart(); syncYours(); syncCompare();" in GAME
    # the written cards stay as the fallback until the towns load
    assert "<h3 class=\"lh3\">Woodlands</h3>" in GAME and "<h3 class=\"lh3\">Sembawang</h3>" in GAME
    # the stand-in used until the towns load is Toa Payoh's value in the data
    assert "{id: 'TOA PAYOH', name: 'Toa Payoh', pct: 1.5, low: false}" in GAME


def test_trends_follow_what_the_customer_entered():
    from runway.trends import BAND_STARTS

    assert f"const BAND_FROM = {BAND_STARTS};" in GAME  # the page's lease bands are the data's bands
    # one place to read it from: Trends' context(), fed by Home, the map and the links
    assert "function context()" in GAME and "function applyProfile()" in GAME and "if(key === st.key) return;" in GAME
    assert "RW.prof.set({pickTown:f.town, pickType:f.ft, lease:Math.floor(f.lease)});" in GAME
    assert "if(k === 'lease') RW.prof.set({lease: L.lease});" in GAME
    assert "RW.prof.set({pickTown: sel.value || null})" in GAME
    # links from Home and from a flat on the map, and the marker on the lease chart
    assert "const trendTownId = () => T.list ? T.list[T.i].id : (sel.value || 'TOA PAYOH');" in GAME  # the picked town, even before the towns load
    assert "RW.enter('trends', {town: trendTownId(), type: $('#lType').value, lease: L.lease})" in GAME
    assert 'id="lTrendLink"' in GAME and 'id="trendBtn"' in GAME and "go('trends',{town:f.town,type:f.ft,lease:f.lease})" in GAME
    assert "spec.mark" in GAME and "' (your lease)'" in GAME
    assert "the town, flat type and lease you last looked at" in GAME


def test_flat_result_shows_the_price_history_of_its_lease_band():
    # Trends' figures for the flat's town, type and lease band, on the sheet under the price check
    assert 'id="histChk"' in GAME and "function historyCheck(f)" in GAME and "historyCheck(f);" in GAME
    assert "window.RWTRENDS = {render, load, history};" in GAME and "function history(p)" in GAME
    assert "window.RWTRENDS.history({town:f.town,type:f.ft,lease:f.lease})" in GAME
    # it compares with the 80 to 89 band (index 4), or with 50 to 59 (index 1) for a flat that already has 80 or more
    from runway.trends import BAND_LABELS

    assert (BAND_LABELS[4], BAND_LABELS[1]) == ("80 to 89", "50 to 59")
    assert "const pos = bandOf(p.lease), ref = pos < 4 ? 4 : 1;" in GAME
    assert "Different flats, so not lease alone." in GAME and "go('trends',{town:f.town,type:f.ft,lease:f.lease})" in GAME


def test_ask_suggests_a_question_built_from_the_customers_details():
    assert "function profileSuggestion()" in GAME
    assert "What does ${Math.floor(p.lease)} years of lease left do to the price of a ${p.pickType} flat in ${t.name}?" in GAME
    assert "(mine&&fresh(mine)?[mine]:[])" in GAME  # first in the list, unless the customer already asked it
    # the question carries the figures itself: nothing extra about the customer is sent to the server
    assert "RW.send('ask', {q, facts: ctx ? flatFacts(ctx) : null, history: prior, age: (S.onbDone||S.ageSet) ? S.age : null, lang: questionLang(q) || S.lang})" in GAME
    assert "and a price lookup (the figures behind Trends)" in GAME


def test_a_clarifying_reply_is_not_rated_like_an_ai_answer():
    assert "if(!r.blocked && !r.offline && !r.clarify) b.fb = {q, v:null};" in GAME  # and it stays in the chat history


def test_every_built_in_suggestion_passes_the_topic_filter():
    from runway.llm import screen_question
    sugg = re.search(r"const SUGG=\[(.*?)\];", GAME, re.S).group(1)
    follow = re.search(r"const FOLLOW=\[(.*?)\]\];", GAME, re.S).group(1)
    key = re.search(r"const KEY_CHIPS = \[(.*?)\];", GAME, re.S).group(1)
    questions = re.findall(r"'([^']*)'", sugg) + re.findall(r",\s*'([^']*)'\]", follow) + re.findall(r"'([^']*)'", key)
    assert len(questions) >= 23
    assert [q for q in questions if screen_question(q)] == []


def test_key_is_an_assistant_button_that_asks_the_same_server_question():
    assert 'id="keyBtn"' in GAME and 'aria-controls="keyPanel"' in GAME and ">KEY</button>" in GAME
    assert 'id="keyPanel" role="dialog" aria-label="KEY, Runway\'s assistant" hidden' in GAME
    assert 'for="keyIn"' in GAME and 'id="keyForm"' in GAME
    # fixed at the bottom right, above the Streamlit badge, and the chat fits a phone
    assert ".keybtn{position:fixed;right:16px;bottom:calc(84px" in GAME and "width:min(380px,calc(100vw - 32px))" in GAME
    js = GAME[GAME.index("/* ---------- KEY: the assistant button"):GAME.index("/* ---------- your town: Toa Payoh")]
    # the same server question as the Ask page, with the same refusal of NRIC, phone and email before anything is sent
    assert "RW.send('ask', {q, facts: null, history: prior," in js and "lang: RW.lang || 'en'" in js
    assert js.index("if(personal(q))") < js.index("RW.send('ask'")
    assert "mine.skip = true" in js and "skip: true" in js  # questions with personal details never join the history
    # Escape closes it; the Ask page has its own chat
    assert "e.key === 'Escape'" in js and "target=\"_blank\"" not in js  # Escape closes; the pop-up has no document links, only a plain "Based on" line
    assert "document.getElementById('scrAsk')" in js and "kb.hidden = onAsk" in js


def test_home_ask_box_and_mic_ask_key():
    hero = GAME[GAME.index("$('#lAskForm').addEventListener"):GAME.index("/* ---------- your town")]
    assert "KEY.open(q)" in hero and "RW.enter('ask', q)" not in hero
    assert hero.count("KEY.open(q)") == 2  # typed and spoken


def test_when_you_sell_shows_a_lease_bar_with_the_rule_behind_why():
    i = GAME.index("function exitView(f){")
    view = GAME[i:GAME.index("function showResult(){", i)]
    assert "<summary>Why?</summary>" in view and "Rule: CPF Board" in view  # the sources stay, behind Why?
    assert 'role="img" aria-label="Bar:' in view and "need=95-EXIT" in view  # the bar and the years the example buyer needs
    assert "${full?'✓':'!'}" in view  # not colour alone
    assert "Full CPF for a buyer aged" not in view and "A short lease also limits your buyer. When do you sell?" in view
    assert "e.left<=20" in view  # 20 years or less keeps the plain message


def test_the_voice_is_not_slowed_down():
    # the server voice and every device voice (the mic greeting, read aloud, the voice test) run a little faster than
    # normal: they were set slower than normal (-8%, 0.92) and sounded too slow
    assert re.findall(r"u\.rate ?= ?([\d.]+)", GAME) == ["1", "1"]  # a voice on the device speaks at its own normal speed (1.1 was quick on a Mac)
    pack = (ROOT / "runway" / "voicepack.py").read_text(encoding="utf-8")
    assert 'rate="+10%"' in pack and 'rate="-' not in pack


def test_voice_clips_are_played_at_one_level():
    # a reply is several clips made separately; each is decoded and played at the gain that brings its speech to one level,
    # so the quiet first sentence is not followed by a louder second clip
    i = GAME.index("// Loudness matching: the voice makes each clip")
    block = GAME[i:GAME.index("async function speak(text,btn,lang='en')", i)]
    assert "const LEVEL=.15, GAIN_MIN=.5, GAIN_MAX=3, PEAK_MAX=.98;" in block
    assert "Math.max(GAIN_MIN, Math.min(GAIN_MAX, LEVEL/Math.sqrt(s/n), PEAK_MAX/peak))" in block  # never clips, never extreme
    assert "if(n<2000||!peak) return 1;" in block  # silence or a tiny clip is left alone
    # only the speech counts, not the pauses; a clip that cannot be decoded (or an audio context that cannot run) plays as it was
    assert "if(v>.02){s+=v*v; n++;}" in block and "if(AC.state!=='running') return null;" in block
    assert "gn.gain.value=clipGain(buf.getChannelData(0));" in block and "new Audio('data:audio/mpeg;base64,'+b64)" in block
    assert "AUD={pause(){try{src.stop();}catch(e){}}}" in block  # stopSpeak() still stops it
    assert "warmUp" not in block and "src.start();" in block  # no lead-in noise before the first clip: it made the voice worse


def test_the_reply_label_says_key_not_runway():
    # the assistant is called KEY: the small name above each reply on the Ask page says so (Runway stays the product name)
    assert '<span class="who">KEY</span>' in GAME and '<span class="who">Runway</span>' not in GAME


def test_key_popup_layout_placeholder_and_thumb_votes():
    # the header button and the quick actions stay on one line each (no clipped chips), text is one font, left aligned
    assert ".keypanel{font-family:var(--font-ui);text-align:left;position:fixed;" in GAME
    assert ".keyhead small{display:block;font-size:.75rem;" in GAME and "white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" in GAME  # the subtitle stays on one line
    assert ".keyhead .keyfull{flex:none;white-space:nowrap;" in GAME
    assert "keyActs" not in GAME and ".keyacts" not in GAME and "KEY_ACTIONS" not in GAME  # no shortcut buttons to other pages above the text box
    assert "height:min(600px,calc(100vh - 160px));" in GAME and "<small>CPF · HDB · MND documents</small>" in GAME  # room for the chat; the subtitle fits on one line
    assert 'id="keyFull" aria-label="Open the full Ask KEY page">Ask KEY</button>' in GAME  # a short label, so the subtitle is not cut off
    # the box says "Type your question": the header already says what KEY reads, and a long hint was cut off
    assert 'id="keyIn" type="text" autocomplete="off" maxlength="1000" placeholder="Type your question"' in GAME
    assert "const KEY_INTRO = 'Hello, I am KEY. How can I help?';" in GAME
    # Helpful / Not helpful are thumbs up and down icons with names for screen readers
    block = GAME[GAME.index("const THUMBS = {up:"):GAME.index("kl.innerHTML = all.map(")]
    assert "<svg width=\"20\" height=\"20\"" in block and 'aria-label="${t}" title="${t}"' in block and ">${t}</button>" not in block
    assert "data-kv=" in block and "aria-pressed=" in block  # the vote handler is unchanged


def test_home_has_no_back_to_top_arrow():
    # the arrow sat under the KEY button on Home; the other long pages keep it
    i = GAME.index("const toTop = document.getElementById('toTop'), LONG = new Set([")
    long_pages = GAME[i:GAME.index("]);", i)]
    assert "LONG = new Set(['methodology'," in long_pages and "[''" not in long_pages and "'', " not in long_pages
    for page in ("methodology", "faq", "sources", "privacy", "terms", "timeline"):
        assert f"'{page}'" in long_pages


def test_key_suggestions_look_unlike_messages_and_sources_are_tucked_away():
    # suggested questions: a caption and green outlined pills, so they cannot be mistaken for one of KEY's white message bubbles
    assert '<p class="keychips-h">Suggested questions</p><div class="keychips">' in GAME
    assert ".keychips button{border:1.5px solid var(--green-mid);border-radius:999px;background:transparent;" in GAME
    assert ".kmsg.bot{align-self:flex-start;background:var(--page);border:1px solid var(--line)}" in GAME  # the bubble they must differ from
    # no document links in the pop-up (the Home and Ask pages have them): one plain line says who the answer is based on and when
    ks = GAME[GAME.index("const kSources = src =>"):GAME.index("function kRender(){")]
    assert "<a " not in ks and "<details" not in ks and "href" not in ks and "noopener" not in ks
    assert "Based on ${esc(who.join(', '))}" in ks and "' · checked ' + esc(on)" in ks and "confirm on the official site." in ks
    assert ".ksrc a{" not in GAME and ".ksrc summary{" not in GAME and ".ksrc ul{" not in GAME  # the link styles are gone too


def test_crowded_map_labels_are_hidden_instead_of_overlapping():
    # a year label that would sit on another label or another diamond is hidden; it is recomputed after every draw and zoom
    i = GAME.index("function declutterLabels(){")
    fn = GAME[i:GAME.index("function applyLayers(){", i)]
    assert "LM.getZoom() < 16" in fn  # below zoom 16 the existing rule already hides every label
    assert "(y.p.ok - x.p.ok) || (y.p.n - x.p.n)" in fn  # matching flats first, then blocks with more sales
    assert "shown.some(q => hit(it.lab, q))" in fn and "items.some(o => o !== it && hit(it.lab, o.dia))" in fn  # clash with a label or a diamond
    assert "it.b.classList.toggle('lbl-off', clash)" in fn and ".pinwrap b.lbl-off{visibility:hidden}" in GAME
    assert "LM.on('zoomend',zoomStyle); LM.on('zoomend',declutterLabels);" in GAME
    assert "LY.sales.clearLayers(); PINS=[];" in GAME and "PINS.push({mk, ok, n:g.length});\n  });\n  declutterLabels();" in GAME


def test_voice_stays_female_and_answer_follows_the_question_language():
    # a device voice that is not male comes first (the voice pack is female), so a fallback does not turn the reply male
    assert "const vgender = v => FEMALE_V.test(v.name) ? 0 : MALE_V.test(v.name) ? 2 : 1;" in GAME
    assert "(vgender(a[0])===2)-(vgender(b[0])===2)||a[1]-b[1]||vgender(a[0])-vgender(b[0])" in GAME
    # a question in Chinese or Tamil letters is answered in that language, by KEY and on the Ask page, whatever the dropdown says
    assert "const questionLang = q => /[\\u3400-\\u9fff]/.test(String(q)) ? 'zh' : /[\\u0B80-\\u0BFF]/.test(String(q)) ? 'ta' : null;" in GAME
    assert "lang: questionLang(q) || S.lang});" in GAME and "lang: questionLang(q) || RW.lang || 'en', as: 'key'});" in GAME


def test_reply_audio_player_is_remade_after_the_mic_lets_go():
    # a Mac can change its audio rate while the mic is open; an idle player made before that is dropped when the mic ends
    assert "function freshAudio(){ if(AUD||!AC) return; const old=AC; AC=null;" in GAME
    end = GAME[GAME.index("function end(){\n    if(phase === 'done') return;"):]
    assert "if(vad) vad.stop();\n    if(typeof freshAudio === 'function') freshAudio();" in end[:400]


def test_first_spoken_answer_keeps_the_server_voice():
    # the first server-voice call of a session can fail fast: retried once, and woken while the question is being spoken
    assert "if(!b64&&i===0&&Date.now()-t0<4000){" in GAME and "b64=await packFetch(cs[0],lang);" in GAME
    assert "window._packWarm=1;packFetch(VOICE[S.lang].hi,S.lang);" in GAME


def test_town_comparison_says_it_in_plain_words():
    # "9 points less" is gone: each card says the drop for a 10-year-shorter lease, then smaller / bigger / as big as the shown town's
    assert "If the lease is 10 years shorter, the price per sqm is about <b class=\"lkey\">${d}%</b> lower in ${esc(t.name)}.${gap}" in GAME
    assert "That is a <b class=\"lkey\">${d < base ? 'smaller' : 'bigger'}</b> drop than in ${esc(cur.name)} (${base}%)." in GAME
    assert "That is <b class=\"lkey\">as big</b> a drop as in ${esc(cur.name)} (${base}%)." in GAME
    assert "points less" not in GAME and "a lease 10 years shorter lowers the price per sqm by about <b class=\"lkey\">${base}%</b>" in GAME


def test_key_numbers_in_the_town_section_are_bold():
    # the lease, the buyer's age, the verdict and the price drop stand out by weight (not colour alone); the town name stays escaped
    assert ".lkey{font-weight:700;color:var(--ink)}" in GAME and ".ltc.dark .lkey{color:var(--on-brand)}" in GAME
    yours = GAME[GAME.index("function syncYours()"):GAME.index("window.RWYours = syncYours;")]
    assert "p.innerHTML = " in yours and "p.textContent" not in yours
    assert "${k(yrs(L.lease))} of lease left and a youngest buyer aged ${k(L.age)}" in yours and "k('in full', 'ok')" in yours
    # the verdict also takes the app's full / part / none colours
    assert "k(v.pct + '%', 'part')" in yours and "k('cannot be used', 'no')" in yours
    assert ".lkey.ok{color:var(--ok)}" in GAME and ".lkey.part{color:var(--part)}" in GAME and ".lkey.no{color:var(--no)}" in GAME
    assert yours.count("esc(cur.name)") >= 2
    assert '<b class="lkey">${d}%</b> lower in ${esc(t.name)}' in GAME and '<b class="lkey">${d < base ? \'smaller\' : \'bigger\'}</b> drop' in GAME


def test_town_ask_buttons_are_answered_from_the_town_data():
    # "Ask about <town>" asks "Why do short leases cost more in <town>?": the documents have no town prices, so the AI answered
    # with a figure it could not source and the guard swapped in links. KEY now answers it from Runway's own town figures.
    assert "async function kTownAnswer(q){" in GAME and "why do short leases cost more in (.+?)" in GAME
    town = GAME[GAME.index("async function kTownAnswer(q){"):GAME.index("async function kAsk(q){")]
    assert "await loadTowns()" in town and "esc(t.name)" in town and "t.pct.toFixed(1)" in town and "tenYears(t.pct)" in town
    assert "too few recent resales" in town and "not a promise of what a flat will sell for" in town
    ask = GAME[GAME.index("async function kAsk(q){"):GAME.index("function keyOpen(q){")]
    assert "const town = await kTownAnswer(q);" in ask and ask.index("kTownAnswer(q)") < ask.index("RW.send('ask'")
    assert "skip: true" in ask[ask.index("kTownAnswer(q)"):ask.index("RW.send('ask'")]  # no AI call, no vote, not sent back as history


def test_one_h1_on_the_home_page_and_described_ratings():
    landing = GAME[GAME.index('<section class="screen" id="scrLanding">'):GAME.index("<!-- ONBOARDING -->")]
    assert len(re.findall(r"<h1\b", landing)) == 1
    assert "Lease matters: 2 of 3" not in GAME and 'aria-label="Lease effect on price in Sembawang: 2 out of 3, quite a lot"' in GAME
    assert not re.search(r"openSheet\(`[^`]*<h1", GAME)  # sheets use h2, so a page keeps one h1


def test_privacy_policy_matches_the_code():
    from runway import bridge

    config = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "gatherUsageStats = false" in config
    assert bridge.MAX_ATTEMPTS == 5 and bridge.LOCKOUT_SECONDS == 60 and "for one minute after five" in GAME
    assert "clean_history(payload.get(\"history\"), 6)" in (ROOT / "runway" / "bridge.py").read_text() and "up to six recent turns" in GAME
    assert "m.timer = setTimeout(() => finish(m.id, null, new Error('timeout')), 90000);" in GAME
    assert GAME.count("Last updated: ${LEGAL_DATE}") == 2 and "const LEGAL_DATE='20 November 2026';" in GAME
    assert "@" not in GAME[GAME.index("function privacyHtml"):GAME.index("// Case study:")]  # no contact address invented


def test_title_and_favicon():
    from runway.bridge import PAGES

    assert PAGES[""] == "Runway — HDB CPF age-95 checker"
    icon = (ROOT / "runway_game" / "assets" / "favicon.svg").read_text()
    assert icon.startswith("<svg") and "M50 15 85 50 50 85 15 50Z" in icon
    assert 'page_icon=str(HERE / "runway_game" / "assets" / "favicon.svg")' in (ROOT / "app.py").read_text()


@needs_node
def test_case_study_numbers_are_the_trends_cells(tmp_path):
    """The case study reads the same cells as Trends' lease chart: 4-room, 80-89 and 50-59 years left."""
    from runway.trends import load_trends

    d = load_trends()
    start = GAME.index("function caseNumbers(d){")
    code = GAME[start:GAME.index("\n}\n", start) + 2]
    (tmp_path / "d.json").write_text(json.dumps(d))
    got = node_json(tmp_path, f"{code}\nconst d=JSON.parse(require('fs').readFileSync({json.dumps(str(tmp_path / 'd.json'))}));"
                              "console.log(JSON.stringify(caseNumbers(d)));")
    hi, lo = d["bands"].index("80 to 89"), d["bands"].index("50 to 59")
    for row in got:
        psm, price = d["lease_psm"]["4 ROOM"][row["town"]], d["lease_price"]["4 ROOM"][row["town"]]
        assert row["psm"] == [psm[hi], psm[lo]] and row["price"] == [price[hi], price[lo]]
        assert row["gap"] == math.floor((psm[hi] - psm[lo]) / psm[hi] * 100 + 0.5)
    assert [r["town"] for r in got] == ["Toa Payoh", "Yishun"] and all(r["gap"] is not None for r in got)
    assert got[0]["gap"] > 2 * got[1]["gap"]  # the story the page tells: the short-lease gap is far wider in Toa Payoh


PERSONAL_CASES = [
    "My NRIC is S1234567D", "my nric is s 1234567 d", "NRIC S1234567-D", "Call 9123 4567", "Call 91234567", "Call 9123-4567",
    "Call +6591234567", "Call +65 9123 4567", "Call 6591234567", "Call ９１２３４５６７", "Email tan.ak@example.com", "Email tan＠example.com",
    "My budget is 1200000 for a 5-room flat, how much CPF can I use?", "The flat costs 1234567 dollars, how much CPF can I use?",
    "Can I use CPF for a $620,000 flat with 61 years of lease left?", "What is the 20-year minimum lease about?",
    "How much CPF for a flat sold in 2026 with 58 years left if I am 28?",
]


@needs_node
def test_personal_data_guard_matches_the_server(tmp_path):
    """The browser refuses an NRIC, phone number or email before a question leaves it; the server uses the same patterns."""
    from runway.llm import screen_question

    guard = GAME[GAME.index("const PERSONAL = "):GAME.index("// FAQ: each answer rests")]
    got = node_json(tmp_path, f"{guard}\nconsole.log(JSON.stringify({json.dumps(PERSONAL_CASES)}.map(q=>[personal(q),redact(q).txt])));")
    for text, (blocked, shown) in zip(PERSONAL_CASES, got):
        assert blocked == (screen_question(text) == "personal"), text
        assert blocked == ("[removed]" in shown), text
    assert any(b for b, _ in got) and not all(b for b, _ in got)


def test_interface_only_trusts_its_host_and_verified_scripts():
    listener = GAME[GAME.index("window.addEventListener('message', ev => {"):][:200]
    assert "if(ev.source !== window.parent) return;" in listener  # other windows can post messages too
    for url in re.findall(r"cdnjs\.cloudflare\.com/ajax/libs/[\w./-]+", GAME):
        assert url.count(".") and "@" not in url  # exact versions only
    loads = len(re.findall(r"loadScript\(V\+'[\w.]+\.js','sha512-[A-Za-z0-9+/=]{88}'\)", GAME))
    assert loads == 2 and "s.integrity = 'sha512-" in GAME and "loadScript(src,sri)" in GAME  # pdf.js ×2, Leaflet


def test_a_redeploy_rebuilds_the_cached_ai(monkeypatch):
    """Streamlit Cloud keeps the process across a redeploy: the AI objects are cached per code version, so a new
    version never calls an instance of the old class (the live Ask page returned empty answers when it did)."""
    import streamlit as st

    seen = []
    monkeypatch.setattr("runway.llm.LLM.answer", lambda self, *a, **k: seen.append(k.get("lang")) or __import__("runway.llm").llm.Answer(text="ok", sources=[]))
    fake_component(monkeypatch, {"id": "a1", "type": "ask", "payload": {"q": "Can I use CPF for an old flat?", "lang": "zh"}})
    st.cache_resource.clear()
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception and seen == ["zh"]
    assert at.session_state["replies"][-1]["value"]["text"] == "ok"
    app = (ROOT / "app.py").read_text()
    assert "llm(CODE, key_id())" in app and "retriever(CODE)" in app and 'glob("*.py")' in app


def test_a_redeploy_reloads_the_runway_modules():
    """Streamlit Cloud keeps the process across a redeploy: app.py forgets the old runway.* modules when the code's file
    time changes (not on the first run), and does so before importing them."""
    app = (ROOT / "app.py").read_text()
    purge = app.index('del sys.modules[_name]')
    assert app.index("CODE = max(") < purge < app.index("from runway.auth import")
    assert "_seen is not None and _seen != CODE" in app and "st._runway_code = CODE" in app


def test_ask_never_shows_an_empty_answer():
    """A failed server reply ({"ok": False, "error": ...}) has no text: the chat says so instead of an empty bubble."""
    ask = GAME[GAME.index("async function ask("):GAME.index("const SPK=")]
    assert "typeof r.text !== 'string'" in ask and ask.index("typeof r.text") < ask.index("md(r.text)")


def test_every_number_is_picked_with_one_slider():
    """Ages, lease years and text size: a native range slider each, with no wheel and no suggested-age chips beside it."""
    assert "wheelHtml" not in GAME and "bindWheel" not in GAME and 'role="listbox"' not in GAME
    assert "data-age=" not in GAME and "[25,30,35,40,50,60]" not in GAME and "Quick pick age" not in GAME
    for use in ("sliderHtml('aAge',", "sliderHtml('sAge',", "sliderHtml('dAw',", "sliderHtml('dVwh',", "sliderHtml('szW',", "sliderHtml('bAge',"):
        assert GAME.count(use) == 1, use
    assert 'id="lRange" class="lrange" type="range" min="1" max="99"' in GAME
    assert 'id="lAgeRange" class="lrange" type="range" min="21" max="85"' in GAME and '<label for="lAgeRange"' in GAME


def test_more_page_is_grouped_under_headings_with_no_guest_line():
    more = GAME[GAME.index("function renderMore("):GAME.index("function signOut(")]
    assert "guest" not in more.lower()
    assert [h for h in ("Your settings", "Guides", "About Runway", "Legal") if f"'{h}'" in more] == ["Your settings", "Guides", "About Runway", "Legal"]
    assert '<h2 class="label"' in more and 'aria-labelledby="mg-' in more
    listed = set(re.findall(r"row\('(\w+)'", more))
    names = re.search(r"const SUBNAME=\{(.*?)\};", GAME).group(1)
    assert listed == set(re.findall(r"(\w+):'", names))  # every More sub-page is in exactly one group


def test_trends_loading_message_prints_no_empty_slots():
    """replaceChildren turns a null argument into the text "null": the loading message once read "nullnull"."""
    msg = GAME[GAME.index("  function message(text, retry, detail){"):GAME.index("  // One request for the Trends data")]
    assert ".filter(Boolean)" in msg and "replaceChildren(...[" in msg


def test_upload_card_does_not_contradict_itself():
    """The file is opened in the browser, personal details go first, then four facts are picked out: one verb each."""
    card = GAME[GAME.index("Have a document? I can suggest towns."):GAME.index('id="chatLive"')]
    assert "removed first, before I look for anything else" in card and "I pick out your age, budget, CPF and flat type" in card
    assert "opened in this browser only and never uploaded" in card and " read" not in card


# ---- voice: one tap greets, then dictation that keeps going through pauses ----

def speech_text(tmp_path, cases):
    code = GAME[GAME.index("const joinSpeech = "):GAME.index("// Dictation:")]
    return node_json(tmp_path, f"{code}\nconsole.log(JSON.stringify({json.dumps(cases, ensure_ascii=False)}.map(speechText)));")


@needs_node
def test_voice_activity_hears_the_user_stop_over_background_noise(tmp_path):
    """vadStep, 50 ms frames in dBFS: speech is the speech band 12 dB over the room's learned level; it adapts to a noisy room."""
    code = GAME[GAME.index("const VAD_DB = "):GAME.index("function voiceActivity(")]
    script = code + """
const run = frames => { const st = {}; return frames.map(db => vadStep(st, db).speaking ? 1 : 0); };
const noise = (n, lvl) => Array.from({length: n}, (_, i) => lvl + (i % 3) - 1);  // a steady room with a little flutter
const quiet = noise(20, -55), loud = noise(40, -32);
console.log(JSON.stringify({
  quiet: run([...quiet, ...noise(10, -25), ...noise(20, -55)]),
  loud: run([...loud, ...noise(10, -12), ...noise(20, -32)]),
  roomOnly: run(noise(60, -32)),
  blip: run([...quiet, -25, -25, ...noise(10, -55)]),
}));"""
    got = node_json(tmp_path, script)
    def onoff(v):  # frame where speech starts and where it stops being heard
        on = v.index(1); return on, on + v[on:].index(0)
    assert onoff(got["quiet"]) == (22, 35)   # 150 ms to notice the voice; 300 ms after it ends, it has stopped
    assert onoff(got["loud"]) == (42, 55)    # same in a loud room (-32 dB of noise): the room's level is learned
    assert 1 not in got["roomOnly"][25:]     # a steady loud room alone is never taken for a voice once learned
    assert 1 not in got["blip"]              # a 100 ms knock is not speech


@needs_node
def test_speech_pieces_join_on_desktop_and_android(tmp_path):
    """Desktop Chrome gives one result per phrase; Android Chrome repeats everything said so far in each result."""
    got = speech_text(tmp_path, [
        ["can I use", " CPF for a 58 year lease"],                        # desktop: phrases add up
        ["what is", "what is the lease", "What is the lease rule"],       # Android: cumulative, never doubled
        ["how much can", "how match can I borrow", "how match can I borrow for a flat"],  # Android correcting a word
        ["我想", "我想问", "公积金"],                                          # Chinese: no spaces added
        ["", "  yes  ", ""],
        ["I want to buy a flat", "I want to know the lease rules"]])                   # desktop: a new phrase, not a repeat
    assert got == ["can I use CPF for a 58 year lease", "What is the lease rule", "how match can I borrow for a flat",
                   "我想问公积金", "yes", "I want to buy a flat I want to know the lease rules"]


def test_both_mics_dictate_through_pauses_and_greet_first():
    shared = GAME[GAME.index("/* ---------- voice, shared by the Home ask box"):GAME.index("// Slider for every number")]
    hero = GAME[GAME.index("  /* voice: as on the Ask page"):GAME.index("/* ---------- your town")]
    ask = GAME[GAME.index("/* ---------- voice: speech to text (in the answer language"):GAME.index("/* ---------- more ----------")]
    assert "r.continuous = true" in shared and "r.interimResults = true" in shared
    assert "const SILENCE_MS = 1000, HUSH_MS = 7000" in shared  # 1 s of quiet sends (it was 2.5 s, which felt slow); a person who says nothing still gets 7 s
    assert "10000);" not in hero + ask and "new SR(" not in hero + ask  # no fixed 10-second cut-off; one dictation for both
    # a session the browser ends restarts unless the user stopped, an error ended it, or it keeps ending at once
    assert "if(phase !== 'listen' || err) return end();" in shared and "if(quick >= 3) return end();" in shared
    assert "e.error !== 'no-speech'" in shared
    assert "MIC_FATAL = ['not-allowed', 'service-not-allowed', 'audio-capture', 'language-not-supported']" in shared
    # a press starts listening at once, inside the press: the mic no longer says "Hi, I'm KEY" first
    dict = shared[shared.index("function dictate(o){"):shared.index("addEventListener('pagehide'")]
    assert "greet(" not in dict and "let phase = 'listen'" in dict
    assert dict.index("try{ session(); }") < dict.index("tick = setInterval(")
    assert "r.onaudiostart = () => hearing('audio')" in dict and "o.input.placeholder = 'Starting the mic…'" in dict
    # the mouse press, not its release, starts it; the click that follows is swallowed
    assert "const MIC_BTNS = '#lMic, #keyMic, #micBtn';" in dict and "e.pointerType !== 'mouse'" in dict and "b.dataset.early" in dict
    # the user has stopped when their words and (on a computer) their voice over the room stopped; words heard while only
    # the room is audible are background and don't keep the mic open
    assert "const vad = voiceActivity();" in dict and "if(!background()){ said = Date.now(); mine = now; }" in dict
    assert "vad.heardVoice && !vad.speaking && Date.now() - vad.last > 500" in dict  # never before it has heard this user's voice
    assert "const got = (vad && vad.heardVoice ? mine : heard()).trim()" in dict
    assert "Math.max(said, vad && vad.speaking ? Date.now() : vad ? vad.last : 0)" in dict
    assert "if(vad) vad.stop();" in dict
    # ending with nothing heard says so instead of quietly switching off
    assert "I didn't hear anything. Tap the mic and speak, or type." in dict and "The voice service didn't answer." in dict
    assert "const base = o.input.value.trim()" in shared and "o.input.value = joinSpeech(base, mine);" in shared  # typed text is kept in front
    assert "dictate({btn: mic, input: inp, lang: RW.lang," in hero and "KEY.open(q)" in hero
    assert "dictate({btn:mb, input:$('#askIn'), lang:S.lang," in ask and "ask(v)" in ask
    assert "The microphone is blocked, so I could not hear you." in ask and "is not available in this browser" in ask
    # leaving the page or the screen stops the mic without asking
    assert "addEventListener('pagehide'" in shared and "'visibilitychange'" in shared
    assert "['#scrLanding', '#rwLoading']" in hero and "MIC.stop(false)" in hero and "MIC.stop(false)" in ask


def test_mic_greeting_in_each_answer_language():
    from runway.llm import LANGUAGES

    voice = GAME[GAME.index("const VOICE = {"):GAME.index("const TTS = ")]
    greet = {k: a or b for k, a, b in re.findall(r"(\w+): \{rec: '[\w-]+', hi: (?:\"([^\"]+)\"|'([^']+)')", voice)}
    assert set(greet) == set(LANGUAGES) and all("KEY" in g and "Runway" not in g for g in greet.values())  # the mic introduces the assistant as KEY
    assert greet["en"] == "Hi, I'm KEY. How are you?" and greet["ms"] == "Hai, saya KEY. Apa khabar?"
    assert re.findall(r"rec: '([\w-]+)'", voice) == ["en-SG", "zh-CN", "ms-MY", "ta-SG"]
    assert "rec:" not in GAME[GAME.index("const LANGS={"):GAME.index("S.lang='en';")]  # one list of recognition tags
    assert "RW.lang = S.lang" in GAME  # the Home mic uses the language chosen on the Ask page
    # the pack's audio if already fetched, else a device voice inside the tap; never stuck
    shared = GAME[GAME.index("function greet(lang){"):GAME.index("// Speech pieces")]
    assert "if(h.a) pack(h.a);" in shared and "cap = setTimeout(end, 8000)" in shared and "setTimeout(end, 2500)" in shared


def test_read_aloud_is_on_by_default_and_never_talks_over_the_mic():
    assert '<input type="checkbox" id="autoRead" checked> Read answers aloud' in GAME
    assert "if($('#autoRead').checked&&!MIC)" in GAME  # an answer arriving while listening is not read into the mic
    speak = GAME[GAME.index("async function speak("):GAME.index("/* ---------- voice: speech to text")]
    assert speak.index("if(MIC)MIC.stop(false);") < speak.index("stopSpeak();")
    ask = GAME[GAME.index("$('#micBtn').onclick=()=>{"):GAME.index("/* ---------- more ----------")]
    assert ask.index("stopSpeak();") < ask.index("dictate(")  # the mic stops an answer being read before it greets
    assert "const INTRO=" in GAME and "speak(" not in GAME[GAME.index("function renderChat(){"):GAME.index("$('#autoRead').onchange")].replace("speak(plain(m.html),b,m.lang)", "")
    policy = GAME[GAME.index("function privacyHtml"):GAME.index("function termsHtml")]
    assert "Read aloud is on until you turn it off." in policy and "never your voice" in policy

def bridge_js(tmp_path, script):
    """The interface's send queue and RW.enter, run in Node with a stand-in page; script's last line prints JSON."""
    start, end = GAME.index("  const RW = window.RW = "), GAME.index("  /* One URL per screen.")
    stub = """const posted = [], els = {};
const el = id => els[id] || (els[id] = {id, hidden: true, textContent: '', dataset: {}, querySelectorAll: () => [],
  setAttribute(){}, removeAttribute(){}});
const document = {getElementById: el, createElement: () => ({}), head: {appendChild(){}}};
const window = {parent: {postMessage: m => posted.push(m.value || m.type), innerHeight: 800}};
const setTimeout = () => 0, clearTimeout = () => {};  // no 90 s reply timers keeping Node running
const sent = () => posted.filter(v => v && v.type).map(v => v.type + (v.payload.q ? ':' + v.payload.q : ''));
"""
    return node_json(tmp_path, stub + "(function(){\n" + GAME[start:end] + "\n})();\nconst RW = window.RW;\n" + script)


@needs_node
def test_a_repeat_while_the_data_loads_keeps_the_question(tmp_path):
    """Regression (bug B): Enter on the home ask box, then Enter again on the emptied box (or the send button, or speech
    ending) while the map data loads, used to replace the waiting question with an empty one: Ask opened, unanswered."""
    got = bridge_js(tmp_path, """RW.enter('ask', 'Can I use CPF?'); RW.enter('ask', ''); RW.enter('ask', 'Can I use CPF?');
const one = {pending: RW.pendingEnter, sent: sent(), shown: el('rwLoadQ').textContent, hidden: el('rwLoadQ').hidden};
RW.enter('ask', 'What is the 20-year minimum?');  // a new question replaces it
const two = RW.pendingEnter.arg;
RW.enter('map');  // choosing another page drops it
console.log(JSON.stringify({one, two, map: RW.pendingEnter, hidden: el('rwLoadQ').hidden}));""")
    assert got["one"]["pending"] == {"target": "ask", "arg": "Can I use CPF?"}
    assert got["one"]["sent"] == ["need_data"]  # the data is asked for once
    assert not got["one"]["hidden"] and "Can I use CPF?" in got["one"]["shown"]  # the loading panel shows it was taken
    assert got["two"] == "What is the 20-year minimum?"
    assert got["map"]["target"] == "map" and got["hidden"]


@needs_node
def test_a_question_on_its_way_is_not_asked_twice(tmp_path):
    """Once the app is loaded, a second call with the same question (double click, speech and Enter) opens Ask only."""
    got = bridge_js(tmp_path, """const calls = []; globalThis.RWAPP = window.RWAPP = {enter: (t, a) => calls.push([t, a ?? null])};
RW.send('ask', {q: 'Can I use CPF?'}); RW.enter('ask', 'Can I use CPF?'); RW.enter('ask', 'Another one');
console.log(JSON.stringify(calls));""")
    assert got == [["ask", None], ["ask", "Another one"]]


@needs_node
def test_questions_and_data_go_ahead_of_waiting_read_aloud(tmp_path):
    """One message at a time: a slow voice service must not hold up a question or the data behind queued audio.
    The message already sent stays first; a nav still goes next in line."""
    got = bridge_js(tmp_path, """RW.send('tts', {}); RW.send('tts', {}); RW.send('feedback', {}); RW.send('ask', {q: 'Q'});
RW.send('need_data'); RW.send('nav', {page: 'ask'}); RW.send('tts', {});
console.log(JSON.stringify({queue: RW.queue.map(m => m.type), sent: sent()}));""")
    assert got["queue"] == ["tts", "nav", "ask", "need_data", "tts", "feedback", "tts"]
    assert got["sent"] == ["tts"]


@needs_node
def test_lease_explorer_matches_python_rules(tmp_path):
    """Lease explorer: every age 21-85 and lease 1-99 gives runway/cpf_rules.py's CPF share (to 0.1 of a percent)."""
    code = GAME[GAME.index("function cpfPct(age,lease){"):GAME.index("const pctText=")]
    cases = [(age, lease) for age in range(21, 86) for lease in range(1, 100)]
    got = node_json(tmp_path, f"{code}\nconsole.log(JSON.stringify({json.dumps(cases)}.map(([a,l])=>cpfPct(a,l))));")
    for (age, lease), pct in zip(cases, got):
        assert pct == pytest.approx(cpf_share(age, lease) * 100, abs=0.0501), (age, lease)  # shown to 0.1, halves up


def test_lease_explorer_and_insights_are_wired_in():
    assert "'lease-explorer': 'more explorer'" in GAME and "'insights': 'more insights'" in GAME
    assert "row('explorer','Lease explorer'," in GAME and "row('insights','Insights'," in GAME
    assert "else if(s==='explorer') leaseExplorer(b,top);" in GAME and "else if(s==='insights') insightsPage(b,top);" in GAME
    assert "if(!REV())" in GAME[GAME.index("function insightsPage"):GAME.index("function caseStudy")]  # reviewers only
    assert GAME.count("${FLOW_EXPLORER}") == 2  # How it works, short and full versions: one flowchart per use case
    assert "id=\"chatDl\"" in GAME and "function downloadChat" in GAME


def test_when_you_sell_says_how_many_years_of_lease_the_buyer_needs():
    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "needs at least ${need} years of lease left to use CPF in full (95 minus ${EXIT})" in game
    assert "${need} years of lease needed</span>" in game


def test_when_you_sell_says_just_under_when_the_lease_is_a_fraction_short():
    i = GAME.index("function exitView(f){")
    view = GAME[i:GAME.index("function showResult(){", i)]
    # between need-1 and need years the card says "Just under N years", not the whole year below, so two flats a fraction
    # short read the same instead of "39 years" next to "need 40" at 97% and 98%
    assert "const near=!full&&e.left<need&&e.left>need-1, got=near?`Just under ${need} years`:`${left} years`;" in view
    assert "<b style=\"color:var(--ink)\">${got} of lease left</b> when you sell." in view
    assert "aria-label=\"Bar: ${got.toLowerCase()} of lease left when you sell;" in view
    assert "(95 minus ${left} full years of lease left)" in view  # the age rule counts whole years of lease
    assert "background:transparent;border:1.5px solid ${col}" in view  # the result chips are outlined tags, not pressable-looking chips


def test_when_you_sell_says_from_what_buyer_age_cpf_is_in_full():
    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "const minAge=95-left;" in game
    assert "Who gets full CPF:" in game and "if the youngest buyer is ${minAge} or older (95 minus ${left} full years of lease left)" in game


def test_an_age_changed_elsewhere_reaches_when_you_sell_home_and_the_lease_explorer():
    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "const start=S.ageSet?S.age:EXIT_AGE" in game and "let EXIT=start, years=5;" in game and "resaleExit(f.lease,y,EXIT)" in game  # the example buyer starts at the age you set
    assert "A buyer aged ${EXIT}${mine} needs at least" in game
    assert "if(st.fromAge!==S.age){ st.age=S.age; st.fromAge=S.age; }" in game  # the Lease explorer
    assert "observe($('#scrLanding'), {attributes: true, attributeFilter: ['hidden']})" in game  # Home takes the age back


def test_when_you_sell_has_buyer_age_chips_that_keep_the_sell_date():
    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "[...new Set([25,35,45,55,start])]" in game and "data-buyer=" in game  # 25, 35, 45, 55 and your own age
    assert "How old is the youngest buyer?" in game
    assert "EXIT=+b.dataset.buyer; upd(years);" in game  # a chip keeps the chosen sell date


def test_ui_fixes_from_the_live_app_review():
    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "if(RW.queue.some(m => m.type === 'ask' && m.payload.q === q)) return;" in game  # Ask: a repeated question is not asked twice
    assert "e.key === 'Escape' && !kp.hidden" in game  # KEY closes on Escape
    assert "kb.style.display = sheetHost.querySelector('.sheet') && kp.hidden ? 'none' : ''" in game  # KEY steps aside for a sheet
    assert "That amount is too large to be real." in game  # Find by budget: absurd amounts
