"""
End-to-end auth flows through the real app (TestClient + fake Supabase):
login, refresh, logout — the credential-handling logic that guards everything
else. The existing suite proved the JWT primitives (test_security.py); this
file proves the ROUTE wiring around them: correct status codes, correct token
types issued, revocation honoured.

Password hashes are real bcrypt via the app's own security.hash_password, so
the verify path is exercised for real — no hash stubbing.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fake_supabase import install
from app.core import security

BIZ = "b0000000-0000-0000-0000-0000000000b1"
USER_ID = "d0000000-0000-0000-0000-0000000000d1"
EMAIL = "owner@example.com"
PASSWORD = "Str0ng!Passw0rd"

# bcrypt is deliberately slow — hash once for the whole module.
_PW_HASH = security.hash_password(PASSWORD)


def _user_row(**over):
    row = {
        "id": USER_ID, "business_id": BIZ, "email": EMAIL,
        "password_hash": _PW_HASH, "role": "admin", "status": "active",
        "first_name": "Owner", "last_name": "Person",
    }
    row.update(over)
    return row


@pytest.fixture
def client(monkeypatch):
    import app.main as m
    from app.core import public_rate_limit as prl

    db = install(monkeypatch, {"ts_users": [_user_row()]})
    prl._hits.clear()
    yield TestClient(m.app, raise_server_exceptions=False), db
    prl._hits.clear()


def _login(client, password=PASSWORD):
    return client.post("/api/techscape/v1/auth/login",
                       json={"email": EMAIL, "password": password})


def test_login_success_issues_both_token_families(client):
    c, _ = client
    r = _login(c)
    assert r.status_code == 200, r.text
    body = r.json()

    access = security.decode_access_token(body["access_token"])
    assert access["type"] == "access"
    assert access["sub"] == USER_ID
    assert access["biz"] == BIZ

    refresh = security.decode_refresh_token(body["refresh_token"])
    assert refresh["type"] == "refresh"
    assert refresh["sub"] == USER_ID

    # the two families must not be interchangeable
    with pytest.raises(Exception):
        security.decode_access_token(body["refresh_token"])


def test_login_wrong_password_is_401_and_leaks_nothing(client):
    c, _ = client
    r = _login(c, password="WrongPassword1!")
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid credentials"}
    assert "access_token" not in r.text


def test_login_response_never_contains_password_hash(client):
    c, _ = client
    r = _login(c)
    assert _PW_HASH not in r.text
    assert "password_hash" not in r.text


def test_refresh_rotates_and_returns_valid_access(client):
    c, _ = client
    tokens = _login(c).json()
    r = c.post("/api/techscape/v1/auth/refresh",
               json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    new_access = security.decode_access_token(r.json()["access_token"])
    assert new_access["sub"] == USER_ID


def test_refresh_rejects_access_token(client):
    c, _ = client
    tokens = _login(c).json()
    r = c.post("/api/techscape/v1/auth/refresh",
               json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


def test_refresh_rejects_garbage(client):
    c, _ = client
    r = c.post("/api/techscape/v1/auth/refresh",
               json={"refresh_token": "junk.junk.junk"})
    assert r.status_code == 401


def test_logout_blacklists_the_token(client):
    c, _ = client
    access = _login(c).json()["access_token"]
    r = c.post("/api/techscape/v1/auth/logout",
               headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    jti = security.decode_access_token(access)["jti"]
    assert security.is_jti_blacklisted(jti) is True


def test_logout_without_token_is_401(client):
    c, _ = client
    assert c.post("/api/techscape/v1/auth/logout").status_code == 401


def test_me_returns_principal_with_valid_token(client):
    c, db = client
    db.tables["ts_businesses"] = [{
        "id": BIZ, "status": "active", "name": "Biz", "subscription_tier": "starter",
        "contact_email": "biz@example.com",
    }]
    access = _login(c).json()["access_token"]
    r = c.get("/api/techscape/v1/auth/me",
              headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    assert "password_hash" not in r.text
    assert "api_key_hash" not in r.text
