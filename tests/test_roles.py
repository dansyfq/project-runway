"""Two built-in accounts with real roles: admin (everything) and user (full pages, no admin tools)."""

import pytest
from streamlit.testing.v1 import AppTest

import runway.auth as auth
import runway.bridge as bridge
from runway.auth import BUILTIN_USERS, check_login, hash_password, load_users, verify_password
from runway.bridge import ADMIN_ONLY, handle

PW = {"admin": "Admin-pass-1", "user": "User-pass-1"}
# The real built-in hashes can't be checked without the passwords (which are not in the repo), so the tests swap in
# hashes made here, at a low count to stay fast. The real entries are checked for their shape and roles below.
TEST_BUILTIN = {name: (name, hash_password(pw, iterations=1000)) for name, pw in PW.items()}
ADMIN_PAYLOADS = {"docs": {}, "upload_doc": {"name": "a.md", "data": "eA=="}, "save_page": {"key": "terms", "html": "<p>x</p>"},
                  "save_faq": {"items": [{"q": "Q?", "a": "A."}]}}


@pytest.fixture(autouse=True)
def builtin(monkeypatch):
    monkeypatch.setattr(auth, "BUILTIN_USERS", TEST_BUILTIN)
    bridge.LOCKS.clear()  # the lockout is shared by every session in the process
    yield
    bridge.LOCKS.clear()


@pytest.fixture
def tools(monkeypatch):
    """Stand in for runway/content.py: record which admin tool ran, change nothing on disk."""
    import runway.content as content

    ran = []
    monkeypatch.setattr(content, "list_docs", lambda: ran.append("docs") or [])
    monkeypatch.setattr(content, "add_doc", lambda p: ran.append("upload_doc") or {"ok": True})
    monkeypatch.setattr(content, "save_page", lambda k, h: ran.append("save_page") or {"ok": True})
    monkeypatch.setattr(content, "save_faq", lambda i: ran.append("save_faq") or {"ok": True})
    return ran


def send(kind, state, users=None, **payload):
    return handle({"id": "x", "type": kind, "payload": payload}, state, load_users({}) if users is None else users, None, None)


def login(name, password=None, state=None, users=None):
    state = {} if state is None else state
    return send("login", state, users, u=name, p=PW.get(name, "") if password is None else password), state


def test_the_real_builtin_accounts_are_hashes_with_their_roles(monkeypatch):
    monkeypatch.undo()  # the real BUILTIN_USERS
    assert {name: role for name, (role, _) in auth.BUILTIN_USERS.items()} == {"admin": "admin", "user": "user"}
    for _, stored in auth.BUILTIN_USERS.values():
        algo, rounds, salt, digest = stored.split("$")
        assert algo == "pbkdf2_sha256" and int(rounds) >= 600_000 and len(salt) >= 24 and len(digest) == 44
        assert not verify_password("", stored) and not verify_password("admin", stored) and not verify_password("user", stored)


@pytest.mark.parametrize("name", ["admin", "user"])
def test_each_builtin_account_logs_in_with_its_role(name):
    reply, state = login(name)
    assert reply == {"ok": True, "user": name, "role": name}
    assert state["user"] == name and state["role"] == name


@pytest.mark.parametrize("name", ["admin", "user"])
def test_wrong_password_fails_and_the_lockout_applies(name):
    for _ in range(bridge.MAX_ATTEMPTS):
        reply, state = login(name, "wrong")
        assert reply["ok"] is False and "user" not in state and "role" not in state
    reply, state = login(name)  # the right password, but the username is paused
    assert "Too many attempts" in reply["error"] and "role" not in state


@pytest.mark.parametrize("kind", sorted(ADMIN_ONLY))
def test_user_is_refused_every_admin_message(kind, tools):
    """Hidden in the interface is not enough: a forged message from a user session is refused by the server."""
    _, state = login("user")
    assert send(kind, state, **ADMIN_PAYLOADS[kind]) == {"ok": False, "error": "Log in as an admin first."}
    assert send(kind, {}, **ADMIN_PAYLOADS[kind])["ok"] is False  # a guest too
    assert send(kind, {"user": "admin", "role": "full"}, **ADMIN_PAYLOADS[kind])["ok"] is False  # the old role name
    assert tools == []


@pytest.mark.parametrize("kind", sorted(ADMIN_ONLY))
def test_admin_may_use_every_admin_message(kind, tools):
    _, state = login("admin")
    assert send(kind, state, **ADMIN_PAYLOADS[kind])["ok"] is True
    assert tools == [kind]


def test_admin_only_covers_every_tool_in_the_interface():
    assert ADMIN_ONLY == {"docs", "upload_doc", "save_page", "save_faq"}


def test_logout_clears_the_role(tools):
    _, state = login("admin")
    assert send("logout", state) == {"ok": True, "role": "brief"}
    assert "user" not in state and state["role"] == "brief"
    assert send("save_page", state, key="terms", html="<p>x</p>")["ok"] is False and tools == []


def test_a_secrets_hash_keeps_the_reviewer_an_admin(tools):
    """Backwards compatible: today's secrets format (username = "hash") still logs in, with the admin tools."""
    users = load_users({"Reviewer": hash_password("Review-pass-1", iterations=1000)})
    reply, state = login("reviewer", "Review-pass-1", users=users)
    assert reply == {"ok": True, "user": "reviewer", "role": "admin"}
    assert send("save_faq", state, users, items=[{"q": "Q?", "a": "A."}])["ok"] and tools == ["save_faq"]
    assert set(users) == {"admin", "user", "reviewer"}  # the built-in accounts stay


