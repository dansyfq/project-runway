import importlib.util
import tomllib
from pathlib import Path

from runway.auth import check_login, hash_password, verify_password

ROOT = Path(__file__).resolve().parent.parent


def test_hash_round_trip():
    stored = hash_password("s3cret-Pass", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("s3cret-Pass", stored)
    assert not verify_password("wrong", stored)


def test_same_password_gets_different_salt():
    assert hash_password("x", iterations=1000) != hash_password("x", iterations=1000)


def test_malformed_hash_is_rejected():
    assert not verify_password("x", "plaintext")
    assert not verify_password("x", "md5$1$a$b")


def test_check_login_is_case_insensitive_on_username():
    users = {"lecturer": hash_password("Pw12345678", iterations=1000)}
    assert check_login("Lecturer ", "Pw12345678", users)
    assert not check_login("lecturer", "nope", users)
    assert not check_login("ghost", "Pw12345678", users)


def load_seed(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("seed_users", ROOT / "scripts" / "seed_users.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ACCOUNTS_FILE", tmp_path / "demo_accounts.local.toml")
    monkeypatch.setattr(mod, "SECRETS_FILE", tmp_path / ".streamlit" / "secrets.toml")
    return mod


def test_seed_generates_accounts_and_keeps_other_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWAY_DEMO_USERS", raising=False)
    seed = load_seed(tmp_path, monkeypatch)
    seed.SECRETS_FILE.parent.mkdir()
    seed.SECRETS_FILE.write_text('OPENAI_API_KEY = "sk-test"\n')
    seed.main()
    accounts = tomllib.loads(seed.ACCOUNTS_FILE.read_text())["accounts"]
    secrets = tomllib.loads(seed.SECRETS_FILE.read_text())
    assert set(accounts) == {"lecturer", "reviewer", "demo"}
    assert secrets["OPENAI_API_KEY"] == "sk-test"
    for name, pw in accounts.items():
        assert verify_password(pw, secrets["auth"]["users"][name])
        assert pw not in seed.SECRETS_FILE.read_text()


def test_seed_reads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNWAY_DEMO_USERS", "alice:Pw1abcdefgh, bob:Pw2abcdefgh")
    seed = load_seed(tmp_path, monkeypatch)
    seed.main()
    users = tomllib.loads(seed.SECRETS_FILE.read_text())["auth"]["users"]
    assert verify_password("Pw2abcdefgh", users["bob"])
    assert not seed.ACCOUNTS_FILE.exists()


def test_no_credentials_in_tracked_sources():
    """Guard: nothing under runway/, pages or app.py may contain an [accounts] table or a hash."""
    for path in [ROOT / "app.py", *ROOT.glob("runway/*.py"), *ROOT.glob("app_pages/*.py")]:
        if path.exists():
            text = path.read_text()
            assert "pbkdf2_sha256$" not in text.replace('f"{ALGO}$', "")
            assert "[accounts]" not in text
