"""Create demo login accounts without putting any credentials in the repo.

Where the accounts come from (first match wins):
  1. RUNWAY_DEMO_USERS env var, e.g. "reviewer:pass1"
  2. demo_accounts.local.toml  (gitignored; [accounts] name = "password")
  3. Otherwise a "reviewer" account with a random password is generated and saved to
     demo_accounts.local.toml so you can hand them out.

Output: `.streamlit/secrets.toml` (gitignored) gets an [auth.users] table of
salted PBKDF2 hashes. Other keys already in that file (e.g. OPENAI_API_KEY)
are kept. Paste the file's contents into Streamlit Cloud > App settings > Secrets.

Usage:
    python scripts/seed_users.py            # seed (or reuse) accounts
    python scripts/seed_users.py --rotate   # new random passwords
"""

from __future__ import annotations

import os
import secrets
import string
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from runway.auth import hash_password  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_FILE = ROOT / "demo_accounts.local.toml"
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"
DEFAULT_USERS = ("reviewer",)


def random_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw


def accounts_from_env() -> dict[str, str]:
    raw = os.environ.get("RUNWAY_DEMO_USERS", "").strip()
    pairs = [p.split(":", 1) for p in raw.split(",") if ":" in p]
    return {name.strip().lower(): pw.strip() for name, pw in pairs if name.strip() and pw.strip()}


def accounts_from_file() -> dict[str, str]:
    if not ACCOUNTS_FILE.exists():
        return {}
    return {k.lower(): v for k, v in tomllib.loads(ACCOUNTS_FILE.read_text()).get("accounts", {}).items()}


def toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_accounts_file(accounts: dict[str, str]) -> None:
    lines = ["# Demo logins for Runway. Gitignored: never commit this file.", "[accounts]"]
    lines += [f"{name} = {toml_str(pw)}" for name, pw in accounts.items()]
    ACCOUNTS_FILE.write_text("\n".join(lines) + "\n")
    ACCOUNTS_FILE.chmod(0o600)


def write_secrets(accounts: dict[str, str]) -> None:
    existing = tomllib.loads(SECRETS_FILE.read_text()) if SECRETS_FILE.exists() else {}
    existing.pop("auth", None)
    lines = [f"{k} = {toml_str(str(v))}" for k, v in existing.items() if not isinstance(v, dict)]
    for table, values in existing.items():
        if isinstance(values, dict):
            lines += ["", f"[{table}]"] + [f"{k} = {toml_str(str(v))}" for k, v in values.items()]
    lines += ["", "[auth.users]"] + [f"{name} = {toml_str(hash_password(pw))}" for name, pw in accounts.items()]
    SECRETS_FILE.parent.mkdir(exist_ok=True)
    SECRETS_FILE.write_text("\n".join(lines).lstrip() + "\n")
    SECRETS_FILE.chmod(0o600)


def main() -> None:
    rotate = "--rotate" in sys.argv
    accounts = accounts_from_env() or ({} if rotate else accounts_from_file())
    source = "RUNWAY_DEMO_USERS" if accounts_from_env() else ACCOUNTS_FILE.name
    if not accounts:
        accounts = {name: random_password() for name in DEFAULT_USERS}
        write_accounts_file(accounts)
        source = f"{ACCOUNTS_FILE.name} (newly generated)"
    write_secrets(accounts)
    print(f"Seeded {len(accounts)} accounts from {source}: {', '.join(accounts)}")
    print(f"Hashes written to {SECRETS_FILE}. Passwords are in {ACCOUNTS_FILE.name} (if generated) or your env var.")


if __name__ == "__main__":
    main()
