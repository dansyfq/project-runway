"""Password check against salted PBKDF2 hashes kept in Streamlit secrets.

No usernames or passwords live in the code. `scripts/seed_users.py` writes the
hashes to `.streamlit/secrets.toml` (gitignored); on Streamlit Community Cloud
the same block is pasted into the app's Secrets settings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 310_000


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


def check_login(username: str, password: str, users: dict[str, str]) -> bool:
    """Constant-ish time: always run one hash, even for unknown usernames."""
    stored = users.get(username.strip().lower())
    if stored is None:
        verify_password(password, hash_password("dummy", iterations=ITERATIONS))
        return False
    return verify_password(password, stored)
