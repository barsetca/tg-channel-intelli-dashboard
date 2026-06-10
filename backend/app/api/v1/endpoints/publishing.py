"""Публикация в Telegram: генерация постов (OpenAI) и отправка (Telethon)."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import TelethonUserSessionServiceDep, get_settings_dep
from app.ai.orchestration.errors import PipelineConfigurationError, PipelineOpenAIError
from app.core.config import Settings
from app.integrations.telethon.exceptions import TelegramTelethonError
from app.publishing.media_payload import decode_media_fields
from app.publishing.service import PublishingService
from app.publishing.style import resolve_style_samples_path
from app.schemas.publishing import (
    AuthorStylePreviewResponse,
    GeneratePostRequest,
    GeneratedPostResponse,
    PublishGeneratedRequest,
    PublishGeneratedResponse,
    PublishManualRequest,
    PublishResultResponse,
    PublishableChannelResponse,
    PublishingImageOptionsResponse,
    SendChatMessageRequest,
)

router = APIRouter()


def get_publishing_service(
    telegram: TelethonUserSessionServiceDep,
    settings: Settings = Depends(get_settings_dep),
) -> PublishingService:
    return PublishingService(telegram=telegram, settings=settings)


def _generate_kwargs(body: GeneratePostRequest) -> dict:
    return {
        "topic": body.topic,
        "target_char_count": body.char_count,
        "extra_info": body.extra_info,
        "output_mode": body.output_mode,
        "use_web_search": body.use_web_search,
        "custom_image_description": body.custom_image_description,
        "image_size": body.image_size,
        "image_quality": body.image_quality,
        "generate_image": body.generate_image,
    }


def _decode_request_media(
    *,
    media_base64: str | None,
    media_filename: str | None,
    image_base64: str | None = None,
):
    try:
        return decode_media_fields(
            media_base64=media_base64,
            media_filename=media_filename,
            image_base64=image_base64,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _to_generated_response(meta, image_bytes: bytes | None, *, generate_image: bool) -> GeneratedPostResponse:
    b64: str | None = None
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("ascii")
    return GeneratedPostResponse(
        topic=meta.topic,
        target_char_count=meta.target_char_count,
        actual_char_count=meta.actual_char_count,
        output_mode=meta.output_mode,
        post_text=meta.post_text,
        image_prompt_used=meta.image_prompt_used,
        image_model=meta.image_model or None,
        image_base64=b64,
        image_generated=generate_image and b64 is not None,
    )


def _to_publish_response(pub) -> PublishResultResponse:
    return PublishResultResponse(
        telegram_message_id=pub.telegram_message_id,
        peer_ref=pub.peer_ref,
        published_at_utc=pub.published_at_utc,
        had_image=pub.had_image,
        had_text=pub.had_text,
        had_media=pub.had_media,
    )


@router.get(
    "/channels",
    response_model=list[PublishableChannelResponse],
    summary="Каналы для публикации",
)
async def list_publishable_channels(
    svc: PublishingService = Depends(get_publishing_service),
) -> list[PublishableChannelResponse]:
    try:
        rows = await svc.list_publishable_channels()
    except TelegramTelethonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return [
        PublishableChannelResponse(
            telegram_channel_id=r.telegram_channel_id,
            username=r.username,
            title=r.title,
        )
        for r in rows
    ]


@router.get(
    "/author-style",
    response_model=AuthorStylePreviewResponse,
    summary="Образец стиля автора",
)
async def author_style_preview(
    svc: PublishingService = Depends(get_publishing_service),
    settings: Settings = Depends(get_settings_dep),
) -> AuthorStylePreviewResponse:
    return AuthorStylePreviewResponse(
        samples=svc.author_style_preview(),
        source_hint=str(resolve_style_samples_path(settings)),
    )


@router.get(
    "/image-options",
    response_model=PublishingImageOptionsResponse,
    summary="Допустимые размер и качество изображения для текущей модели",
)
async def publishing_image_options(
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishingImageOptionsResponse:
    opts = svc.image_options()
    return PublishingImageOptionsResponse(
        model=opts.model,
        family=opts.family,
        sizes=list(opts.sizes),
        qualities=list(opts.qualities),
        default_size=opts.default_size,
        default_quality=opts.default_quality,
    )


@router.post(
    "/generate",
    response_model=GeneratedPostResponse,
    summary="Сгенерировать пост (без публикации)",
)
async def generate_post(
    body: GeneratePostRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> GeneratedPostResponse:
    try:
        meta, image_bytes = await svc.generate_preview(**_generate_kwargs(body))
    except PipelineConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (PipelineOpenAIError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_generated_response(meta, image_bytes, generate_image=body.generate_image)


@router.post(
    "/publish-generated",
    response_model=PublishGeneratedResponse,
    summary="Сгенерировать и опубликовать в канал",
)
async def publish_generated(
    body: PublishGeneratedRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishGeneratedResponse:
    attachment = _decode_request_media(
        media_base64=body.media_base64,
        media_filename=body.media_filename,
    )
    try:
        meta, image_bytes, pub = await svc.generate_and_publish(
            channel_ref=body.channel_ref,
            attachment=attachment,
            **_generate_kwargs(body),
        )
    except PipelineConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (PipelineOpenAIError, ValueError, TelegramTelethonError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return PublishGeneratedResponse(
        generated=_to_generated_response(meta, image_bytes, generate_image=body.generate_image),
        published=_to_publish_response(pub),
    )


@router.post(
    "/publish-manual",
    response_model=PublishResultResponse,
    summary="Опубликовать готовый текст и/или медиа",
)
async def publish_manual(
    body: PublishManualRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishResultResponse:
    media = _decode_request_media(
        media_base64=body.media_base64,
        media_filename=body.media_filename,
        image_base64=body.image_base64,
    )
    try:
        pub = await svc.publish_to_channel(
            channel_ref=body.channel_ref,
            text=body.text,
            media=media,
        )
    except TelegramTelethonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_publish_response(pub)


@router.post(
    "/send-message",
    response_model=PublishResultResponse,
    summary="Написать сообщение в чат от своего имени",
)
async def send_chat_message(
    body: SendChatMessageRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishResultResponse:
    media = _decode_request_media(
        media_base64=body.media_base64,
        media_filename=body.media_filename,
    )
    try:
        pub = await svc.send_chat_message(
            chat_ref=body.chat_ref,
            text=body.text,
            media=media,
        )
    except TelegramTelethonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_publish_response(pub)
