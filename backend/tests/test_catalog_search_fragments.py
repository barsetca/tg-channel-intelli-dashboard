"""Юнит-тесты нормализации темы и фрагментов ILIKE для поиска по сохранённому каталогу."""

from __future__ import annotations

from app.repositories.channel_repository import (
    catalog_search_like_fragments,
    normalize_catalog_topic_phrase,
)


def test_normalize_splits_ampersand_and_case() -> None:
    assert normalize_catalog_topic_phrase("Investing & Personal Finance") == "investing personal finance"


def test_fragments_include_norm_and_long_tokens() -> None:
    frags = catalog_search_like_fragments("investing & personal finance")
    assert "investing & personal finance" in frags
    assert "investing personal finance" in frags
    assert "investing" in frags
    assert "personal" in frags
    assert "finance" in frags


def test_fragments_cyrillic_topic() -> None:
    frags = catalog_search_like_fragments("Финансы")
    assert any("финансы" in f.lower() for f in frags)
