"""Requesting a reading and running it in the worker."""
import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..photos import api as photos
from ..platform import clock, jobs
from ..platform.blobstore import BlobStore
from ..platform.settings import Settings
from .engine import ExtractionFailure, prepare_jpeg_bytes
from .models import Reading, ReadingPhoto
from .providers import provider

logger = logging.getLogger(__name__)
RUN = "reading.run"
FINISHED = ("succeeded", "failed")


def request(db: Session, settings: Settings, owner: uuid.UUID, photo_ids: list[int], *, then_kind: str = "",
            then_payload: dict | None = None) -> Reading:
    """A queued reading of these photos (in this order) and the job that runs it, in the caller's
    transaction. When it is done, a `then_kind` job is enqueued with then_payload + reading_id."""
    service = provider(settings)
    reading = Reading(owner_id=owner, status="queued", provider=settings.reading_provider,
                      model=service.model() if service else "", prompt_version=service.prompt_version if service else "",
                      params=service.parameters() if service else {}, result=None, raw_response={}, error_code="",
                      error_message="", then_kind=then_kind, then_payload=then_payload or {}, created_at=clock.now())
    db.add(reading)
    db.flush()
    db.add_all([ReadingPhoto(reading_id=reading.id, position=position, photo_id=photo_id)
                for position, photo_id in enumerate(photo_ids, 1)])
    jobs.enqueue(db, RUN, {"reading_id": reading.id})
    db.flush()
    return reading


def run(sessions: sessionmaker[Session], payload: dict, *, blobs: BlobStore, settings: Settings) -> None:
    """The worker's job: mark the reading running, read without holding a transaction, store what
    came back, and enqueue the requester's job. Safe to run twice: a finished reading is left alone."""
    reading_id = payload["reading_id"]
    with sessions() as db:
        reading = db.scalar(select(Reading).where(Reading.id == reading_id).with_for_update())
        if reading is None or reading.status in FINISHED:
            return
        reading.status, reading.started_at = "running", clock.now()
        sources = [(photo.position, photo.photo_id) for photo in reading.photos]
        name = reading.provider
        db.commit()
    started = time.monotonic()
    result, raw, code, message, dimensions = None, {}, "", "", []
    try:
        service = provider(settings)
        if service is None or service.id != name:
            raise ExtractionFailure("unknown_provider", f"沒有名為 {name!r} 的讀取服務。")
        try:
            with sessions() as db:
                originals = [(position, photos.original_bytes(db, blobs, photo_id)) for position, photo_id in sources]
        except OSError as error:
            raise ExtractionFailure("photo_unavailable", "照片檔案讀不到，請重新上傳。") from error
        images = []
        for position, original in originals:
            jpeg, size = prepare_jpeg_bytes(original)
            images.append((position, jpeg))
            dimensions.append(size)
        result, raw = service.read(images)
    except ExtractionFailure as failure:
        code, message, raw = failure.code, failure.message, failure.raw_response
    except Exception:  # a bug or a surprise: the reading still ends, as failed
        logger.exception("reading %s failed unexpectedly", reading_id)
        code, message = "internal", "讀取時發生內部錯誤。"
    elapsed = int((time.monotonic() - started) * 1000)
    with sessions() as db:
        reading = db.scalar(select(Reading).where(Reading.id == reading_id).with_for_update())
        if reading.status in FINISHED:  # another worker finished it after this one's lease ran out
            return
        reading.status = "failed" if code else "succeeded"
        reading.result, reading.raw_response = result, raw
        reading.error_code, reading.error_message = code, message
        reading.params = reading.params | {"image_dimensions": dimensions}
        reading.completed_at, reading.elapsed_ms = clock.now(), elapsed
        if reading.then_kind:
            # Ahead of readings still waiting: the requester's step is quick and someone may be watching.
            jobs.enqueue(db, reading.then_kind, reading.then_payload | {"reading_id": reading.id},
                         priority=jobs.FOLLOW_UP)
        db.commit()
    logger.info("reading %s %s in %s ms%s", reading_id, "failed" if code else "succeeded", elapsed,
                f" ({code})" if code else "")
