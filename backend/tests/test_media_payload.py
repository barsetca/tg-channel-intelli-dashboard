"""Декодирование и подготовка медиа для публикации."""

from __future__ import annotations

from app.integrations.telethon.media_bytes import prepare_media_attachment
from app.publishing.media_payload import decode_media_fields
import base64


def test_decode_media_with_filename() -> None:
    raw = b"fake-video"
    b64 = base64.b64encode(raw).decode()
    decoded = decode_media_fields(media_base64=b64, media_filename="clip.mp4")
    assert decoded is not None
    assert decoded.filename == "clip.mp4"
    assert decoded.data == raw


def test_decode_legacy_image_base64() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    b64 = base64.b64encode(png).decode()
    decoded = decode_media_fields(media_base64=None, media_filename=None, image_base64=b64)
    assert decoded is not None
    prepared = prepare_media_attachment(decoded.data, decoded.filename)
    assert prepared.kind == "photo"


def test_prepare_mp3_as_audio() -> None:
    data = b"ID3" + b"\x00" * 20
    prepared = prepare_media_attachment(data, "track.mp3")
    assert prepared.kind == "audio"
    assert prepared.mime == "audio/mpeg"
