"""Публикация в Telegram: генерация постов (OpenAI) и отправка (Telethon)."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import TelethonUserSessionServiceDep, get_settings_dep
from app.ai.orchestration.errors import PipelineConfigurationError, PipelineOpenAIError
from app.core.config import Settings
from app.integrations.telethon.exceptions import TelegramTelethonError
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
    SendChatMessageRequest,
)

router = APIRouter()


def get_publishing_service(telegram: TelethonUserSessionServiceDep) -> PublishingService:
    return PublishingService(telegram=telegram)


def _to_generated_response(meta, image_bytes: bytes) -> GeneratedPostResponse:
    return GeneratedPostResponse(
        topic=meta.topic,
        target_char_count=meta.target_char_count,
        actual_char_count=meta.actual_char_count,
        output_mode=meta.output_mode,
        post_text=meta.post_text,
        image_prompt_used=meta.image_prompt_used,
        image_model=meta.image_model,
        image_base64=base64.b64encode(image_bytes).decode("ascii"),
    )


def _to_publish_response(pub) -> PublishResultResponse:
    return PublishResultResponse(
        telegram_message_id=pub.telegram_message_id,
        peer_ref=pub.peer_ref,
        published_at_utc=pub.published_at_utc,
        had_image=pub.had_image,
        had_text=pub.had_text,
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
        meta, image_bytes = await svc.generate_preview(
            topic=body.topic,
            target_char_count=body.char_count,
            extra_info=body.extra_info,
            output_mode=body.output_mode,
        )
    except PipelineConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (PipelineOpenAIError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_generated_response(meta, image_bytes)


@router.post(
    "/publish-generated",
    response_model=PublishGeneratedResponse,
    summary="Сгенерировать и опубликовать в канал",
)
async def publish_generated(
    body: PublishGeneratedRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishGeneratedResponse:
    try:
        meta, image_bytes, pub = await svc.generate_and_publish(
            channel_ref=body.channel_ref,
            topic=body.topic,
            target_char_count=body.char_count,
            extra_info=body.extra_info,
            output_mode=body.output_mode,
        )
    except PipelineConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (PipelineOpenAIError, ValueError, TelegramTelethonError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return PublishGeneratedResponse(
        generated=_to_generated_response(meta, image_bytes),
        published=_to_publish_response(pub),
    )


@router.post(
    "/publish-manual",
    response_model=PublishResultResponse,
    summary="Опубликовать готовый текст и/или картинку",
)
async def publish_manual(
    body: PublishManualRequest,
    svc: PublishingService = Depends(get_publishing_service),
) -> PublishResultResponse:
    image_bytes: bytes | None = None
    if body.image_base64:
        try:
            image_bytes = base64.b64decode(body.image_base64, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Некорректный image_base64",
            ) from exc
    try:
        pub = await svc.publish_to_channel(
            channel_ref=body.channel_ref,
            text=body.text,
            image_bytes=image_bytes,
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
    try:
        pub = await svc.send_chat_message(chat_ref=body.chat_ref, text=body.text)
    except TelegramTelethonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_publish_response(pub)
