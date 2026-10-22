"""The photo library (photos/): checking photos, storing them with their files, duplicates, and serving them."""
import hashlib
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import func, select

from cojidaily.photos import api as photos
from cojidaily.photos.images import prepare_photo
from cojidaily.photos.models import Photo, Upload

from .conftest import make_user, sign_in
from .photo_samples import drawing


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_previews_and_thumbnails_are_the_old_apps_bytes():
    # Hashes of what api/app/storage.py (backend/'s code) makes from the same drawing, Pillow 12.3.0.
    prepared = prepare_photo("receipt.png", drawing())
    assert (prepared.width, prepared.height, prepared.content_type, prepared.extension) == (2400, 1500, "image/png", "png")
    assert sha(prepared.preview) == "12490d88f65d3a3b17e25813e787ed0f294b38a3771ffd64ffc12219337183a6"
    assert sha(prepared.thumbnail) == "a383a46ef2088e67498ecf0e84df6554c492016f3333c84f42f778edef2f79c1"


@pytest.mark.parametrize("content, message", [
    (b"not an image", "照片無法讀取，請重新拍照或選擇其他圖片。"),
    (drawing("GIF", (40, 40)), "支援 JPEG、PNG、WebP 和 HEIC／HEIF 靜態照片。"),
])
def test_only_real_still_photos_are_taken(content, message):
    with pytest.raises(photos.PhotoRejected) as refused:
        prepare_photo("x", content)
    assert refused.value.message == message


def test_too_many_pixels_is_refused_before_decoding():
    out = BytesIO()
    Image.new("L", (8000, 5001)).save(out, format="PNG")
    with pytest.raises(photos.PhotoRejected) as refused:
        prepare_photo("x", out.getvalue())
    assert refused.value.message == "照片最多 4,000 萬像素。"


def stored(app, owner, files, **options):
    with app.state.sessions() as db:
        ids = photos.store(db, app.state.blobs, owner, "receipt_page", files, **options)
        db.commit()
    return ids


def test_an_upload_stores_each_photo_with_its_three_files(app, owner):
    ids = stored(app, owner, [("top.png", drawing()), ("bottom.jpg", drawing("JPEG", shade=9))])
    with app.state.sessions() as db:
        rows = db.scalars(select(Photo).order_by(Photo.id)).all()
        upload = db.scalar(select(Upload))
    assert [p.id for p in rows] == ids
    assert [(p.position, p.original_name, p.upload_id) for p in rows] == [(1, "top.png", upload.id),
                                                                       (2, "bottom.jpg", upload.id)]
    assert upload.channel == "receipt_page"
    files = sorted(path.name for path in (app.state.blobs.root / "photos").rglob("*") if path.is_file())
    assert files == ["original.jpg", "original.png", "preview.jpg", "preview.jpg", "thumb.jpg", "thumb.jpg"]
    with app.state.sessions() as db:
        assert photos.original_bytes(db, app.state.blobs, ids[0]) == drawing()


def test_duplicates_are_refused_unless_allowed_and_nothing_is_saved(app, owner):
    first = stored(app, owner, [("a.png", drawing())])
    with pytest.raises(photos.DuplicatePhotos) as refused:
        stored(app, owner, [("again.png", drawing()), ("new.png", drawing(shade=5)), ("twice.png", drawing(shade=5))])
    assert refused.value.duplicates == [
        {"index": 0, "existing_photo_ids": first, "same_as_indices": []},
        {"index": 1, "existing_photo_ids": [], "same_as_indices": [2]},
        {"index": 2, "existing_photo_ids": [], "same_as_indices": [1]},
    ]
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Photo)) == 1
    assert len(stored(app, owner, [("again.png", drawing())], allow_duplicates=True)) == 1


def test_another_owner_s_identical_photo_is_not_a_duplicate(app, sessions, owner):
    stored(app, owner, [("a.png", drawing())])
    assert len(stored(app, make_user(sessions, "someone"), [("a.png", drawing())])) == 1


def test_files_written_for_a_transaction_that_does_not_commit_are_removed(app, owner):
    with app.state.sessions() as db:
        photos.store(db, app.state.blobs, owner, "receipt_page", [("a.png", drawing())])
        assert any((app.state.blobs.root / "photos").rglob("original.png"))
        db.rollback()
    assert not (app.state.blobs.root / "photos").exists()


def test_photos_are_served_only_to_their_owner(app, client, sessions, owner):
    [photo_id] = stored(app, owner, [("Kroger 10/09.png", drawing())])
    assert client.get(f"/api/photos/{photo_id}/preview").status_code == 401
    sign_in(client)
    preview = client.get(f"/api/photos/{photo_id}/preview")
    assert preview.headers["content-type"] == "image/jpeg"
    assert preview.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert sha(preview.content) == "12490d88f65d3a3b17e25813e787ed0f294b38a3771ffd64ffc12219337183a6"
    original = client.get(f"/api/photos/{photo_id}/original")
    assert original.content == drawing()
    assert original.headers["content-disposition"] == "attachment; filename*=UTF-8''Kroger%2010%2F09.png"
    assert client.get(f"/api/photos/{photo_id}/huge").status_code == 400
    make_user(sessions, "someone")
    sign_in(client, "someone")
    assert client.get(f"/api/photos/{photo_id}/preview").status_code == 404
    with app.state.sessions() as db:
        assert photos.describe(db, owner, [photo_id])[photo_id].preview_url == f"/api/photos/{photo_id}/preview"
