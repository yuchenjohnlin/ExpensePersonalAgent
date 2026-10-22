"""What other modules may use from the photo library: receive an upload, store its photos, and
read or describe them by id."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.blobstore import BlobStore
from . import service
from .images import PhotoRejected  # noqa: F401  (raised by store)
from .models import Photo
from .service import DuplicatePhotos  # noqa: F401  (raised by store)
from .uploads import Upload, receive  # noqa: F401

MAX_PHOTOS_PER_UPLOAD = 20


def store(db: Session, blobs: BlobStore, owner: uuid.UUID, channel: str, files: list[tuple[str, bytes]], *,
          allow_duplicates: bool = False) -> list[int]:
    """The photos' ids, in the order sent; in the caller's transaction (see service.store)."""
    return [photo.id for photo in service.store(db, blobs, owner, channel, files, allow_duplicates=allow_duplicates)]


def original_bytes(db: Session, blobs: BlobStore, photo_id: int) -> bytes:
    photo = db.get(Photo, photo_id)
    return blobs.get(service.file_key(photo.storage_key, photo.extension, "original"))


@dataclass(frozen=True)
class PhotoInfo:
    id: int
    original_name: str
    width: int
    height: int
    preview_url: str
    thumbnail_url: str
    original_url: str


def describe(db: Session, owner: uuid.UUID, photo_ids) -> dict[int, PhotoInfo]:
    ids = list(photo_ids)
    if not ids:
        return {}
    photos = db.scalars(select(Photo).where(Photo.owner_id == owner, Photo.id.in_(ids)))
    return {p.id: PhotoInfo(p.id, p.original_name, p.width, p.height, f"/api/photos/{p.id}/preview",
                            f"/api/photos/{p.id}/thumbnail", f"/api/photos/{p.id}/original") for p in photos}
