"""Подготовка байтов изображения для отправки в Telegram как фото (не как файл)."""

from __future__ import annotations

import io
from typing import BinaryIO


def image_bytes_for_telegram_photo(image_bytes: bytes) -> tuple[BinaryIO, str]:
    """
    Telethon по «голым» bytes часто шлёт документ для скачивания.

    Возвращает file-like с ``.name`` и MIME, чтобы ``send_file(..., force_document=False)``
    отобразил картинку в ленте канала.
    """
    if image_bytes[:3] == b"\xff\xd8\xff":
        ext, mime = "jpg", "image/jpeg"
    elif image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        ext, mime = "png", "image/png"
    elif len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        ext, mime = "webp", "image/webp"
    else:
        ext, mime = "png", "image/png"
    buf = io.BytesIO(image_bytes)
    buf.name = f"post.{ext}"
    return buf, mime
