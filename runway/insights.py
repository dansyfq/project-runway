"""Reviewer Insights (More > Insights): how Ask Runway is doing, for the person who looks after its documents.

- Documents: how many official documents and passages Ask searches, and which were uploaded by a reviewer.
- Quality: the latest eval run (python eval/run_eval.py), including retrieval by search mode.
- Feedback: Helpful / Not helpful votes, by answer language, and the questions people marked Not helpful (only
  those that passed screening are ever kept: runway/bridge.py), so a reviewer knows which document to add next.
- AI use: calls in the last hour against the process-wide cap.
Reads only what Runway already keeps; nothing here is new personal data.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_FILE = ROOT / "data" / "eval_results.json"
MAX_LOW_RATED = 10


def read_votes(feedback_file: Path) -> tuple[list[dict], str]:
    """Votes, newest first, and where they came from: the database when set up, else this disk's log."""
    from runway import store

    if store.db_enabled():
        try:
            return store.recent_votes(), "database"
        except Exception as exc:  # fall through to the file, and say so in the log
            print(f"[runway] reading votes from the database failed: {type(exc).__name__}: {exc}", flush=True)
    votes = []
    try:
        for line in feedback_file.read_text(encoding="utf-8").splitlines():
            try:
                v = json.loads(line)
            except ValueError:
                continue
            if isinstance(v, dict) and v.get("rating") in ("up", "down"):
                votes.append(v)
    except OSError:
        return [], "none yet"
    return votes[::-1], "this server's log file (cleared by a redeploy)"


def feedback_summary(votes: list[dict]) -> dict:
    votes = [v for v in votes if isinstance(v, dict) and v.get("rating") in ("up", "down")]  # the database too
    up = sum(v.get("rating") == "up" for v in votes)
    langs = Counter(str(v.get("lang", "en")) for v in votes)
    seen, low = set(), []
    for v in votes:  # newest first
        q = str(v.get("question", "")).strip()
        if v.get("rating") == "down" and q and q.lower() not in seen:
            seen.add(q.lower())
            low.append({"q": q[:300], "date": str(v.get("date", ""))[:10]})
        if len(low) >= MAX_LOW_RATED:
            break
    return {"total": len(votes), "up": up, "down": len(votes) - up,
            "helpful_pct": round(100 * up / len(votes)) if votes else None,
            "by_lang": dict(langs.most_common()), "low_rated": low}


def eval_summary() -> dict | None:
    try:
        data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    s = data.get("summary", {})
    return {"run_at": data.get("run_at"), "mode": data.get("retrieval_mode"), "by_mode": data.get("by_mode"),
            "checks": [[name, s.get(f"{key}_pass" if key != "retrieval" else "retrieval_hits", 0), s.get(f"{key}_total", 0)]
                       for name, key in (("Right document in the top 5", "retrieval"), ("Calculator matches official examples", "figure"),
                                         ("Advice, injection and off-topic declined", "decline"), ("AI answers cite and use the expected words", "llm"))]}


def build(chunks: list, feedback_file: Path, ai_calls: int, ai_cap: int, model: str, ai_on: bool, mode: str) -> dict:
    from runway.content import RUNTIME_CORPUS, list_docs

    uploaded = {p.stem for p in RUNTIME_CORPUS.glob("*.md")}
    per_doc = Counter(c.doc for c in chunks)
    docs = [{**d, "passages": per_doc.get(d["slug"], 0), "uploaded": d["slug"] in uploaded} for d in list_docs()]
    votes, votes_from = read_votes(feedback_file)
    return {
        "generated": time.strftime("%d %b %Y %H:%M"),
        "corpus": {"docs": len(docs), "passages": len(chunks), "uploaded": len(uploaded), "mode": mode, "list": docs},
        "eval": eval_summary(),
        "feedback": {**feedback_summary(votes), "from": votes_from},
        "ai": {"on": ai_on, "model": model if ai_on else None, "calls_last_hour": ai_calls, "cap": ai_cap},
    }
