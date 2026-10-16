"""Convert a downloaded official page (HTML or PDF) into a corpus document.

Usage:
    python scripts/to_corpus.py <file> <slug> --url URL --title TITLE --publisher PUB

Writes data/corpus/<slug>.md with a small front-matter block that the RAG
index reads for citations. Pages that only render with JavaScript (cpf.gov.sg,
hdb.gov.sg) were copied from a browser instead and use the same format.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from bs4 import BeautifulSoup

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"
NOISE_TAGS = ["script", "style", "noscript", "svg", "header", "footer", "nav", "aside"]


def html_to_text(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        if el.find(["p", "li", "td"]):  # skip containers, keep leaves
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in {"h1", "h2", "h3", "h4"}:
            text = "#" * int(el.name[1]) + " " + text
        elif el.name == "li":
            text = "- " + text
        lines.append(text)
    return "\n\n".join(lines)


def pdf_to_text(path: Path) -> str:
    from pypdf import PdfReader

    pages = [p.extract_text() or "" for p in PdfReader(path).pages]
    text = "\n\n".join(pages)
    return re.sub(r"[ \t]+", " ", text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("slug")
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--publisher", required=True)
    args = ap.parse_args()

    data = args.file.read_bytes()
    if data[:4] == b"%PDF":
        body = pdf_to_text(args.file)
    else:
        body = html_to_text(data.decode("utf-8", errors="ignore"))

    header = (
        f"---\ntitle: {args.title}\npublisher: {args.publisher}\n"
        f"url: {args.url}\nretrieved: {dt.date.today().isoformat()}\n---\n\n"
    )
    out = CORPUS_DIR / f"{args.slug}.md"
    out.write_text(header + body.strip() + "\n", encoding="utf-8")
    print(f"{out.name}: {len(body.split())} words")


if __name__ == "__main__":
    main()
