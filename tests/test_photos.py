"""Town photo credits (CC BY / BY-SA need the author and licence, whole)."""

import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_photo_credit_is_one_whole_line():
    for row in csv.DictReader((ROOT / "data" / "photos" / "landmarks.csv").open()):
        if row["photo_file"]:
            title, *author, licence, site = row["caption"].split(" · ")
            assert "\n" not in row["caption"] and site == "Wikimedia Commons", row["town"]
            assert licence.startswith("CC") and author and len(" · ".join(author)) < 80, row["town"]


def test_long_artist_notice_is_reduced_to_the_name(monkeypatch):
    spec = importlib.util.spec_from_file_location("fetch_town_photos", ROOT / "scripts" / "fetch_town_photos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    artist = ("\n\n\nThis Photo was taken by Timothy A. Gonsalves.  Feel free to use my photos, but please mention "
              "me as the author.  I would much appreciate if you send me an email x@example.com.\n")
    page = {"title": "File:Hill.jpg", "imageinfo": [{"mime": "image/jpeg", "thumburl": "t", "descriptionurl": "d",
            "extmetadata": {"Artist": {"value": artist}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}
    monkeypatch.setattr(mod, "api", lambda **_: {"query": {"pages": [page]}})
    assert mod.find_photo("Bukit Timah Hill")["author"] == "Timothy A. Gonsalves"
