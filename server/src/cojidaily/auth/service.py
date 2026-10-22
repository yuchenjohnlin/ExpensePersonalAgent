"""Accounts and sign-ins: server-side sessions behind an HttpOnly cookie (pm/decisions/session-cookie-auth.md)."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as Db

from ..platform import clock
from ..platform.errors import invalid
from .models import Session, User
from .passwords import check_password, make_password, password_problems

COOKIE = "coji_session"
AGE = timedelta(weeks=2)  # from signing in; not extended by use


def password_tag(secret_key: str, password_hash: str) -> str:
    key = hashlib.sha256(b"cojidaily.auth.session" + secret_key.encode()).digest()
    return hmac.new(key, password_hash.encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_username(username: str) -> str:
    username = username.strip()
    problems = []
    if not username:
        problems.append("請輸入帳號。")
    elif len(username) > 150 or any(c.isspace() for c in username):
        problems.append("帳號最多 150 個字元，不能有空白。")
    if problems:
        raise invalid({"username": problems})
    return username


def create_user(db: Db, username: str, password: str) -> User:
    username = clean_username(username)
    if problems := password_problems(password):
        raise invalid({"password": problems})
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise invalid({"username": ["這個帳號已經有人用了。"]})
    user = User(username=username, password_hash=make_password(password), is_active=True, created_at=clock.now())
    db.add(user)
    db.flush()
    return user


def set_password(db: Db, user: User, password: str) -> None:
    """A new password; every session opened with the old one stops working (password_tag)."""
    if problems := password_problems(password):
        raise invalid({"password": problems})
    user.password_hash = make_password(password)
    db.flush()


def authenticate(db: Db, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip()))
    correct, outdated = check_password(password, user.password_hash if user else None)
    if not correct or user is None or not user.is_active:
        return None
    if outdated:
        user.password_hash = make_password(password)
    return user


def open_session(db: Db, user: User, secret_key: str) -> str:
    """A new sign-in; returns the cookie's token. Expired sessions of this user go at the same time."""
    moment = clock.now()
    db.execute(delete(Session).where(Session.user_id == user.id, Session.expires_at <= moment))
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), user_id=user.id,
                   password_tag=password_tag(secret_key, user.password_hash), created_at=moment,
                   expires_at=moment + AGE))
    user.last_login_at = moment
    return token


def close_session(db: Db, token: str | None) -> None:
    if token:
        db.execute(delete(Session).where(Session.token_hash == token_hash(token)))


def user_for(db: Db, token: str | None, secret_key: str) -> User | None:
    """The signed-in user for a cookie's token: the session must exist, be unexpired, and have been
    opened with the user's current password; the user must be active."""
    if not token or len(token) > 100:
        return None
    row = db.execute(select(Session, User).join(User, User.id == Session.user_id)
                     .where(Session.token_hash == token_hash(token), Session.expires_at > clock.now())).first()
    if row is None:
        return None
    session, user = row
    if not user.is_active or not hmac.compare_digest(session.password_tag, password_tag(secret_key, user.password_hash)):
        return None
    return user
