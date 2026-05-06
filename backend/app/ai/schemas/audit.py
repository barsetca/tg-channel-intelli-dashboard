"""Структурированный артефакт аудита канала (стадия Structured JSON)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContentStrategyBlock(BaseModel):
    """Выводы по позиционированию и контент-стратегии канала."""

    goals: str = Field(default="", description="Цели канала")
    main_topics: str = Field(default="", description="Основные темы")
    formats: str = Field(default="", description="Форматы: посты, сторис, видео и т.д.")
    cadence: str = Field(
        default="",
        description="Частота / ритм публикаций (в терминах редакции, не сырые числа)",
    )
    rubricator: str = Field(default="", description="Рубрикатор, серии, постоянные рубрики")
    target_audience: str = Field(default="", description="На какую ЦА ориентирован контент")
    seo_focus: str = Field(
        default="",
        description="SEO: ключевые слова, подача, структура заголовков",
    )
    engagement: str = Field(default="", description="Вовлечённость аудитории, отклик, дискуссия")


class ToneOfVoiceBlock(BaseModel):
    """Тональность и стиль подачи."""

    style: str = Field(
        default="",
        description="Стиль: формальный / дружественный / ироничный и т.д.",
    )
    lexicon: str = Field(default="", description="Лексика, жаргон, уровень сложности")
    emotions: str = Field(default="", description="Эмоциональный фон")
    distance: str = Field(default="", description="Дистанция обращения: ты / вы / нейтрально")
    consistency: str = Field(default="", description="Единообразие подачи между постами")
    vs_positioning: str = Field(
        default="",
        description="Согласованность tone of voice с заявленным позиционированием и ЦА",
    )


class ChannelAuditArtifact(BaseModel):
    """Итоговый JSON для сохранения в `Analysis.result_json` (или вложение внутрь обёртки)."""

    overall_score: float = Field(ge=0.0, le=10.0, description="Обобщённая оценка 0..10")
    strengths: list[str] = Field(
        default_factory=list,
        description="SWOT: сильные стороны самого канала как медиаплощадки (не нишевая экспертиза)",
    )
    risks: list[str] = Field(
        default_factory=list,
        description=(
            "SWOT: риски и уязвимости канала (репутация, право, монетизация, зависимость от TG, качество "
            "модерации и т.п.). НЕ сюда: риски целевой аудитории как группы людей."
        ),
    )
    summary: str = Field(
        default="",
        description="1–2 предложения: краткое резюме аудита (не дублируй развёрнутое содержание постов)",
    )
    content_strategy: ContentStrategyBlock = Field(
        default_factory=ContentStrategyBlock,
        description="Стратегический вывод по позиционированию и подаче тем",
    )
    tone_of_voice: ToneOfVoiceBlock = Field(
        default_factory=ToneOfVoiceBlock,
        description="Стиль коммуникации",
    )
