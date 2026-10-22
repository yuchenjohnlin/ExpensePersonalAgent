"""GET /api/photos/{id}/preview | thumbnail | original: the files, only to their owner."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from ..auth.api import Signed
from ..platform.db import Db
from . import service

router = APIRouter(prefix="/api")
# A photo never changes under its URL, so the browser may keep previews; originals are not cached.
CACHED = {"Cache-Control": "private, max-age=31536000, immutable"}


@router.get("/photos/{photo_id}/{variant}")
def photo_file(photo_id: int, variant: Literal["preview", "thumbnail", "original"], request: Request,
               principal: Signed, db: Db) -> FileResponse:
    photo = service.owned_photo(db, principal.user_id, photo_id)
    path = request.app.state.blobs.path(service.file_key(photo.storage_key, photo.extension, variant))
    if variant != "original":
        return FileResponse(path, media_type="image/jpeg", headers=CACHED)
    disposition = f"attachment; filename*=UTF-8''{quote(photo.original_name, safe="")}"
    return FileResponse(path, media_type=photo.content_type,
                        headers={"Cache-Control": "private, no-store", "Content-Disposition": disposition})
