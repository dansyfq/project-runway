"""Data the Runway interface needs after sign-in: towns and sales (map.json), roads, bus stops and
amenities (features.json), and one Wikimedia Commons photo per town with its credit."""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME_DIR = ROOT / "data" / "game"
PHOTO_DIR = ROOT / "data" / "photos"


def load_photos() -> dict[str, dict]:
    photos = {}
    for row in csv.DictReader((PHOTO_DIR / "landmarks.csv").open()):
        path = PHOTO_DIR / row["photo_file"] if row.get("photo_file") else None
        if path and path.exists():
            img = "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()
            photos[row["town"]] = {"img": img, "credit": row["caption"], "landmark": row["landmark"]}
    return photos


def load_game_data() -> dict:
    return {
        "M": json.loads((GAME_DIR / "map.json").read_text()),
        "F": json.loads((GAME_DIR / "features.json").read_text()),
        "PHOTOS": load_photos(),
    }
