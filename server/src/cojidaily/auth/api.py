"""What other modules may use from auth: who the request is, and making accounts (the CLI)."""
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.db import Db
from ..platform.errors import ApiError
from . import service
from .csrf import CsrfMiddleware  # noqa: F401  (main.py installs it)
from .models import User

SIGN_IN = "請先登入。"


@dataclass(frozen=True)
class Principal:
    """The signed-in account. user_id is what other modules store as owner_id."""
    user_id: uuid.UUID
    username: str


def current_principal(request: Request, db: Session) -> Principal | None:
    user = service.user_for(db, request.cookies.get(service.COOKIE), request.app.state.settings.secret_key)
    return None if user is None else Principal(user.id, user.username)


def require_principal(request: Request, db: Db) -> Principal:
    principal = current_principal(request, db)
    if principal is None:
        raise ApiError(401, SIGN_IN)
    return principal


Signed = Annotated[Principal, Depends(require_principal)]


def create_user(db: Session, username: str, password: str) -> uuid.UUID:
    return service.create_user(db, username, password).id


def set_password(db: Session, username: str, password: str) -> bool:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        return False
    service.set_password(db, user, password)
    return True
