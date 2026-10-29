"""Tests for the periodic mod-role re-check of the web API (webui/backend/app.py).

app.py connects to Redis and validates env vars at import, so the module is
loaded from its path with env vars set, redis.Redis stubbed and the mariadb
driver faked. Sessions use Flask's cookie interface instead of Redis.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

pytest.importorskip("flask")
pytest.importorskip("flask_session")
import flask_session.redis.redis # noqa: E402,F401 - import before redis.Redis is stubbed

APP_FILE = Path(__file__).resolve().parents[1] / "webui" / "backend" / "app.py"
T0 = 1_000_000.0
MIN = 60


def stub_redis(monkeypatch):
    """redis.Redis whose ping succeeds (Flask-Session wants a real Redis subclass)."""
    import redis

    class FakeRedis(redis.Redis):
        def ping(self, **kwargs):
            return True

    monkeypatch.setattr(redis, "Redis", FakeRedis)


class FakeKeyStore:
    """Dict-backed stand-in for the Redis client (get/set/delete/exists)."""
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def get(self, key):
        self._check()
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self._check()
        self.data[key] = value
        self.ttls[key] = ex
        return True

    def delete(self, *keys):
        self._check()
        return sum(self.data.pop(k, None) is not None for k in keys)

    def exists(self, *keys):
        self._check()
        return sum(k in self.data for k in keys)


@pytest.fixture
def webapp(monkeypatch, tmp_path):
    from flask.sessions import SecureCookieSessionInterface

    for key, value in {
        "FLASK_SECRET_KEY": "test-secret", "DISCORD_CLIENT_ID": "cid",
        "DISCORD_CLIENT_SECRET": "csecret", "DISCORD_TOKEN": "bot-token",
        "DISCORD_GUILD_ID": "111", "DISCORD_MOD_ID": "900,901",
        "REDIS_HOST": "localhost", "DB_USERNAME": "u", "DB_PASSWORD": "p",
        "DB_HOST": "h", "DB_PORT": "3306", "DB_NAME": "n",
    }.items():
        monkeypatch.setenv(key, value)
    stub_redis(monkeypatch)
    fake_db = types.ModuleType("mariadb")
    fake_db.Error = type("Error", (Exception,), {})
    monkeypatch.setitem(sys.modules, "mariadb", fake_db)
    monkeypatch.chdir(tmp_path) # app.py creates logs/ in the cwd

    spec = importlib.util.spec_from_file_location("webui_backend_app_under_test", APP_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.app.session_interface = SecureCookieSessionInterface()
    module.app.config["TESTING"] = True
    module.app.add_url_rule("/api/_protected", "protected_test", module.mod_required(lambda: "ok"))

    clock = {"now": T0}
    monkeypatch.setattr(module, "_now", lambda: clock["now"])
    module.clock = clock
    module.keys = FakeKeyStore()
    monkeypatch.setattr(module, "redis_client", module.keys)
    module.fetch = MagicMock(return_value={"900"})
    monkeypatch.setattr(module, "fetch_member_roles", module.fetch)
    return module


def login(client, **extra):
    with client.session_transaction() as sess:
        sess.update({"user_id": "42", "username": "mod#0", "is_authorized": True,
                     "roles_checked_at": T0, **extra})


def session_data(client):
    with client.session_transaction() as sess:
        return dict(sess)


def transient(status=None, retry_after=None):
    return lambda module: module.TransientRoleCheckError("boom", status=status, retry_after=retry_after)


ENDPOINTS = ["/api/_protected", "/api/auth/status"]


def allowed(client, path):
    resp = client.get(path)
    if path == "/api/auth/status":
        assert resp.status_code == 200
        return resp.get_json()["is_logged_in"]
    assert resp.status_code in (200, 401)
    return resp.status_code == 200


@pytest.mark.parametrize("path", ENDPOINTS)
def test_fresh_session_no_discord_call(webapp, path):
    client = webapp.app.test_client()
    login(client)
    webapp.clock["now"] = T0 + 14 * MIN
    assert allowed(client, path)
    webapp.fetch.assert_not_called()


@pytest.mark.parametrize("path", ENDPOINTS)
def test_recheck_after_15_min_with_role(webapp, path):
    client = webapp.app.test_client()
    login(client)
    webapp.clock["now"] = T0 + 15 * MIN
    assert allowed(client, path)
    webapp.fetch.assert_called_once_with("42")
    assert session_data(client)["roles_checked_at"] == T0 + 15 * MIN


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("roles", [set(), {"123"}, None], ids=["no-roles", "other-role", "404"])
def test_recheck_without_role_or_not_member_clears_session(webapp, path, roles):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.return_value = roles
    webapp.clock["now"] = T0 + 15 * MIN
    assert not allowed(client, path)
    assert "user_id" not in session_data(client)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_session_without_roles_checked_at_is_checked_now(webapp, path):
    client = webapp.app.test_client()
    login(client)
    with client.session_transaction() as sess:
        del sess["roles_checked_at"]
    assert allowed(client, path)
    webapp.fetch.assert_called_once()
    assert session_data(client)["roles_checked_at"] == T0


@pytest.mark.parametrize("path", ENDPOINTS)
def test_session_without_roles_checked_at_and_no_role_is_rejected(webapp, path):
    client = webapp.app.test_client()
    login(client)
    with client.session_transaction() as sess:
        del sess["roles_checked_at"]
    webapp.fetch.return_value = set()
    assert not allowed(client, path)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_session_without_roles_checked_at_and_transient_error_fails_closed(webapp, path):
    client = webapp.app.test_client()
    login(client)
    with client.session_transaction() as sess:
        del sess["roles_checked_at"]
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("boom")
    assert not allowed(client, path)


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("make_error", [
    transient(status=429, retry_after=120), transient(status=500),
    transient(status=403), transient(status=401), transient(),
], ids=["429", "5xx", "403", "401", "network"])
def test_transient_error_keeps_session_within_window(webapp, path, make_error):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.side_effect = make_error(webapp)
    webapp.clock["now"] = T0 + 15 * MIN
    assert allowed(client, path)
    data = session_data(client)
    assert data["roles_checked_at"] == T0 # not refreshed
    assert data["roles_retry_at"] >= T0 + 16 * MIN


def test_retry_after_is_respected_and_minimum_is_60s(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.clock["now"] = T0 + 15 * MIN
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("rl", status=429, retry_after=300)
    assert allowed(client, "/api/_protected")
    assert session_data(client)["roles_retry_at"] == T0 + 15 * MIN + 300

    client2 = webapp.app.test_client()
    login(client2)
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("rl", status=429, retry_after=5)
    assert allowed(client2, "/api/_protected")
    assert session_data(client2)["roles_retry_at"] == T0 + 15 * MIN + 60


def test_no_second_discord_call_before_retry_at(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("boom", status=500)
    webapp.clock["now"] = T0 + 15 * MIN
    assert allowed(client, "/api/_protected")
    assert webapp.fetch.call_count == 1
    webapp.clock["now"] = T0 + 15 * MIN + 59
    assert allowed(client, "/api/_protected")
    assert allowed(client, "/api/auth/status")
    assert webapp.fetch.call_count == 1
    webapp.clock["now"] = T0 + 15 * MIN + 60
    assert allowed(client, "/api/_protected")
    assert webapp.fetch.call_count == 2


@pytest.mark.parametrize("path", ENDPOINTS)
def test_repeated_transient_errors_past_60_min_log_out(webapp, path):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("boom", status=500)
    for minutes in (15, 30, 45, 59):
        webapp.clock["now"] = T0 + minutes * MIN
        assert allowed(client, "/api/_protected")
    webapp.clock["now"] = T0 + 60 * MIN
    assert not allowed(client, path)
    assert "user_id" not in session_data(client)


def test_past_60_min_logs_out_even_during_backoff(webapp):
    client = webapp.app.test_client()
    login(client, roles_retry_at=T0 + 3 * 60 * MIN)
    webapp.clock["now"] = T0 + 61 * MIN
    assert not allowed(client, "/api/_protected")
    webapp.fetch.assert_not_called()


def test_success_after_transient_error_resets_retry(webapp):
    client = webapp.app.test_client()
    login(client, roles_retry_at=T0 + 20 * MIN)
    webapp.clock["now"] = T0 + 20 * MIN
    assert allowed(client, "/api/_protected")
    data = session_data(client)
    assert data["roles_checked_at"] == T0 + 20 * MIN
    assert "roles_retry_at" not in data


def test_unauthenticated_requests(webapp):
    client = webapp.app.test_client()
    assert client.get("/api/_protected").status_code == 401
    assert client.get("/api/auth/status").get_json() == {"is_logged_in": False}
    webapp.fetch.assert_not_called()


# --- fetch_member_roles (real function, requests mocked) ---

def fake_response(status, roles=None, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.json.return_value = {"roles": roles or []}
    return resp


@pytest.fixture
def real_fetch_member_roles(monkeypatch):
    """Load app.py again to get the unmocked function (the webapp fixture patches it)."""
    env = {
        "FLASK_SECRET_KEY": "s", "DISCORD_CLIENT_ID": "c", "DISCORD_CLIENT_SECRET": "c",
        "DISCORD_TOKEN": "bot-token", "DISCORD_GUILD_ID": "111", "DISCORD_MOD_ID": "900",
        "REDIS_HOST": "x", "DB_USERNAME": "u", "DB_PASSWORD": "p", "DB_HOST": "h",
        "DB_PORT": "1", "DB_NAME": "n",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    stub_redis(monkeypatch)
    fake_db = types.ModuleType("mariadb")
    fake_db.Error = type("Error", (Exception,), {})
    monkeypatch.setitem(sys.modules, "mariadb", fake_db)
    spec = importlib.util.spec_from_file_location("webui_backend_app_fetch", APP_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_member_roles_results(real_fetch_member_roles, monkeypatch):
    m = real_fetch_member_roles
    get = MagicMock(return_value=fake_response(200, roles=["900", "5"]))
    monkeypatch.setattr(m.requests, "get", get)
    assert m.fetch_member_roles("42") == {"900", "5"}
    assert get.call_args.args[0].endswith("/guilds/111/members/42")
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bot bot-token"}

    get.return_value = fake_response(404)
    assert m.fetch_member_roles("42") is None


def test_fetch_member_roles_errors(real_fetch_member_roles, monkeypatch):
    m = real_fetch_member_roles
    get = MagicMock(return_value=fake_response(429, headers={"Retry-After": "7.5"}))
    monkeypatch.setattr(m.requests, "get", get)
    with pytest.raises(m.TransientRoleCheckError) as err:
        m.fetch_member_roles("42")
    assert err.value.retry_after == 7.5 and err.value.status == 429

    for status in (401, 403, 500):
        get.return_value = fake_response(status)
        with pytest.raises(m.TransientRoleCheckError) as err:
            m.fetch_member_roles("42")
        assert err.value.status == status and err.value.retry_after is None

    get.side_effect = requests.exceptions.ConnectionError("down")
    with pytest.raises(m.TransientRoleCheckError) as err:
        m.fetch_member_roles("42")
    assert err.value.status is None


# --- OAuth callback ---

def test_callback_sets_roles_checked_at(webapp, monkeypatch):
    def fake_post(*a, **k):
        r = MagicMock(); r.json.return_value = {"access_token": "tok"}; return r

    def fake_get(url, **k):
        r = MagicMock()
        r.json.return_value = ([{"id": "111"}] if url.endswith("/guilds") else
                               {"id": "42", "username": "mod", "discriminator": "0"})
        return r

    monkeypatch.setattr(webapp.requests, "post", fake_post)
    monkeypatch.setattr(webapp.requests, "get", fake_get)
    webapp.clock["now"] = T0 + 5
    client = webapp.app.test_client()
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    resp = client.get("/api/auth/discord/callback?code=c&state=st")
    assert resp.status_code == 302
    data = session_data(client)
    assert data["user_id"] == "42" and data["is_authorized"] is True
    assert data["roles_checked_at"] == T0 + 5
    webapp.fetch.assert_called_once_with("42")


# --- Durable revocation ---

def test_revocation_writes_key_with_long_ttl(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.return_value = set()
    webapp.clock["now"] = T0 + 15 * MIN
    assert client.get("/api/_protected").status_code == 401
    assert "revoked:42" in webapp.keys.data
    assert webapp.keys.ttls["revoked:42"] >= webapp.ROLE_MAX_UNVERIFIED


def test_404_writes_revocation_key(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.return_value = None
    webapp.clock["now"] = T0 + 15 * MIN
    assert client.get("/api/_protected").status_code == 401
    assert "revoked:42" in webapp.keys.data


def test_transient_error_does_not_revoke(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("x", status=429)
    webapp.clock["now"] = T0 + 15 * MIN
    assert client.get("/api/_protected").status_code == 200
    assert webapp.keys.data == {}


def test_stale_session_resurrected_after_revocation_still_gets_401(webapp):
    """A clears the session; B (429, started with the old session) saves after A."""
    client = webapp.app.test_client()
    login(client)
    webapp.fetch.return_value = set()
    webapp.clock["now"] = T0 + 15 * MIN
    assert client.get("/api/_protected").status_code == 401
    # request B, started before, saves its old session + retry_at after A cleared it
    login(client, roles_retry_at=T0 + 16 * MIN)
    webapp.fetch.side_effect = webapp.TransientRoleCheckError("rate", status=429)
    webapp.clock["now"] = T0 + 16 * MIN
    assert client.get("/api/_protected").status_code == 401
    assert not allowed(client, "/api/auth/status")
    # even after the back-off ends, without the key Discord's 429 would keep the session
    webapp.clock["now"] = T0 + 17 * MIN
    login(client)
    assert client.get("/api/_protected").status_code == 401


def test_revocation_applies_to_all_sessions_of_user(webapp):
    c1, c2 = webapp.app.test_client(), webapp.app.test_client()
    login(c1)
    login(c2)
    webapp.fetch.return_value = set()
    webapp.clock["now"] = T0 + 15 * MIN
    assert c1.get("/api/_protected").status_code == 401
    webapp.fetch.reset_mock()
    webapp.clock["now"] = T0 + 16 * MIN # c2 is fresh enough to skip a check otherwise
    assert c2.get("/api/_protected").status_code == 401
    webapp.fetch.assert_not_called()


def test_fresh_session_is_denied_while_revoked(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.keys.set("revoked:42", "1", ex=10)
    assert client.get("/api/_protected").status_code == 401
    webapp.fetch.assert_not_called()


def test_redis_error_on_revocation_read_fails_closed(webapp):
    client = webapp.app.test_client()
    login(client)
    webapp.keys.fail = True
    assert client.get("/api/_protected").status_code == 401
    assert not allowed(client, "/api/auth/status")
    webapp.fetch.assert_not_called()


def mock_oauth(webapp, monkeypatch):
    def fake_post(*a, **k):
        r = MagicMock(); r.json.return_value = {"access_token": "tok"}; return r

    def fake_get(url, **k):
        r = MagicMock()
        r.json.return_value = ([{"id": "111"}] if url.endswith("/guilds") else
                               {"id": "42", "username": "mod", "discriminator": "0"})
        return r

    monkeypatch.setattr(webapp.requests, "post", fake_post)
    monkeypatch.setattr(webapp.requests, "get", fake_get)


def test_login_with_mod_role_lifts_revocation(webapp, monkeypatch):
    mock_oauth(webapp, monkeypatch)
    webapp.keys.set("revoked:42", "1", ex=3600)
    client = webapp.app.test_client()
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    assert client.get("/api/auth/discord/callback?code=c&state=st").status_code == 302
    assert "revoked:42" not in webapp.keys.data
    assert client.get("/api/_protected").status_code == 200


def test_login_without_mod_role_keeps_revocation(webapp, monkeypatch):
    mock_oauth(webapp, monkeypatch)
    webapp.fetch.return_value = {"123"}
    webapp.keys.set("revoked:42", "1", ex=3600)
    client = webapp.app.test_client()
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    client.get("/api/auth/discord/callback?code=c&state=st")
    assert "revoked:42" in webapp.keys.data


def test_callback_regenerates_sid(webapp, monkeypatch):
    """The cookie-session swap has no sid, so a recording interface checks the call."""
    mock_oauth(webapp, monkeypatch)
    calls = []

    class Recording(type(webapp.app.session_interface)):
        def regenerate(self, session):
            calls.append(dict(session)) # must already hold user_id: empty sessions are skipped

    webapp.app.session_interface = Recording()
    client = webapp.app.test_client()
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    assert client.get("/api/auth/discord/callback?code=c&state=st").status_code == 302
    assert len(calls) == 1 and calls[0]["user_id"] == "42"


def test_callback_without_regenerate_still_logs_in(webapp, monkeypatch):
    mock_oauth(webapp, monkeypatch)
    client = webapp.app.test_client()
    with client.session_transaction() as sess:
        sess["oauth_state"] = "st"
    assert not hasattr(webapp.app.session_interface, "regenerate")
    assert client.get("/api/auth/discord/callback?code=c&state=st").status_code == 302
    assert session_data(client)["user_id"] == "42"
