"""Admin changes: page text (About Us, Methodology, Privacy, Terms), the FAQ and uploaded Ask documents.

Each change is written to data/runtime/ at once, so it takes effect without a restart, and, when GITHUB_TOKEN is
set, committed to the repo (data/content.json, data/corpus/<slug>.md), so it survives the redeploys that wipe the
app's disk. data/runtime/ is gitignored: a redeploy pulls the committed copy without clashing with it.
With DATABASE_URL set, Neon keeps them instead of GitHub (runway/store.py), and R2 keeps each upload's original file.
"""

from __future__ import annotations

import base64
import copy
import datetime as dt
import functools
import io
import json
import re
import urllib.error
import urllib.request
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from runway import store
from runway.config import get_setting

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "corpus"
CONTENT_FILE = ROOT / "data" / "content.json"
RUNTIME = ROOT / "data" / "runtime"
RUNTIME_CORPUS = RUNTIME / "corpus"
RUNTIME_CONTENT = RUNTIME / "content.json"
# Methodology's keys replaced How it works' (method.full, method.brief), so an edit of the old page can't hide the new one.
PAGE_KEYS = {"about.full", "about.brief", "methodology.full", "methodology.brief", "privacy", "terms"}
MAX_PAGE_CHARS = 100_000
MAX_FAQ = 100
MAX_UPLOAD_BYTES = 6 * 1024 * 1024
CONTENT_TYPES = {".pdf": "application/pdf", ".html": "text/html", ".htm": "text/html", ".md": "text/markdown",
                 ".txt": "text/plain"}
DEFAULT_REPO = "dansyfq/project-runway"


# ---------- saving: this disk now, GitHub for keeps ----------

def commit(path: str, data: bytes, message: str) -> str:
    """Commit one file to the repo. Returns "github", or "local" when no token is set. Raises on a GitHub error."""
    token = get_setting("GITHUB_TOKEN")
    if not token:
        return "local"
    repo, branch = get_setting("GITHUB_REPO", DEFAULT_REPO), get_setting("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "runway-app"}
    sha = None
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{url}?ref={branch}", headers=headers), timeout=20) as r:
            sha = json.load(r).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:  # 404: a new file
            raise
    body = {"message": message, "content": base64.b64encode(data).decode(), "branch": branch}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=30):
        pass
    return "github"


def save(rel_path: str, local: Path, data: bytes, message: str) -> dict:
    """Write locally (always), then keep it: Neon when DATABASE_URL is set, else a GitHub commit, else this disk only.
    A failed keep leaves the local change working and says why."""
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    where = "the database" if store.db_enabled() else "GitHub"
    try:
        if store.db_enabled():
            store.put_file(rel_path, data)
            return {"saved": "database"}
        return {"saved": commit(rel_path, data, message)}
    except Exception as exc:  # the change already works here; say it won't survive a restart
        print(f"[runway] keeping {rel_path} in {where} failed: {type(exc).__name__}: {exc}", flush=True)
        return {"saved": "local", "warn": f"{where[0].upper() + where[1:]} didn't accept it ({type(exc).__name__}), so it lasts until the app restarts."}


@functools.lru_cache(maxsize=1)
def restore() -> int:
    """Once per process: put the database's copies back on this disk, which a redeploy wiped. Returns how many."""
    if not store.db_enabled():
        return 0
    try:
        files = store.all_files()
    except Exception as exc:  # Runway still works from the committed files
        print(f"[runway] restoring from the database failed: {type(exc).__name__}: {exc}", flush=True)
        return 0
    n = 0
    for path, body in files.items():
        if path == "data/content.json":
            local = RUNTIME_CONTENT
        elif re.fullmatch(r"data/corpus/[a-z0-9-]{1,80}\.md", path):
            local = RUNTIME_CORPUS / Path(path).name
        else:  # only the paths Runway writes
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(body)
        n += 1
    return n


# ---------- page text and FAQ ----------

