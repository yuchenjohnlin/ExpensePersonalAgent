"""Files by key (platform/blobstore.py) and work undone when a transaction rolls back (platform/db.py)."""
import pytest
from sqlalchemy import text

from cojidaily.platform.blobstore import BlobStore
from cojidaily.platform.db import on_rollback


def test_files_go_in_and_come_back_by_key(tmp_path):
    blobs = BlobStore(tmp_path)
    blobs.put("photos/abc/original.jpg", b"jpeg bytes")
    assert blobs.get("photos/abc/original.jpg") == b"jpeg bytes"
    with pytest.raises(FileExistsError):
        blobs.put("photos/abc/original.jpg", b"other")
    blobs.delete("photos/abc/original.jpg")
    assert not (tmp_path / "photos").exists()  # empty folders go too
    blobs.delete("photos/abc/original.jpg")  # already gone is fine


@pytest.mark.parametrize("key", ["../outside", "/etc/passwd", "photos/../../x", "a//b", "", "photos/a b"])
def test_keys_cannot_leave_the_root(tmp_path, key):
    with pytest.raises(ValueError):
        BlobStore(tmp_path).put(key, b"")


def test_work_is_undone_when_its_transaction_does_not_commit(sessions):
    undone = []

    def register(db, name):
        db.execute(text("SELECT 1"))  # inside a transaction, as a service registers it
        on_rollback(db, lambda: undone.append(name))

    with sessions() as db:
        register(db, "rolled back")
        db.rollback()
        assert undone == ["rolled back"]
        register(db, "committed")
        db.commit()
        db.rollback()
    assert undone == ["rolled back"]
    with sessions() as db:
        register(db, "closed without a commit")
    assert undone == ["rolled back", "closed without a commit"]
