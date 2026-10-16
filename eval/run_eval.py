"""Run Runway's quality checks and save data/eval_results.json (shown on the Methodology page).

Checks:
- retrieval: is an expected official document among the top 5 passages?
- figure: does the CPF calculator match the official worked example?
- decline: are advice, prompt-injection and off-topic questions declined?
- llm (only when OPENAI_API_KEY is set): does the answer cite a passage and contain the expected words?

Usage:  python eval/run_eval.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runway.cpf_rules import cpf_share  # noqa: E402
from runway.llm import LLM, screen_question  # noqa: E402
from runway.rag import Retriever, load_chunks  # noqa: E402


def main() -> None:
    cases = json.loads((ROOT / "eval" / "questions.json").read_text())
    bot = LLM()
    index = Retriever(load_chunks(), embed=bot.embed if bot.available else None)
    rows, s = [], dict.fromkeys(
        ["retrieval_hits", "retrieval_total", "figure_pass", "figure_total", "decline_pass", "decline_total",
         "llm_pass", "llm_total"], 0)

    for case in cases:
        q, kind = case["question"], case["type"]
        row = {"Type": kind, "Question": q}
        if kind == "retrieval":
            top = index.search(q, k=5)
            hit = any(c.doc in case["expect_docs"] for c in top)
            s["retrieval_total"] += 1
            s["retrieval_hits"] += hit
            row["Result"] = "pass" if hit else "fail"
            row["Detail"] = "top source: " + top[0].doc
            if bot.available:
                ans = bot.answer(q, top)
                cited = bool(re.search(r"\[\d\]", ans.text))
                has_words = all(w.lower() in ans.text.lower() for w in case["expect_words"])
                s["llm_total"] += 1
                s["llm_pass"] += cited and has_words
                row["LLM answer"] = "pass" if cited and has_words else f"fail (cited={cited}, words={has_words})"
        elif kind == "figure":
            got = cpf_share(case["age"], case["lease"])
            ok = abs(got - case["expected"]) < 0.001
            s["figure_total"] += 1
            s["figure_pass"] += ok
            row["Result"] = "pass" if ok else "fail"
            row["Detail"] = f"got {got:.1%}, expected {case['expected']:.1%} ({case['source']})"
        elif kind == "decline":
            reason = screen_question(q)
            ok = reason == case["expect_reason"]
            s["decline_total"] += 1
            s["decline_pass"] += ok
            row["Result"] = "pass" if ok else "fail"
            row["Detail"] = f"screened as {reason}"
        rows.append(row)

    s["total"] = len(cases)
    out = {"run_at": dt.datetime.now().strftime("%d %b %Y %H:%M"), "retrieval_mode": index.mode,
           "summary": s, "cases": rows}
    (ROOT / "data" / "eval_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(s, indent=2))
    failed = [r for r in rows if r["Result"] != "pass"]
    for r in failed:
        print("FAIL:", r)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
