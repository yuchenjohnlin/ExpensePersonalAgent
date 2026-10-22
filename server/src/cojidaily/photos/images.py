"""Checking a photo and making its preview and thumbnail (moved from api/app/storage.py, itself
backend/'s receipt_storage.py: the same code and Pillow versions, so the same photo gives the same
preview and thumbnail bytes in all three apps; tests/test_photos.py pins their hashes)."""
import hashlib
import uuid
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000

# Originals from an iPhone are HEIC.
register_heif_opener(thumbnails=False)
FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "HEIF": ("image/heic", "heic"),
}
THUMBNAIL_LONG_SIDE = 320


class PhotoRejected(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class PreparedPhoto:
    original_name: str
    original: bytes
    preview: bytes  # 1600 px long side, to read the photo in the browser
    thumbnail: bytes  # 320 px, for lists
    width: int
    height: int
    content_type: str
    extension: str
    storage_key: uuid.UUID
    sha256: str


def prepare_photo(name: str, original: bytes) -> PreparedPhoto:
    """Decode the photo for real (not trusting the browser's type or the file name), then make the
    preview and thumbnail: oriented by EXIF, on white, as JPEG."""
    if len(original) > MAX_FILE_BYTES:
        raise PhotoRejected("每張照片最多 15 MiB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(original)) as image:
                if image.format not in FORMATS:
                    raise PhotoRejected("支援 JPEG、PNG、WebP 和 HEIC／HEIF 靜態照片。")
                if getattr(image, "n_frames", 1) != 1:
                    raise PhotoRejected("請上傳靜態照片；暫不接受動畫或多影格圖片。")
                if image.width * image.height > MAX_PIXELS:
                    raise PhotoRejected("照片最多 4,000 萬像素。")
                content_type, extension = FORMATS[image.format]
                image.load()  # open() is lazy: load() proves the data really decodes
                oriented = ImageOps.exif_transpose(image)
                width, height = oriented.size
                oriented.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                output = BytesIO()
                background.save(output, format="JPEG", quality=88, optimize=True)
                thumbnail = thumbnail_bytes(background)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise PhotoRejected("照片無法讀取，請重新拍照或選擇其他圖片。") from error
    name = "".join(c for c in name if ord(c) >= 32 and ord(c) != 127)[:255] or "photo"
    return PreparedPhoto(name, original, output.getvalue(), thumbnail, width, height, content_type, extension,
                         uuid.uuid4(), hashlib.sha256(original).hexdigest())


def thumbnail_bytes(image) -> bytes:
    small = image.convert("RGB")
    small.thumbnail((THUMBNAIL_LONG_SIDE, THUMBNAIL_LONG_SIDE), Image.Resampling.LANCZOS)
    output = BytesIO()
    small.save(output, format="JPEG", quality=75, optimize=True)
    return output.getvalue()
