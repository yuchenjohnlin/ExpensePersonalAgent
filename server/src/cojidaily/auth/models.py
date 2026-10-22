import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..platform.db import Base


class User(Base):
    __tablename__ = "auth_user"

    # The id other modules store as owner_id. A UUID, as an identity provider's subject would be.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    """One sign-in. The cookie carries a random token; only its SHA-256 is stored, so the table
    alone cannot sign anyone in."""
    __tablename__ = "auth_session"
    __table_args__ = (Index("ix_auth_session_user_id", "user_id"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auth_user.id", ondelete="CASCADE"))
    # An HMAC of the password hash it was opened with: a new password ends every older session.
    password_tag: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
