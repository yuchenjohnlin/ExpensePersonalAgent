"""Storing photos: one upload's photos are checked, then saved together or not at all."""
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..platform import clock
from ..platform.blobstore import BlobStore
from ..platform.db import on_rollback
from ..platform.errors import not_found
from .images import prepare_photo
from .models import Photo, Upload

VARIANTS = {"preview": "preview.jpg", "thumbnail": "thumb.jpg"}


class DuplicatePhotos(Exception):
    """Photos whose bytes are already stored (or sent twice in this upload); nothing was saved."""

    def __init__(self, duplicates: list[dict]):
        super().__init__("duplicate photos")
        self.duplicates = duplicates


def file_key(storage_key, extension: str, variant: str) -> str:
    return f"photos/{storage_key}/{VARIANTS.get(variant) or f'original.{extension}'}"


def duplicates(db: Session, owner: uuid.UUID, prepared) -> list[dict]:
    """For each photo in the upload whose SHA-256 is already one of the owner's photos, or appears
    again in this upload: its index, the stored photos, and the other indices."""
    indices = defaultdict(list)
    for index, photo in enumerate(prepared):
        indices[photo.sha256].append(index)
    existing = defaultdict(list)
    for photo_id, digest in db.execute(select(Photo.id, Photo.sha256).where(
            Photo.owner_id == owner, Photo.sha256.in_(list(indices))).order_by(Photo.id)):
        existing[digest].append(photo_id)
    found = []
    for index, photo in enumerate(prepared):
        others = [other for other in indices[photo.sha256] if other != index]
        if existing[photo.sha256] or others:
            found.append({"index": index, "existing_photo_ids": existing[photo.sha256], "same_as_indices": others})
    return found


def store(db: Session, blobs: BlobStore, owner: uuid.UUID, channel: str, files: list[tuple[str, bytes]], *,
          allow_duplicates: bool) -> list[Photo]:
    """Check every photo (PhotoRejected), refuse duplicates unless allowed (DuplicatePhotos), then
    add the upload and its photos to the caller's transaction and write their files. If that
    transaction does not commit, the files are deleted again."""
    prepared = [prepare_photo(name, content) for name, content in files]
    # One upload at a time per owner from the duplicate check to the commit, so two uploads of
    # the same photo cannot both pass the check.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"photos:{owner}", 0))))
    found = duplicates(db, owner, prepared)
    if found and not allow_duplicates:
        raise DuplicatePhotos(found)
    moment = clock.now()
    upload = Upload(owner_id=owner, channel=channel, created_at=moment)
    db.add(upload)
    db.flush()
    photos = [Photo(owner_id=owner, upload_id=upload.id, position=position, storage_key=photo.storage_key,
                    original_name=photo.original_name, size=len(photo.original), width=photo.width,
                    height=photo.height, content_type=photo.content_type, extension=photo.extension,
                    sha256=photo.sha256, created_at=moment)
              for position, photo in enumerate(prepared, 1)]
    db.add_all(photos)
    db.flush()
    written: list[str] = []

    def remove_files():
        for key in written:
            blobs.delete(key)

    on_rollback(db, remove_files)
    for photo in prepared:
        for variant, content in (("original", photo.original), ("preview", photo.preview),
                                 ("thumbnail", photo.thumbnail)):
            key = file_key(photo.storage_key, photo.extension, variant)
            blobs.put(key, content)
            written.append(key)
    return photos


def owned_photo(db: Session, owner: uuid.UUID, photo_id: int) -> Photo:
    photo = db.scalar(select(Photo).where(Photo.id == photo_id, Photo.owner_id == owner))
    if photo is None:
        raise not_found("照片")
    return photo