def test_a_secrets_entry_overrides_the_builtin_password():
    users = load_users({"admin": hash_password("New-admin-pass", iterations=1000),
                        "user": {"hash": hash_password("New-user-pass", iterations=1000)}})
    assert login("admin", users=users)[0]["ok"] is False  # the built-in password no longer works
    assert login("admin", "New-admin-pass", users=users)[0]["role"] == "admin"
    assert login("user", "New-user-pass", users=users)[0]["role"] == "user"  # a bare hash keeps the built-in role


def test_a_secrets_table_sets_the_role():
    users = load_users({"alice": {"hash": hash_password("Alice-pass-1", iterations=1000), "role": "user"},
                        "bob": {"hash": hash_password("Bob-pass-1", iterations=1000), "role": "admin"},
                        "user": {"hash": hash_password("Up-pass-1", iterations=1000), "role": "admin"}})
    assert check_login("alice", "Alice-pass-1", users) == "user"
    assert check_login("bob", "Bob-pass-1", users) == "admin"
    assert check_login("user", "Up-pass-1", users) == "admin"  # the owner may promote a built-in account


@pytest.mark.parametrize("entry", [{"hash": "x", "role": "root"}, {"role": "user"}, {"hash": 5}, 5, None])
def test_a_broken_secrets_entry_fails_closed(entry):
    """An unknown role or a missing hash drops the account, and never falls back to the built-in password."""
    users = load_users({"admin": entry, "carol": entry})
    assert "admin" not in users and "carol" not in users
    assert login("admin", users=users)[0]["ok"] is False


@pytest.mark.parametrize("setting, names", [("admin,user", {"admin", "user"}), ("user", {"user"}), (" User , ADMIN ", {"admin", "user"}),
                                            ("", set()), (None, set())])
def test_builtin_accounts_switch(setting, names):
    assert set(load_users({}, setting)) == names


def test_no_accounts_at_all_fails_closed():
    reply, _ = login("admin", users=load_users({}, ""))
    assert reply["ok"] is False and "isn't set up" in reply["error"]


def test_the_check_is_one_hash_for_builtin_secrets_and_unknown_names(monkeypatch):
    calls = []
    real = auth.hashlib.pbkdf2_hmac
    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", lambda *a: calls.append(a[0]) or real(*a))
    users = load_users({"reviewer": hash_password("x", iterations=1000)})
    calls.clear()
    for name in ("admin", "reviewer", "ghost"):
        assert check_login(name, "wrong", users) is None
    assert len(calls) == 3


def fake_component(monkeypatch, msg):
    import streamlit.components.v1 as components

    renders = []
    monkeypatch.setattr(components, "declare_component", lambda *a, **k: lambda **kw: renders.append(kw) or msg)
    return renders


@pytest.mark.parametrize("secrets, name, password, role", [
    ({}, "user", PW["user"], "user"),
    ({}, "admin", PW["admin"], "admin"),
    ({"auth": {"users": {"reviewer": hash_password("Review-pass-1", iterations=1000)}}}, "reviewer", "Review-pass-1", "admin"),
    ({"auth": {"users": {"admin": hash_password("Other-pass-1", iterations=1000)}}}, "admin", "Other-pass-1", "admin"),
    ({"auth": {"users": {"amy": {"hash": hash_password("Amy-pass-1", iterations=1000), "role": "user"}}}}, "amy", "Amy-pass-1", "user"),
])
def test_the_host_logs_in_with_builtin_and_secrets_accounts(monkeypatch, secrets, name, password, role):
    """app.py: the built-in accounts and Secrets [auth.users] reach the login, and the next render carries the role."""
    renders = fake_component(monkeypatch, {"id": "l1", "type": "login", "payload": {"u": name, "p": password}})
    at = AppTest.from_file("app.py", default_timeout=60)
    for key, value in secrets.items():
        at.secrets[key] = value
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1]["value"] == {"ok": True, "user": name, "role": role}
    assert renders[-1]["me"] == {"user": name, "role": role}


def test_the_host_can_turn_the_builtin_admin_off(monkeypatch):
    fake_component(monkeypatch, {"id": "l2", "type": "login", "payload": {"u": "admin", "p": PW["admin"]}})
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["BUILTIN_ACCOUNTS"] = "user"
    at.run()
    assert not at.exception
    assert at.session_state["replies"][-1]["value"]["ok"] is False and "role" not in at.session_state


def test_the_interface_shows_the_role():
    from pathlib import Path

    game = (Path(__file__).resolve().parent.parent / "runway_game" / "index.html").read_text(encoding="utf-8")
    assert "const REV = () => S.role === 'admin';" in game  # admin tools only for admin
    assert "const FULL = () => S.role === 'user' || (REV() && !S.asPublic);" in game  # full pages for both
    assert "For reviewers." not in game and "Admin manages the Ask documents and pages." in game
    assert "admin tools are on" in game and "Logged in as ${esc(S.user)}</b>" in game
    assert "S.role === 'full'" not in game
