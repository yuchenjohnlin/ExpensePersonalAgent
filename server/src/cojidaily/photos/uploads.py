"""Receiving a multipart photo upload with its limits checked while it arrives (moved from api/app/uploads.py).

In order: the media type and Content-Length (50 MiB of photos plus 1 MiB of form), then as each
part arrives: only the `photos` field carries files, at most `max_files` of them, 15 MiB each and
50 MiB in all; at most 1000 form fields in 64 KiB. A refusal reads the rest of the body first, so
the connection stays usable for the answer.
"""
import html
from dataclasses import dataclass, field

from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header

from ..platform.errors import ApiError
from .images import MAX_FILE_BYTES

MIB = 1024 * 1024
MAX_TOTAL_BYTES = 50 * MIB
MAX_FIELDS, MAX_FIELD_BYTES = 1000, 64 * 1024
GENERIC = "上傳格式無效或照片數量超過限制。"


class _Refused(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


class _Malformed(Exception):
    pass


@dataclass
class Upload:
    fields: dict[str, list[str]] = field(default_factory=dict)
    files: list[tuple[str, bytes]] = field(default_factory=list)  # (file name, content), in the order sent


def sanitize_file_name(name: str) -> str | None:
    name = html.unescape(name).rsplit("/")[-1].rsplit("\\")[-1]
    name = "".join(character for character in name if character.isprintable())
    return None if name in {"", ".", ".."} else name


class _Receiver:
    def __init__(self, max_files):
        self.max_files = max_files
        self.upload = Upload()
        self.headers, self.header_field, self.header_value = {}, b"", b""
        self.kind = self.name = self.file_name = None
        self.data = bytearray()
        self.files = self.field_count = self.field_bytes = self.total = 0

    def on_part_begin(self):
        self.headers, self.data, self.kind = {}, bytearray(), None

    def on_header_field(self, data, start, end):
        self.header_field += data[start:end]

    def on_header_value(self, data, start, end):
        self.header_value += data[start:end]

    def on_header_end(self):
        self.headers[self.header_field.decode("latin-1").lower()] = self.header_value
        self.header_field, self.header_value = b"", b""

    def on_headers_finished(self):
        disposition, params = parse_options_header(self.headers.get("content-disposition", b""))
        if disposition != b"form-data" or b"name" not in params:
            self.kind = "skip"
            return
        self.name = params[b"name"].decode("utf-8", "replace")
        if params.get(b"filename"):
            self.kind = "file"
            self.file_name = sanitize_file_name(params[b"filename"].decode("utf-8", "replace")) or "photo"
            self.files += 1
            if self.name != "photos":
                raise _Refused("只接受 photos 照片欄位。")
            if self.files > self.max_files:
                raise _Refused(f"這次上傳最多 {self.max_files} 張照片。")
        else:
            self.kind = "field"
            self.field_count += 1
            if self.field_count > MAX_FIELDS:
                raise _Malformed
            self.field_bytes += len(self.name) + 2

    def on_part_data(self, data, start, end):
        chunk = data[start:end]
        if self.kind == "file":
            self.total += len(chunk)
            if len(self.data) + len(chunk) > MAX_FILE_BYTES:
                raise _Refused("每張照片最多 15 MiB。", 413)
            if self.total > MAX_TOTAL_BYTES:
                raise _Refused("每次上傳的照片合計最多 50 MiB。", 413)
        elif self.kind == "field":
            self.field_bytes += len(chunk)
            if self.field_bytes > MAX_FIELD_BYTES:
                raise _Malformed
        if self.kind != "skip":
            self.data += chunk

    def on_part_end(self):
        if self.kind == "file":
            self.upload.files.append((self.file_name, bytes(self.data)))
        elif self.kind == "field":
            self.upload.fields.setdefault(self.name, []).append(self.data.decode("utf-8", "replace"))


async def receive(request: Request, max_files: int) -> Upload:
    media, params = parse_options_header(request.headers.get("content-type", ""))
    if media.lower() != b"multipart/form-data":
        raise ApiError(400, "請使用 multipart/form-data 上傳照片。")
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise ApiError(400, "無效的上傳長度。") from None
    stream = request.stream()
    if length > MAX_TOTAL_BYTES + MIB:
        async for _ in stream:  # answering mid-upload would break the client's connection
            pass
        raise ApiError(413, "每次上傳的照片合計最多 50 MiB。")
    boundary = params.get(b"boundary")
    receiver = _Receiver(max_files)
    try:
        if not boundary:
            raise _Malformed
        callbacks = ("on_part_begin", "on_header_field", "on_header_value", "on_header_end", "on_headers_finished",
                     "on_part_data", "on_part_end")
        parser = MultipartParser(boundary, {name: getattr(receiver, name) for name in callbacks})
        async for chunk in stream:
            parser.write(chunk)
        parser.finalize()
    except _Refused as refused:
        async for _ in stream:
            pass
        raise ApiError(refused.status, refused.message, {"photos": [refused.message]}) from None
    except Exception:  # _Malformed, or a body python-multipart cannot parse
        async for _ in stream:
            pass
        raise ApiError(400, GENERIC) from None
    return receiver.upload
