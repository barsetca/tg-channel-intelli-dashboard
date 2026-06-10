"""Декодирование медиа из API-запросов."""

from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedMedia:
    data: bytes
    filename: str


def decode_media_fields(
    *,
    media_base64: str | None,
    media_filename: str | None,
    image_base64: str | None = None,
) -> DecodedMedia | None:
    """Приоритет: media_base64 + filename, иначе legacy image_base64."""
    if media_base64:
        try:
            data = base64.b64decode(media_base64, validate=True)
        except Exception as exc:
            raise ValueError("Некорректный media_base64") from exc
        if not media_filename or not media_filename.strip():
            raise ValueError("Укажите media_filename для медиафайла.")
        return DecodedMedia(data=data, filename=media_filename.strip())
    if image_base64:
        try:
            data = base64.b64decode(image_base64, validate=True)
        except Exception as exc:
            raise ValueError("Некорректный image_base64") from exc
        return DecodedMedia(data=data, filename="post.jpg")
    return None
