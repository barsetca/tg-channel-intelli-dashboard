"""Подготовка медиафайлов для отправки через Telethon send_file."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

MediaKind = Literal["photo", "video", "audio", "document"]

_EXT_TO_KIND: dict[str, MediaKind] = {
    ".jpg": "photo",
    ".jpeg": "photo",
    ".png": "photo",
    ".webp": "photo",
    ".gif": "photo",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".mkv": "video",
    ".m4v": "video",
    ".mp3": "audio",
    ".ogg": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".opus": "audio",
    ".flac": "audio",
}

_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4v": "video/x-m4v",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
}


@dataclass(frozen=True)
class PreparedMedia:
    file: BinaryIO
    mime: str
    kind: MediaKind
    filename: str


def _sniff_image_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def _sniff_video_ext(data: bytes) -> str | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    return None


def _sniff_audio_ext(data: bytes) -> str | None:
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return ".mp3"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WAVE":
        return ".wav"
    return None


def _guess_ext(data: bytes, filename: str | None) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext:
            return ext
    for sniff in (_sniff_image_ext, _sniff_video_ext, _sniff_audio_ext):
        found = sniff(data)
        if found:
            return found
    return ".bin"


def prepare_media_attachment(data: bytes, filename: str | None = None) -> PreparedMedia:
    """Готовит file-like для send_file: фото в ленте, видео/аудио как медиа."""
    ext = _guess_ext(data, filename)
    kind = _EXT_TO_KIND.get(ext, "document")
    mime = _EXT_TO_MIME.get(ext, "application/octet-stream")
    name = Path(filename).name if filename else f"attachment{ext}"
    buf = io.BytesIO(data)
    buf.name = name
    return PreparedMedia(file=buf, mime=mime, kind=kind, filename=name)


def image_bytes_for_telegram_photo(image_bytes: bytes) -> tuple[BinaryIO, str]:
    """Совместимость: только изображение как фото в ленте."""
    prepared = prepare_media_attachment(image_bytes, None)
    ext = Path(prepared.filename).suffix or ".png"
    prepared.file.name = f"post{ext}"
    return prepared.file, prepared.mime
