"""Files by key, on the local disk under Settings.blob_root.

A key is a relative path made by the module that owns the file (photos/<uuid>/original.jpg).
Writes go to a temporary name and are renamed into place, so a reader never sees half a file.
An S3-like store could replace this class without the modules noticing.
"""
import os
import re
import tempfile
from pathlib import Path

KEY = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


class BlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path(self, key: str) -> Path:
        if not KEY.fullmatch(key) or any(part in (".", "..") for part in key.split("/")):
            raise ValueError(f"not a blob key: {key!r}")
        return self.root / key

    def put(self, key: str, content: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(key)
        handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".partial-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        target = self.path(key)
        target.unlink(missing_ok=True)
        # Drop now-empty folders up to the root.
        folder = target.parent
        while folder != self.root and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
