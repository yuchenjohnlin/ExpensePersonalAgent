"""GET /api/session, POST /api/auth/login, POST /api/auth/logout."""
import uuid
from datetime import date

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from ..platform import clock
from ..platform.db import Db
from ..platform.errors import invalid
from . import csrf, service
from .api import Principal, current_principal

router = APIRouter(prefix="/api")


class UserOut(BaseModel):
    id: uuid.UUID
    username: str


class SessionOut(BaseModel):
    csrf_token: str
    user: UserOut | None  # null until signed in
    today: date  # the ledger's today, in its timezone
    timezone: str
    currency: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str
    password: str


def session_out(request: Request, response: Response, principal: Principal | None, rotate=False) -> dict:
    settings = request.app.state.settings
    return {
        "csrf_token": csrf.token(request, response, secure=settings.secure_cookies, rotate=rotate),
        "user": None if principal is None else {"id": principal.user_id, "username": principal.username},
        "today": clock.today(settings.timezone),
        "timezone": settings.timezone,
        "currency": "USD",
    }


@router.get("/session")
def session(request: Request, response: Response, db: Db) -> SessionOut:
    return session_out(request, response, current_principal(request, db))


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Db) -> SessionOut:
    """Check the password and open a server-side session. The answer carries a new csrf_token,
    which the page must use from now on."""
    settings = request.app.state.settings
    user = service.authenticate(db, body.username, body.password)
    if user is None:
        raise invalid({"__all__": ["帳號或密碼不正確。"]})
    service.close_session(db, request.cookies.get(service.COOKIE))
    token = service.open_session(db, user, settings.secret_key)
    db.commit()
    seconds = int(service.AGE.total_seconds())
    response.set_cookie(service.COOKIE, token, max_age=seconds, path="/", httponly=True, samesite="lax",
                        secure=settings.secure_cookies)
    return session_out(request, response, Principal(user.id, user.username), rotate=True)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Db) -> SessionOut:
    """End the session on the server, so the old cookie no longer signs anyone in."""
    service.close_session(db, request.cookies.get(service.COOKIE))
    db.commit()
    response.delete_cookie(service.COOKIE, path="/", httponly=True, samesite="lax")
    return session_out(request, response, None)
