"""Lasting storage for what changes while Runway runs. Streamlit Community Cloud wipes the app's disk on every redeploy.

- Neon (Postgres), when DATABASE_URL is set: reviewer edits (data/content.json), uploaded Ask documents
  (data/corpus/<slug>.md) and answer votes. The running app works from files in data/runtime/; this keeps their
  lasting copy and puts them back after a restart (runway.content.restore).
- Cloudflare R2, when R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET are set: the original file
  of each upload (the PDF or web page), kept as it came.

Without these settings Runway behaves as before: the GitHub commit (GITHUB_TOKEN), else this disk only.
"""

from __future__ import annotations

import functools
import json

from runway.config import get_setting

SCHEMA = """
create table if not exists runway_files (
    path text primary key,           -- the repo path the file stands for: data/content.json, data/corpus/<slug>.md
    body bytea not null,
    updated timestamptz not null default now()
);
create table if not exists runway_feedback (
    id bigserial primary key,
    vote jsonb not null              -- as written to data/feedback.jsonl: its date, never a time of day (Privacy Policy)
);
"""


def db_enabled() -> bool:
    return bool(get_setting("DATABASE_URL"))


def r2_enabled() -> bool:
    return all(get_setting(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"))


def _connect():
    import psycopg

    return psycopg.connect(get_setting("DATABASE_URL"), autocommit=True, connect_timeout=10)


@functools.lru_cache(maxsize=1)
def _schema_ready(url: str) -> bool:
    """Create the tables once per process (and once per database URL)."""
    with _connect() as conn:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
    return True


def _db():
    _schema_ready(get_setting("DATABASE_URL"))
    return _connect()


def put_file(path: str, body: bytes) -> None:
    with _db() as conn:
        conn.execute("insert into runway_files (path, body) values (%s, %s) "
                     "on conflict (path) do update set body = excluded.body, updated = now()", (path, body))


def all_files() -> dict[str, bytes]:
    with _db() as conn:
        return {p: bytes(b) for p, b in conn.execute("select path, body from runway_files").fetchall()}


def add_vote(vote: dict) -> None:
    with _db() as conn:
        conn.execute("insert into runway_feedback (vote) values (%s::jsonb)", (json.dumps(vote, ensure_ascii=False),))


def recent_votes(limit: int = 2000) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("select vote from runway_feedback order by id desc limit %s", (limit,)).fetchall()
    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


def _r2():
    import boto3

    return boto3.client("s3", endpoint_url=f"https://{get_setting('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                        aws_access_key_id=get_setting("R2_ACCESS_KEY_ID"),
                        aws_secret_access_key=get_setting("R2_SECRET_ACCESS_KEY"), region_name="auto")


def put_original(key: str, body: bytes, content_type: str) -> None:
    _r2().put_object(Bucket=get_setting("R2_BUCKET"), Key=key, Body=body, ContentType=content_type)
