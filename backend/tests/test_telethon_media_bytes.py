"""Подготовка изображений для Telethon send_file."""

from __future__ import annotations

from app.integrations.telethon.media_bytes import image_bytes_for_telegram_photo


def test_png_gets_name_and_mime() -> None:
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    bio, mime = image_bytes_for_telegram_photo(png_header)
    assert bio.name == "post.png"
    assert mime == "image/png"


def test_jpeg_gets_name_and_mime() -> None:
    jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    bio, mime = image_bytes_for_telegram_photo(jpeg_header)
    assert bio.name == "post.jpg"
    assert mime == "image/jpeg"
