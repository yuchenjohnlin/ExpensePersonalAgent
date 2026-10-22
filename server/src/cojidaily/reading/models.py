import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..platform.db import Base


class Reading(Base):
    """One attempt to read some photos. Its status is what a page shows while it waits."""
    __tablename__ = "reading_reading"
    __table_args__ = (CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="status"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB)  # how the photos were prepared and the model asked
    result: Mapped[dict | None] = mapped_column(JSONB)  # the draft, when succeeded
    raw_response: Mapped[dict] = mapped_column(JSONB)  # the model's own answer, without secrets
    error_code: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str] = mapped_column(Text)
    # The job to enqueue when done, with this payload plus reading_id: how the requester hears back.
    then_kind: Mapped[str] = mapped_column(Text)
    then_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)

    photos: Mapped[list["ReadingPhoto"]] = relationship(order_by="ReadingPhoto.position", lazy="selectin")


class ReadingPhoto(Base):
    """The photos a reading reads, in order (positions 1..n are the model's "source image" numbers)."""
    __tablename__ = "reading_photo"

    reading_id: Mapped[int] = mapped_column(ForeignKey("reading_reading.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos_photo.id", ondelete="RESTRICT"))
