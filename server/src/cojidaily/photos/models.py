import uuid
from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text,
                        UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from ..platform.db import Base

class Upload(Base):
    """Photos that arrived together: from where, and when. Not a document; a later step may find
    several documents in one upload. Channels so far: the receipt page (later the gallery, the
    agent's chat)."""
    __tablename__ = "photos_upload"
    __table_args__ = (CheckConstraint("channel IN ('receipt_page')", name="channel"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    channel: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Photo(Base):
    """One photo. The original's bytes are never rewritten; a preview and a thumbnail sit beside it."""
    __tablename__ = "photos_photo"
    __table_args__ = (
        UniqueConstraint("upload_id", "position", name="uq_photos_photo_upload_position"),
        Index("ix_photos_photo_owner_sha256", "owner_id", "sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    upload_id: Mapped[int] = mapped_column(ForeignKey("photos_upload.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)  # 1-based, in the order sent
    storage_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)  # bytes of the original
    width: Mapped[int] = mapped_column(Integer)  # after EXIF orientation
    height: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(32))
    extension: Mapped[str] = mapped_column(String(5))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
