"""What other modules may use from reading: ask for a reading, look at readings, check a result,
and the worker's handlers."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.blobstore import BlobStore
from ..platform.jobs import Handler
from ..platform.settings import Settings
from . import service
from .checks import arithmetic_warnings
from .models import Reading


def request(db: Session, settings: Settings, owner: uuid.UUID, photo_ids: list[int], *, then_kind: str = "",
            then_payload: dict | None = None) -> int:
    """Queue a reading of these photos (in order); when it is done, a `then_kind` job gets
    then_payload plus "reading_id". In the caller's transaction."""
    return service.request(db, settings, owner, photo_ids, then_kind=then_kind, then_payload=then_payload).id


@dataclass(frozen=True)
class ReadingView:
    id: int
    status: str  # queued, running, succeeded, failed
    provider: str
    model: str
    prompt_version: str
    result: dict | None
    error_code: str
    error_message: str
    created_at: datetime
    completed_at: datetime | None
    elapsed_ms: int | None
    photo_ids: list[int]
    usage: dict | None
    checks: list[str]  # the server's arithmetic checks on a succeeded result


def view(reading: Reading) -> ReadingView:
    return ReadingView(reading.id, reading.status, reading.provider, reading.model, reading.prompt_version,
                       reading.result, reading.error_code, reading.error_message, reading.created_at,
                       reading.completed_at, reading.elapsed_ms, [p.photo_id for p in reading.photos],
                       reading.raw_response.get("usage"),
                       arithmetic_warnings(reading.result) if reading.result is not None else [])


def get_many(db: Session, reading_ids) -> dict[int, ReadingView]:
    ids = list(reading_ids)
    if not ids:
        return {}
    return {r.id: view(r) for r in db.scalars(select(Reading).where(Reading.id.in_(ids)))}


def handlers(settings: Settings, blobs: BlobStore) -> dict[str, Handler]:
    return {service.RUN: partial(service.run, blobs=blobs, settings=settings)}
