"""Signing in and out, sessions, CSRF and passwords (auth/)."""
from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from fastapi import APIRouter
from sqlalchemy import func, select, update

from cojidaily.auth import api as auth
from cojidaily.auth.models import Session, User
from cojidaily.auth.passwords import check_password, make_password
from cojidaily.main import create_app
from cojidaily.platform import clock

from .conftest import PASSWORD, make_user, sign_in


@pytest.fixture
def app(settings):
    """The app, with two routes that need a signed-in account."""
    app = create_app(settings)
    probe = APIRouter(prefix="/api/probe")

    @probe.get("/whoami")
    def whoami(principal: auth.Signed):
        return {"username": principal.username, "id": str(principal.user_id)}

    @probe.post("/write")
    def write(principal: auth.Signed):
        return {"ok": True}

    app.include_router(probe)
    return app


def sessions_count(sessions):
    with sessions() as db:
        return db.scalar(select(func.count()).select_from(Session))


def test_signed_out_the_session_has_no_user_and_routes_answer_401(client):
    body = client.get("/api/session").json()
    assert body["user"] is None
    assert body["timezone"] == "America/New_York" and body["currency"] == "USD"
    assert len(body["csrf_token"]) == 43
    assert client.cookies["coji_csrf"] == body["csrf_token"]
    response = client.get("/api/probe/whoami")
    assert (response.status_code, response.json()) == (401, {"error": "請先登入。"})


def test_signing_in_opens_a_session_and_rotates_the_csrf_token(client, sessions, owner):
    first = client.get("/api/session").json()["csrf_token"]
    response = client.post("/api/auth/login", json={"username": "yuchen", "password": PASSWORD},
                           headers={"X-CSRF-Token": first})
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"id": str(owner), "username": "yuchen"}
    assert body["csrf_token"] != first
    cookie = response.headers.get_list("set-cookie")
    assert any(c.startswith("coji_session=") and "HttpOnly" in c and "SameSite=lax" in c for c in cookie)
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    assert client.get("/api/probe/whoami").json()["username"] == "yuchen"
    assert client.post("/api/probe/write").json() == {"ok": True}
    # Only a hash of the cookie's token is stored.
    with sessions() as db:
        stored = db.scalar(select(Session.token_hash))
    assert stored != client.cookies["coji_session"] and len(stored) == 64


def test_a_wrong_password_or_unknown_name_says_the_same_thing(client, owner):
    token = client.get("/api/session").json()["csrf_token"]
    for name, password in (("yuchen", "wrong password"), ("nobody", PASSWORD)):
        response = client.post("/api/auth/login", json={"username": name, "password": password},
                               headers={"X-CSRF-Token": token})
        assert response.status_code == 400
        assert response.json() == {"error": "請檢查輸入內容。", "fields": {"__all__": ["帳號或密碼不正確。"]}}


def test_the_login_body_must_be_two_strings(client, owner):
    token = client.get("/api/session").json()["csrf_token"]
    response = client.post("/api/auth/login", json={"username": "yuchen", "password": 12345678, "extra": 1},
                           headers={"X-CSRF-Token": token})
    assert response.status_code == 400
    assert response.json()["fields"] == {"password": ["請使用文字。"], "extra": ["不支援的欄位。"]}


def test_writes_need_the_csrf_token_and_a_trusted_origin(signed):
    token = signed.headers.pop("X-CSRF-Token")
    refused = signed.post("/api/probe/write")
    assert (refused.status_code, refused.json()) == (403, {"error": "驗證已過期，請重新整理後再試。"})
    assert signed.post("/api/probe/write", headers={"X-CSRF-Token": "x" * 43}).status_code == 403
    assert signed.post("/api/probe/write", headers={"X-CSRF-Token": token}).status_code == 200
    for origin, status in (("http://testserver", 200), ("http://localhost:5173", 200), ("https://evil.example", 403)):
        response = signed.post("/api/probe/write", headers={"X-CSRF-Token": token, "Origin": origin})
        assert response.status_code == status, origin
    # Reads need no token.
    assert signed.get("/api/probe/whoami").status_code == 200


def test_signing_out_ends_the_session_on_the_server(signed, sessions):
    old_cookie = signed.cookies["coji_session"]
    body = signed.post("/api/auth/logout").json()
    assert body["user"] is None
    assert sessions_count(sessions) == 0
    signed.cookies.set("coji_session", old_cookie)
    assert signed.get("/api/probe/whoami").status_code == 401


def test_signing_in_again_replaces_the_old_session(signed, sessions):
    sign_in(signed)
    assert sessions_count(sessions) == 1


def test_a_new_password_ends_older_sessions(signed, sessions):
    with sessions() as db:
        assert auth.set_password(db, "yuchen", "a brand new password")
        db.commit()
    assert signed.get("/api/probe/whoami").status_code == 401
    sign_in(signed, password="a brand new password")
    assert signed.get("/api/probe/whoami").status_code == 200


def test_expired_sessions_and_inactive_accounts_sign_nobody_in(signed, sessions):
    with sessions() as db:
        db.execute(update(Session).values(expires_at=clock.now() - timedelta(seconds=1)))
        db.commit()
    assert signed.get("/api/probe/whoami").status_code == 401
    sign_in(signed)
    assert sessions_count(sessions) == 1  # the expired one went at this sign-in
    with sessions() as db:
        db.execute(update(User).values(is_active=False))
        db.commit()
    assert signed.get("/api/probe/whoami").status_code == 401
    token = signed.get("/api/session").json()["csrf_token"]
    assert signed.post("/api/auth/login", json={"username": "yuchen", "password": PASSWORD},
                       headers={"X-CSRF-Token": token}).status_code == 400


def test_accounts_need_a_free_name_and_a_reasonable_password(sessions, owner):
    from cojidaily.platform.errors import ApiError

    for name, password, field in (("yuchen", PASSWORD, "username"), ("", PASSWORD, "username"),
                                  ("two words", PASSWORD, "username"), ("other", "short", "password"),
                                  ("other", "12345678901", "password")):
        with pytest.raises(ApiError) as error:
            make_user(sessions, name, password)
        assert field in error.value.fields, (name, password)


def test_password_hashes_are_argon2id_with_the_old_apps_cost():
    encoded = make_password(PASSWORD)
    assert encoded.startswith("$argon2id$v=19$m=102400,t=2,p=8$")
    assert check_password(PASSWORD, encoded) == (True, False)
    assert check_password("other", encoded) == (False, False)
    assert check_password(PASSWORD, None) == (False, False)
    cheaper = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    assert check_password(PASSWORD, cheaper) == (True, True)  # remade at the next sign-in
