"""Download one freely licensed Wikimedia Commons photo per town landmark for the town stamps.

Usage:  python scripts/fetch_town_photos.py
Reads data/photos/landmarks.csv, searches Commons for each landmark, keeps only CC BY, CC BY-SA,
CC0 or public-domain images, saves a 360px thumbnail as data/photos/<town>.jpg and records
the author, licence and source page in landmarks.csv.

Uses /usr/bin/curl because Python's TLS stack fails behind some corporate proxies.
"""

from __future__ import annotations

import csv
import html
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

PHOTO_DIR = Path(__file__).resolve().parent.parent / "data" / "photos"
API = "https://commons.wikimedia.org/w/api.php"
OK_LICENCE = re.compile(r"^(CC BY(-SA)? [0-9.]+|CC0|Public domain|PD)", re.I)
UA = "RunwayBootcampProject/1.0 (educational; contact via github.com/dansyfq)"


def curl(url: str) -> bytes:
    return subprocess.run(["/usr/bin/curl", "-sL", "-A", UA, url], check=True, capture_output=True).stdout


def api(**params) -> dict:
    params |= {"format": "json", "formatversion": "2"}
    for attempt in range(4):  # Commons rate-limits bursts with an empty reply
        time.sleep(1.5 * (attempt + 1))
        body = curl(API + "?" + urllib.parse.urlencode(params))
        if body.strip().startswith(b"{"):
            return json.loads(body)
    raise RuntimeError("Commons API kept refusing; try again later")


def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def find_photo(query: str) -> dict | None:
    found = api(action="query", generator="search", gsrsearch=f"{query} filetype:bitmap", gsrnamespace=6,
                gsrlimit=12, prop="imageinfo", iiprop="url|extmetadata|mime", iiurlwidth=360)
    pages = sorted(found.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licence = strip_tags(meta.get("LicenseShortName", {}).get("value", ""))
        if info.get("mime") != "image/jpeg" or not OK_LICENCE.match(licence):
            continue
        return {
            "thumb": info["thumburl"],
            "page": info["descriptionurl"],
            "author": strip_tags(meta.get("Artist", {}).get("value", "Unknown author"))[:80],
            "licence": licence,
            "title": page["title"].removeprefix("File:"),
        }
    return None


def save(path: Path, rows: list[dict]) -> None:
    fields = ["town", "landmark", "photo_file", "caption", "source_url", "status"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in fields} for r in rows)


def main() -> None:
    path = PHOTO_DIR / "landmarks.csv"
    rows = list(csv.DictReader(path.open()))
    for row in rows:
        slug = row["town"].lower().replace(" ", "_").replace("/", "_")
        if row.get("source_url") and (PHOTO_DIR / f"{slug}.jpg").exists():
            continue  # already fetched with full credit
        hit = find_photo(f"{row['landmark']} Singapore") or find_photo(f"{row['town'].title()} Singapore HDB")
        if not hit:
            print(f"no free photo: {row['town']}")
            continue
        (PHOTO_DIR / f"{slug}.jpg").write_bytes(curl(hit["thumb"]))
        row.update(photo_file=f"{slug}.jpg", status="have",
                   caption=f"{hit['title']} · {hit['author']} · {hit['licence']} · Wikimedia Commons",
                   source_url=hit["page"])
        save(path, rows)
        print(f"{row['town']}: {hit['title']} ({hit['licence']})")


if __name__ == "__main__":
    main()