def load_content() -> dict:
    """The newest copy: this disk's (if a change was made since the last start), else the committed one.
    Runs on every message, and the files rarely change: read once per file version, a fresh copy for each caller."""
    restore()
    stamp = tuple((str(p), p.stat().st_mtime_ns if p.exists() else 0) for p in (RUNTIME_CONTENT, CONTENT_FILE))
    return copy.deepcopy(_read_content(stamp))


@functools.lru_cache(maxsize=4)
def _read_content(stamp: tuple) -> dict:
    for path, _ in stamp:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {"pages": data.get("pages") or {}, "faq": data.get("faq")}
        except (OSError, ValueError):
            continue
    return {"pages": {}, "faq": None}


def _write_content(content: dict, message: str) -> dict:
    data = json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8")
    return save("data/content.json", RUNTIME_CONTENT, data, message)


ALLOWED_TAGS = {"h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "b", "strong", "i", "em", "a", "br", "table", "thead",
                "tbody", "tr", "th", "td", "div", "span", "small", "section"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math", "form",
                     "textarea", "select", "button"}
SAFE_CLASS = re.compile(r"^[\w -]{0,80}$")
SAFE_ID = re.compile(r"^[\w-]{1,40}$")


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED_TAGS:
            return
        keep = []
        for k, v in attrs:
            v = v or ""
            if k == "class" and SAFE_CLASS.match(v) or k == "id" and SAFE_ID.match(v):
                keep.append(f' {k}="{escape(v)}"')
            elif k == "href" and tag == "a" and re.match(r"^(https?://|mailto:|#)", v.strip(), re.I):
                keep.append(f' href="{escape(v.strip())}"')
                if not v.strip().startswith("#"):
                    keep.append(' target="_blank" rel="noopener"')
        self.out.append(f"<{tag}{''.join(keep)}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ALLOWED_TAGS and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))


def clean_html(raw: str) -> str:
    """Page text from the editor reaches every visitor: keep plain formatting, links and the page's own classes only."""
    p = _Clean()
    p.feed(raw)
    p.close()
    return "".join(p.out).strip()


def save_page(key: str, html: str) -> dict:
    if key not in PAGE_KEYS or not isinstance(html, str) or len(html) > MAX_PAGE_CHARS:
        return {"ok": False, "error": "That page can't be saved."}
    content = load_content()
    cleaned = clean_html(html)
    if cleaned:
        content["pages"][key] = cleaned
    else:  # empty: back to the page as built
        content["pages"].pop(key, None)
    return {"ok": True, "content": content, **_write_content(content, f"Reviewer edit: {key} page")}


def _line(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _url(value) -> str:
    url = _line(value, 500)
    return url if re.match(r"^https?://", url, re.I) else ""


def save_faq(items) -> dict:
    if items is None:  # back to the FAQ as built
        content = load_content()
        content["faq"] = None
        return {"ok": True, "content": content, **_write_content(content, "Reviewer edit: FAQ restored")}
    if not isinstance(items, list) or len(items) > MAX_FAQ:
        return {"ok": False, "error": "The FAQ can hold up to 100 questions."}
    faq = []
    for it in items:
        if not isinstance(it, dict):
            return {"ok": False, "error": "bad FAQ"}
        q, a = _line(it.get("q"), 300), str(it.get("a") or "").strip()[:3000]
        if not q or not a:
            return {"ok": False, "error": "Every question needs a question and an answer."}
        faq.append({"q": q, "a": a, "doc": _line(it.get("doc"), 80), "title": _line(it.get("title"), 200),
                    "publisher": _line(it.get("publisher"), 80), "url": _url(it.get("url"))})
    content = load_content()
    content["faq"] = faq
    return {"ok": True, "content": content, **_write_content(content, "Reviewer edit: FAQ")}


# ---------- Ask documents ----------

NOISE_TAGS = ["script", "style", "noscript", "svg", "header", "footer", "nav", "aside"]


def html_to_text(raw: str) -> str:
    from bs4 import BeautifulSoup

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


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
    return re.sub(r"[ \t]+", " ", "\n\n".join(pages))


def doc_meta(path: Path) -> dict:
    head = path.read_text(encoding="utf-8").split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)


def corpus_files() -> dict[str, Path]:
    """Every Ask document by slug; one uploaded on this disk wins over the committed copy."""
    restore()
    files = {p.stem: p for p in sorted(CORPUS_DIR.glob("*.md"))}
    files.update({p.stem: p for p in sorted(RUNTIME_CORPUS.glob("*.md"))})
    return dict(sorted(files.items()))


def list_docs() -> list[dict]:
    out = []
    for slug, path in corpus_files().items():
        meta = doc_meta(path)
        out.append({"slug": slug, "title": meta.get("title", slug), "publisher": meta.get("publisher", ""),
                    "retrieved": meta.get("retrieved", "")})
    return out


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def add_doc(payload: dict) -> dict:
    name = _line(payload.get("name"), 200)
    try:
        data = base64.b64decode(str(payload.get("data", "")), validate=True)
    except ValueError:
        return {"ok": False, "error": "The file didn't arrive whole. Try again."}
    if not data:
        return {"ok": False, "error": "Choose a file first."}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"ok": False, "error": "That file is over 6 MB."}
    try:
        if data[:4] == b"%PDF":
            body = pdf_to_text(data)
        elif name.lower().endswith((".html", ".htm")):
            body = html_to_text(data.decode("utf-8", errors="ignore"))
        else:
            body = data.decode("utf-8", errors="ignore")
            if body.startswith("---\n") and body.count("---\n") >= 2:  # a corpus file: keep its text, not its header
                body = body.split("---\n", 2)[2]
    except Exception as exc:  # a broken PDF or HTML file
        return {"ok": False, "error": f"Runway couldn't read that file ({type(exc).__name__})."}
    body = body.replace("\r\n", "\n").strip()
    if len(body.split()) < 30:
        return {"ok": False, "error": "Runway found almost no text in that file. A scanned PDF has none to read."}

    title = _line(payload.get("title"), 200) or Path(name).stem or "Uploaded document"
    replace = _line(payload.get("replace"), 80)
    files = corpus_files()
    if replace and replace not in files:
        return {"ok": False, "error": "The document to replace isn't in the library."}
    slug = replace or slugify(title) or "uploaded-document"
    if not replace and slug in files:  # a new document never overwrites one by accident
        slug = f"{slug[:55]}-{dt.datetime.now():%H%M%S}"
    header = (f"---\ntitle: {title}\npublisher: {_line(payload.get('publisher'), 80) or 'Reviewer upload'}\n"
              f"url: {_url(payload.get('url'))}\nretrieved: {dt.date.today().isoformat()}\n---\n\n")
    doc = (header + body + "\n").encode("utf-8")
    verb = "Replace" if replace else "Add"
    result = save(f"data/corpus/{slug}.md", RUNTIME_CORPUS / f"{slug}.md", doc, f"Reviewer upload: {verb} {slug}")
    if store.r2_enabled():  # the file as it came, beside the text Runway searches
        ext = (Path(name).suffix.lower() or ".txt")[:6]
        key = f"uploads/{slug}/{dt.datetime.now():%Y%m%d-%H%M%S}{ext if re.fullmatch(r'[.][a-z0-9]{1,5}', ext) else '.bin'}"
        try:
            store.put_original(key, data, CONTENT_TYPES.get(ext, "application/octet-stream"))
            result["original"] = key
        except Exception as exc:  # the document already works; only the original copy is missing
            print(f"[runway] R2 upload of {key} failed: {type(exc).__name__}: {exc}", flush=True)
            result["warn"] = (result.get("warn", "") + f" The original file wasn't kept in R2 ({type(exc).__name__}).").strip()
    return {"ok": True, "slug": slug, "replaced": bool(replace), "words": len(body.split()), **result}
