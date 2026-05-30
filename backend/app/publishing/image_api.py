"""Параметры OpenAI Images API с учётом семейства модели (DALL·E vs gpt-image)."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings

_GPT_IMAGE_SIZES = frozenset({"1024x1024", "1536x1024", "1024x1536", "auto"})
_DALLE3_SIZES = frozenset({"1024x1024", "1792x1024", "1024x1792"})
_DALLE2_SIZES = frozenset({"256x256", "512x512", "1024x1024"})

_SIZE_TO_GPT = {
    "1024x1024": "1024x1024",
    "1792x1024": "1536x1024",
    "1024x1792": "1024x1536",
    "1536x1024": "1536x1024",
    "1024x1536": "1024x1536",
}


def _is_gpt_image_model(model: str) -> bool:
    m = model.strip().lower()
    return m.startswith("gpt-image") or m.startswith("chatgpt-image")


def _is_dalle3(model: str) -> bool:
    return "dall-e-3" in model.lower() or "dalle-3" in model.lower()


def resolve_openai_image_generate_kwargs(settings: Settings) -> dict[str, Any]:
    """
    Собирает kwargs для ``images.generate``.

    * **gpt-image-*** — quality: low | medium | high | auto; size: 1024², 1536×1024, 1024×1536
    * **dall-e-3** — quality: standard | hd; size: 1024², 1792×1024, 1024×1792
    * **dall-e-2** — без quality; size: до 1024²
    """
    model = settings.openai_image_model.strip()
    raw_size = (settings.openai_image_size or "1024x1024").strip()
    raw_quality = (settings.openai_image_quality or "standard").strip().lower()

    if _is_gpt_image_model(model):
        size = _SIZE_TO_GPT.get(raw_size, raw_size)
        if size not in _GPT_IMAGE_SIZES:
            size = "1024x1024"
        dalle_to_gpt = {"standard": "medium", "hd": "high", "low": "low", "high": "high"}
        if raw_quality in dalle_to_gpt:
            quality = dalle_to_gpt[raw_quality]
        elif raw_quality in ("low", "medium", "high", "auto"):
            quality = raw_quality
        else:
            quality = "auto"
        return {"model": model, "size": size, "quality": quality}

    if _is_dalle3(model):
        size = raw_size if raw_size in _DALLE3_SIZES else "1024x1024"
        gpt_to_dalle = {"low": "standard", "medium": "standard", "high": "hd", "auto": "standard"}
        if raw_quality in gpt_to_dalle:
            quality = gpt_to_dalle[raw_quality]
        elif raw_quality in ("standard", "hd"):
            quality = raw_quality
        else:
            quality = "standard"
        return {"model": model, "size": size, "quality": quality}

    # dall-e-2 и прочие
    size = raw_size if raw_size in _DALLE2_SIZES else "1024x1024"
    return {"model": model, "size": size}
