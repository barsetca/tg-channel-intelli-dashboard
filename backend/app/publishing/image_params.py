"""Параметры OpenAI Images API с учётом семейства модели (DALL·E 3 vs gpt-image-1)."""

from __future__ import annotations

from app.core.config import Settings

_DALLE3_SIZES = frozenset({"1024x1024", "1792x1024", "1024x1792"})
_GPT_IMAGE_SIZES = frozenset({"1024x1024", "1536x1024", "1024x1536", "auto"})
_DALLE3_QUALITY = frozenset({"standard", "hd"})
_GPT_IMAGE_QUALITY = frozenset({"low", "medium", "high", "auto"})


def _is_gpt_image_model(model: str) -> bool:
    m = model.lower()
    return m.startswith("gpt-image") or m == "dall-e-2"


def resolve_image_generate_kwargs(settings: Settings) -> dict[str, str]:
    """
    Возвращает ``size`` и ``quality`` в формате, ожидаемом выбранной моделью.

    DALL·E 3: quality standard|hd, size 1024x1024|1792x1024|1024x1792
    gpt-image-1*: quality low|medium|high|auto, size 1024x1024|1536x1024|1024x1536|auto
    """
    model = settings.openai_image_model
    raw_size = (settings.openai_image_size or "1024x1024").strip()
    raw_quality = (settings.openai_image_quality or "standard").strip().lower()

    if _is_gpt_image_model(model):
        size_aliases = {
            "1792x1024": "1536x1024",
            "1024x1792": "1024x1536",
        }
        size = raw_size if raw_size in _GPT_IMAGE_SIZES else size_aliases.get(raw_size, "1024x1536")
        if raw_quality in _GPT_IMAGE_QUALITY:
            quality = raw_quality
        elif raw_quality == "hd":
            quality = "high"
        elif raw_quality == "standard":
            quality = "medium"
        else:
            quality = "medium"
        return {"size": size, "quality": quality}

    size = raw_size if raw_size in _DALLE3_SIZES else "1024x1024"
    if raw_quality in _DALLE3_QUALITY:
        quality = raw_quality
    elif raw_quality in ("low", "medium", "auto"):
        quality = "standard"
    elif raw_quality == "high":
        quality = "hd"
    else:
        quality = "standard"
    return {"size": size, "quality": quality}
