"""Accounts, roles and the password check against salted PBKDF2 hashes.

Two accounts are built in (BUILTIN_USERS): `admin` (role admin) and `user` (role user). Only their hashes
are here; the passwords are handed over separately and are not in the repo. More accounts, or a new
password for a built-in one, come from Streamlit secrets ([auth.users], written by `scripts/seed_users.py`).
Roles: "admin" can do everything, including uploading Ask documents and editing pages and the FAQ;
"user" sees the full About Us and How it works but has no admin tools; guests have the role "brief".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 600_000  # OWASP's figure for PBKDF2-SHA256; older hashes keep their own count


def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8", "surrogatepass"), salt, iterations)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"{ALGO}${iterations}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:  # a malformed secrets entry fails closed (binascii.Error is a ValueError)
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != ALGO:
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8", "surrogatepass"), base64.b64decode(salt_b64), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


DUMMY_HASH = hash_password("dummy")  # made once, so unknown usernames cost exactly one hash like known ones
ROLES = ("admin", "user")
# username -> (role, hash). The repo is public, so these are long random passwords hashed with 600,000 rounds.
BUILTIN_USERS = {
    "admin": ("admin", "pbkdf2_sha256$600000$tWu7a3PvVJf6dt6rFwTx/g==$6tJ8tWKidfE13KOa9z+tH89wQxgdkq1Fc3bq+WZnVoQ="),
    "user": ("user", "pbkdf2_sha256$600000$kL6q7U3/40wLG/LoJA4FhQ==$ZVkaSMdEabBdKx0qHejebdkehfRrahVC2rkE9023udw="),
}


def load_users(secret_users, builtin: str = "admin,user") -> dict[str, tuple[str, str]]:
    """The accounts that can log in: username -> (role, hash).

    `builtin` lists the built-in accounts that are on (the BUILTIN_ACCOUNTS setting; "user" or "" turns
    the built-in admin off). A secrets entry replaces a built-in account of the same name. It is either a
    hash, as before (the built-in account's role, otherwise admin, so the original reviewer keeps the admin
    tools), or a table {hash = "...", role = "user"}. An entry with an unknown role or no hash is left out.
    """
    on = {name.strip().lower() for name in (builtin or "").split(",")}
    users = {name: entry for name, entry in BUILTIN_USERS.items() if name in on}
    for name, value in (secret_users or {}).items():
        name = str(name).strip().lower()
        role = BUILTIN_USERS.get(name, ("admin",))[0]
        if hasattr(value, "get"):  # a table
            role, value = value.get("role", role), value.get("hash")
        if isinstance(value, str) and role in ROLES:
            users[name] = (role, value)
        else:
            users.pop(name, None)  # a broken entry fails closed, and never falls back to the built-in password
    return users


def check_login(username: str, password: str, users: dict) -> str | None:
    """The account's role if the password matches, else None. `users` maps a username to (role, hash), or
    to a bare hash (admin). Constant-ish time: always run one hash, even for unknown usernames."""
    entry = users.get(username.strip().lower())
    if entry is None:
        verify_password(password, DUMMY_HASH)
        return None
    role, stored = entry if isinstance(entry, tuple) else ("admin", entry)
    return role if verify_password(password, stored) else None
