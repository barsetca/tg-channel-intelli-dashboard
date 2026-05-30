"""Режим saved_catalog «Показать все» (count=null) не должен обрезать выдачу до 20."""

from __future__ import annotations

from app.services.intelligence_service import _saved_catalog_page_limits


def test_show_all_has_no_sql_or_response_cap() -> None:
    catalog_limit, page_cap = _saved_catalog_page_limits(None)
    assert catalog_limit is None
    assert page_cap is None


def test_explicit_count_enables_pagination_cap() -> None:
    catalog_limit, page_cap = _saved_catalog_page_limits(30)
    assert catalog_limit == 31
    assert page_cap == 30


def test_explicit_count_minimum_one() -> None:
    catalog_limit, page_cap = _saved_catalog_page_limits(1)
    assert catalog_limit == 2
    assert page_cap == 1
