"""Параметры OpenAI Images API с учётом семейства модели (DALL·E vs gpt-image)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings

_GPT_IMAGE_SIZES = ("1024x1024", "1536x1024", "1024x1536", "auto")
_GPT_IMAGE_SIZES_UI = ("1024x1024", "1536x1024", "1024x1536")
_GPT_IMAGE_QUALITIES = ("low", "medium", "high", "auto")
_DALLE3_SIZES = ("1024x1024", "1792x1024", "1024x1792")
_DALLE3_QUALITIES = ("standard", "hd")
_DALLE2_SIZES = ("256x256", "512x512", "1024x1024")

_SIZE_TO_GPT = {
    "1024x1024": "1024x1024",
    "1792x1024": "1536x1024",
    "1024x1792": "1024x1536",
    "1536x1024": "1536x1024",
    "1024x1536": "1024x1536",
}

ImageModelFamily = Literal["gpt-image", "dall-e-3", "dall-e-2"]


@dataclass(frozen=True)
class PublishingImageOptions:
    model: str
    family: ImageModelFamily
    sizes: tuple[str, ...]
    qualities: tuple[str, ...]
    default_size: str
    default_quality: str


def _is_gpt_image_model(model: str) -> bool:
    m = model.strip().lower()
    return m.startswith("gpt-image") or m.startswith("chatgpt-image")


def _is_dalle3(model: str) -> bool:
    return "dall-e-3" in model.lower() or "dalle-3" in model.lower()


def detect_image_model_family(model: str) -> ImageModelFamily:
    if _is_gpt_image_model(model):
        return "gpt-image"
    if _is_dalle3(model):
        return "dall-e-3"
    return "dall-e-2"


def get_publishing_image_options(settings: Settings) -> PublishingImageOptions:
    """Опции для UI и валидации запроса по текущей OPENAI_IMAGE_MODEL."""
    model = settings.openai_image_model.strip()
    family = detect_image_model_family(model)
    kw = resolve_openai_image_generate_kwargs(settings)
    default_size = str(kw["size"])
    default_quality = str(kw.get("quality", "standard"))

    if family == "gpt-image":
        return PublishingImageOptions(
            model=model,
            family=family,
            sizes=_GPT_IMAGE_SIZES_UI,
            qualities=_GPT_IMAGE_QUALITIES,
            default_size=default_size if default_size in _GPT_IMAGE_SIZES_UI else "1024x1024",
            default_quality=default_quality,
        )
    if family == "dall-e-3":
        return PublishingImageOptions(
            model=model,
            family=family,
            sizes=_DALLE3_SIZES,
            qualities=_DALLE3_QUALITIES,
            default_size=default_size,
            default_quality=default_quality,
        )
    return PublishingImageOptions(
        model=model,
        family=family,
        sizes=_DALLE2_SIZES,
        qualities=(),
        default_size=default_size,
        default_quality="",
    )


def resolve_openai_image_generate_kwargs(
    settings: Settings,
    *,
    size_override: str | None = None,
    quality_override: str | None = None,
) -> dict[str, Any]:
    """
    Собирает kwargs для ``images.generate``.

    * **gpt-image-*** — quality: low | medium | high | auto; size: 1024², 1536×1024, 1024×1536
    * **dall-e-3** — quality: standard | hd; size: 1024², 1792×1024, 1024×1792
    * **dall-e-2** — без quality; size: до 1024²
    """
    model = settings.openai_image_model.strip()
    raw_size = (size_override or settings.openai_image_size or "1024x1024").strip()
    raw_quality = (quality_override or settings.openai_image_quality or "standard").strip().lower()

    if _is_gpt_image_model(model):
        size = _SIZE_TO_GPT.get(raw_size, raw_size)
        if size not in _GPT_IMAGE_SIZES:
            size = "1024x1024"
        dalle_to_gpt = {"standard": "medium", "hd": "high", "low": "low", "high": "high"}
        if raw_quality in dalle_to_gpt:
            quality = dalle_to_gpt[raw_quality]
        elif raw_quality in _GPT_IMAGE_QUALITIES:
            quality = raw_quality
        else:
            quality = "auto"
        return {"model": model, "size": size, "quality": quality}

    if _is_dalle3(model):
        size = raw_size if raw_size in _DALLE3_SIZES else "1024x1024"
        gpt_to_dalle = {"low": "standard", "medium": "standard", "high": "hd", "auto": "standard"}
        if raw_quality in gpt_to_dalle:
            quality = gpt_to_dalle[raw_quality]
        elif raw_quality in _DALLE3_QUALITIES:
            quality = raw_quality
        else:
            quality = "standard"
        return {"model": model, "size": size, "quality": quality}

    size = raw_size if raw_size in _DALLE2_SIZES else "1024x1024"
    return {"model": model, "size": size}
