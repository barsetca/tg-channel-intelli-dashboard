"""Генерация PDF отчёта анализа канала (on-the-fly, без файлового кеша)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from app.schemas.intelligence import ChannelAnalysisReport, ContentStrategyReport, ToneOfVoiceReport

_PAGE_BOTTOM = 282.0
_MARGIN_X = 12.0
_CONTENT_W = 186.0

_VIOLET = (124, 58, 237)
_VIOLET_LIGHT = (245, 243, 255)
_CYAN_LIGHT = (236, 254, 255)
_ZINC_900 = (24, 24, 27)
_ZINC_600 = (82, 82, 91)
_ZINC_500 = (113, 113, 122)
_BORDER = (228, 228, 231)
_WHITE = (255, 255, 255)

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans.ttf",
)

_FONT_NAME = "DejaVu"


def channel_analysis_report_slug(*, channel_display_ref: str | None, channel_id: int, analysis_id: int) -> str:
    """Идентификатор отчёта: `<username>_<номер_отчёта>` для имени файла и шапки PDF."""
    raw = (channel_display_ref or "").strip().lstrip("@")
    if not raw:
        raw = str(channel_id)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)
    safe = re.sub(r"_+", "_", safe).strip("._-") or str(channel_id)
    return f"{safe}_{analysis_id}"


def channel_analysis_pdf_filename(*, channel_display_ref: str | None, channel_id: int, analysis_id: int) -> str:
    return f"{channel_analysis_report_slug(channel_display_ref=channel_display_ref, channel_id=channel_id, analysis_id=analysis_id)}.pdf"


def _resolve_font_path() -> Path:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError("Шрифт DejaVuSans.ttf не найден (нужен для кириллицы в PDF).")


def _safe_text(value: str | None, *, max_len: int = 8000) -> str:
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _paragraph_text(value: str | None, *, max_len: int = 8000) -> str:
    """Как в UI: один абзац без лишних переводов строк между предложениями."""
    text = _safe_text(value, max_len=max_len)
    text = text.replace("\u2028", " ").replace("\u2029", " ")
    return " ".join(text.split())


def _fmt_report_date(iso: datetime | str | None) -> str:
    if iso is None:
        return "—"
    if isinstance(iso, str):
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            return iso
    else:
        dt = iso
    return dt.strftime("%d.%m.%Y %H:%M")


class _AnalysisPdf(FPDF):
    def __init__(self, *, report_slug: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=False)
        self._report_slug = report_slug
        font_path = _resolve_font_path()
        self.add_font(_FONT_NAME, style="", fname=str(font_path))
        self.set_font(_FONT_NAME, size=10)

    def header(self) -> None:
        self.set_fill_color(*_VIOLET)
        self.rect(0, 0, 210, 22, style="F")
        self.set_text_color(*_WHITE)
        self.set_font(_FONT_NAME, style="", size=14)
        self.set_xy(_MARGIN_X, 7)
        self.cell(0, 8, "Отчёт анализа канала")
        self.set_font(_FONT_NAME, size=9)
        self.set_xy(_MARGIN_X, 14)
        sub = self._report_slug
        self.cell(0, 5, _safe_text(sub, max_len=120))
        self.set_text_color(*_ZINC_900)
        self.set_y(28)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(_FONT_NAME, size=8)
        self.set_text_color(*_ZINC_500)
        self.cell(0, 8, f"Стр. {self.page_no()}/{{nb}}", align="C")


def build_channel_analysis_pdf(
    *,
    report: ChannelAnalysisReport,
    channel_label: str,
    channel_id: int,
    analysis_id: int,
    status: str,
    message: str,
) -> bytes:
    _ = status, message
    slug = channel_analysis_report_slug(
        channel_display_ref=channel_label or None,
        channel_id=channel_id,
        analysis_id=analysis_id,
    )
    pdf = _AnalysisPdf(report_slug=slug)
    pdf.alias_nb_pages()
    pdf.add_page()

    _draw_channel_link_row(pdf, channel_label=channel_label, channel_url=report.channel_url)
    _draw_text_card(
        pdf,
        label="Описание канала",
        body=_safe_text(report.channel_description, max_len=4000),
        body_size=9,
        line_h=4.2,
    )
    _draw_metrics_grid(pdf, report)
    _draw_text_card(
        pdf,
        label="Краткое содержание постов",
        body=_safe_text(report.posts_summary, max_len=4000),
        title="Краткое содержание постов",
        title_icon="▣",
    )
    _draw_content_strategy(pdf, report.content_strategy)
    _draw_tone_of_voice(pdf, report.tone_of_voice)
    _draw_swot(pdf, report.strengths, report.risks)
    _draw_recommendations(pdf, report.recommendations)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, bytearray) else raw.encode("latin-1") if isinstance(raw, str) else raw


_PAGE_TOP = 28.0
_MAX_BLOCK_H = _PAGE_BOTTOM - _PAGE_TOP


def _ensure_space(pdf: _AnalysisPdf, needed_mm: float) -> None:
    if pdf.get_y() + needed_mm > _PAGE_BOTTOM:
        pdf.add_page()


def _ensure_block_together(pdf: _AnalysisPdf, block_h: float) -> None:
    """Не разрезать компактный блок посередине: перенос на следующую страницу."""
    if block_h <= 0:
        return
    remaining = _PAGE_BOTTOM - pdf.get_y()
    if block_h <= _MAX_BLOCK_H and block_h > remaining:
        pdf.add_page()


def _split_wrapped_lines(
    pdf: _AnalysisPdf,
    w: float,
    line_h: float,
    text: str,
    *,
    font_size: int,
) -> list[str]:
    pdf.set_font(_FONT_NAME, size=font_size)
    lines = pdf.multi_cell(w, line_h, text, split_only=True)
    return lines if lines else [""]


def _estimate_text_height(
    pdf: _AnalysisPdf,
    w: float,
    line_h: float,
    text: str,
    *,
    font_size: int,
) -> float:
    lines = _split_wrapped_lines(pdf, w, line_h, text, font_size=font_size)
    return max(1, len(lines)) * line_h


def _draw_text_card(
    pdf: _AnalysisPdf,
    *,
    label: str,
    body: str,
    body_size: int = 9,
    line_h: float = 4.2,
    title: str | None = None,
    title_icon: str | None = None,
    fill: tuple[int, int, int] = _WHITE,
    preserve_line_breaks: bool = False,
) -> None:
    inner_w = _CONTENT_W - 6.0
    raw = body.strip() or "—"
    content = raw if preserve_line_breaks else _paragraph_text(raw, max_len=8000)
    title_extra = 10.0 if title else 0.0
    header_h = 7.0 + title_extra
    body_lines = _split_wrapped_lines(pdf, inner_w, line_h, content, font_size=body_size)
    body_h = max(1, len(body_lines)) * line_h
    card_h = header_h + body_h + 6.0

    if card_h <= _MAX_BLOCK_H:
        _ensure_block_together(pdf, card_h + 4)
    else:
        _ensure_space(pdf, header_h + 8)

    x = _MARGIN_X
    y0 = pdf.get_y()
    pdf.set_fill_color(*fill)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(x, y0, _CONTENT_W, card_h if card_h <= _MAX_BLOCK_H else header_h + 6.0, style="DF")

    pdf.set_xy(x + 3, y0 + 3)
    if title:
        pdf.set_font(_FONT_NAME, size=10)
        pdf.set_text_color(*_ZINC_900)
        pdf.cell(inner_w, 5, f"{title_icon or '▣'}  {title}")
        body_y = y0 + 9
    else:
        pdf.set_font(_FONT_NAME, size=7)
        pdf.set_text_color(*_ZINC_500)
        pdf.cell(inner_w, 4, label)
        body_y = y0 + 9

    pdf.set_font(_FONT_NAME, size=body_size)
    pdf.set_text_color(*_ZINC_900)
    pdf.set_xy(x + 3, body_y)

    if card_h <= _MAX_BLOCK_H:
        pdf.multi_cell(inner_w, line_h, content)
        pdf.set_y(y0 + card_h + 5)
        return

    for i, line in enumerate(body_lines):
        if pdf.get_y() + line_h > _PAGE_BOTTOM:
            pdf.add_page()
            y0 = pdf.get_y()
            pdf.set_fill_color(*fill)
            pdf.set_draw_color(*_BORDER)
            pdf.rect(x, y0, _CONTENT_W, min(line_h + 4, _PAGE_BOTTOM - y0), style="DF")
            pdf.set_xy(x + 3, y0 + 2)
        pdf.cell(inner_w, line_h, line)
    pdf.set_y(pdf.get_y() + 5)


def _channel_link_display(channel_label: str, channel_url: str | None) -> tuple[str, str | None]:
    url = (channel_url or "").strip() or None
    label = (channel_label or "").strip()
    if label and not label.startswith("http"):
        display = label if label.startswith("@") else f"@{label.lstrip('@')}"
        return display, url
    if url:
        slug = url.rstrip("/").split("/")[-1]
        return (f"@{slug}" if slug else url), url
    return "—", None


def _draw_channel_link_row(
    pdf: _AnalysisPdf,
    *,
    channel_label: str,
    channel_url: str | None,
) -> None:
    display, url = _channel_link_display(channel_label, channel_url)
    if display == "—" and not url:
        return
    h = 18.0
    _ensure_space(pdf, h + 4)
    x = _MARGIN_X
    y0 = pdf.get_y()
    inner_w = _CONTENT_W - 6.0
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(x, y0, _CONTENT_W, h, style="DF")
    pdf.set_xy(x + 3, y0 + 3)
    pdf.set_font(_FONT_NAME, size=7)
    pdf.set_text_color(*_ZINC_500)
    pdf.cell(inner_w, 4, "Канал")
    pdf.set_xy(x + 3, y0 + 9)
    pdf.set_font(_FONT_NAME, size=11)
    pdf.set_text_color(109, 40, 217)
    text = _safe_text(display, max_len=64)
    if url:
        pdf.cell(inner_w, 6, text, link=url)
    else:
        pdf.set_text_color(*_ZINC_900)
        pdf.cell(inner_w, 6, text)
    pdf.set_y(y0 + h + 5)
    pdf.set_text_color(*_ZINC_900)


def _draw_metrics_grid(pdf: _AnalysisPdf, report: ChannelAnalysisReport) -> None:
    _ensure_space(pdf, 14)
    pdf.set_font(_FONT_NAME, size=11)
    pdf.set_text_color(*_VIOLET)
    pdf.cell(0, 7, "◆  Ключевые показатели")
    pdf.ln(6)

    metrics: list[tuple[str, str]] = [
        ("Тематика", _paragraph_text(report.topic, max_len=300)),
        (
            "Подписчиков",
            f"{report.subscribers_count:,}".replace(",", " ")
            if report.subscribers_count is not None
            else "—",
        ),
        ("Дата отчёта", _fmt_report_date(report.report_created_at)),
        ("Канал создан", _safe_text(report.channel_created_display or "—")),
        ("Возраст канала", _safe_text(report.channel_age_display or "—")),
        (
            "Постов за 30 дней",
            str(report.posts_last_30_days) if report.posts_last_30_days is not None else "—",
        ),
        (
            "Всего постов",
            str(report.total_posts_filtered) if report.total_posts_filtered is not None else "—",
        ),
        ("Частота публикаций", _safe_text(report.publication_frequency)),
        (
            "Средняя длина постов",
            f"{report.avg_post_length} симв." if report.avg_post_length is not None else "—",
        ),
    ]

    col_w = 91.0
    x_left = _MARGIN_X
    x_right = _MARGIN_X + col_w + 4.0
    row_h = 20.0

    for i in range(0, len(metrics), 2):
        left = metrics[i]
        right = metrics[i + 1] if i + 1 < len(metrics) else None
        _ensure_block_together(pdf, row_h + 4)
        y0 = pdf.get_y()
        _metric_card(pdf, x_left, y0, col_w, row_h, left[0], left[1])
        if right is not None:
            _metric_card(pdf, x_right, y0, col_w, row_h, right[0], right[1])
        pdf.set_y(y0 + row_h + 5)


def _metric_card(
    pdf: _AnalysisPdf,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    value: str,
) -> None:
    inner_w = w - 6.0
    value_text = _paragraph_text(value, max_len=200)
    if len(value_text) > 52:
        value_text = value_text[:49] + "…"
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(x, y, w, h, style="DF")
    pdf.set_xy(x + 3, y + 2)
    pdf.set_font(_FONT_NAME, size=7)
    pdf.set_text_color(*_ZINC_500)
    pdf.cell(inner_w, 4, label)
    pdf.set_xy(x + 3, y + 7)
    pdf.set_font(_FONT_NAME, size=9)
    pdf.set_text_color(*_ZINC_900)
    pdf.cell(inner_w, 5, value_text)


def _draw_section_banner(pdf: _AnalysisPdf, title: str, *, fill: tuple[int, int, int], text_color: tuple[int, int, int]) -> None:
    _ensure_space(pdf, 16)
    y0 = pdf.get_y()
    pdf.set_fill_color(*fill)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(_MARGIN_X, y0, _CONTENT_W, 9, style="F")
    pdf.set_xy(_MARGIN_X + 2, y0 + 2)
    pdf.set_font(_FONT_NAME, size=10)
    pdf.set_text_color(*text_color)
    pdf.cell(0, 6, title)
    pdf.set_y(y0 + 12)


def _draw_field_grid(pdf: _AnalysisPdf, fields: list[tuple[str, str]]) -> None:
    for label, value in fields:
        text = _paragraph_text(value, max_len=1500)
        if not text or text == "—":
            continue
        _draw_text_card(pdf, label=label, body=text, body_size=9, line_h=4.0)


def _draw_content_strategy(pdf: _AnalysisPdf, cs: ContentStrategyReport) -> None:
    _ensure_space(pdf, 20)
    _draw_section_banner(
        pdf,
        "◆  Контент-стратегия и позиционирование",
        fill=_VIOLET_LIGHT,
        text_color=(76, 29, 149),
    )
    fields = [
        ("Цели канала", cs.goals),
        ("Основные темы", cs.main_topics),
        ("Форматы", cs.formats),
        ("Частота и ритм", cs.cadence),
        ("Рубрикатор", cs.rubricator),
        ("Целевая аудитория", cs.target_audience),
        ("SEO и ключевые акценты", cs.seo_focus),
        ("Вовлечённость аудитории", cs.engagement),
    ]
    _draw_field_grid(pdf, fields)


def _draw_tone_of_voice(pdf: _AnalysisPdf, tv: ToneOfVoiceReport) -> None:
    _ensure_space(pdf, 20)
    _draw_section_banner(
        pdf,
        "◆  Tone of voice",
        fill=_CYAN_LIGHT,
        text_color=(22, 78, 99),
    )
    fields = [
        ("Стиль", tv.style),
        ("Лексика", tv.lexicon),
        ("Эмоции", tv.emotions),
        ("Обращение", tv.distance),
        ("Единообразие", tv.consistency),
        ("Согласованность с ЦА", tv.vs_positioning),
    ]
    _draw_field_grid(pdf, fields)


def _swot_block_height(pdf: _AnalysisPdf, w: float, items: list[str]) -> float:
    line_h = 4.5
    total = 0.0
    bullets = items if items else ["—"]
    for item in bullets:
        text = f"– {_paragraph_text(item, max_len=500)}"
        n = len(_split_wrapped_lines(pdf, w, line_h, text, font_size=9))
        total += max(1, n) * line_h
    return total


def _draw_swot(pdf: _AnalysisPdf, strengths: list[str], risks: list[str]) -> None:
    col_w = _CONTENT_W
    # Высота блока: заголовок секции + подзаголовок подколонки (см. _swot_column) + текст.
    subsection_header_h = 7.0
    title_h = 10.0
    left_h = subsection_header_h + _swot_block_height(pdf, col_w, strengths)
    right_h = subsection_header_h + _swot_block_height(pdf, col_w, risks)
    spacing_after_title = 2.0
    gap_between = 3.0
    tail_pad = 5.0
    total_swot_h = title_h + spacing_after_title + left_h + gap_between + right_h + tail_pad
    _ensure_block_together(pdf, total_swot_h)
    _ensure_space(pdf, title_h + 4)

    pdf.set_font(_FONT_NAME, size=10)
    pdf.set_text_color(*_ZINC_900)
    # ln=1 — перенос на следующую строку с учётом высоты ячейки (без этого Y почти не сдвигается).
    pdf.cell(0, 8, "◆  SWOT", ln=1)
    pdf.ln(2)

    y_after_left = _swot_column(pdf, _MARGIN_X, col_w, "Сильные стороны", strengths)
    pdf.set_y(y_after_left + 3)
    _ensure_block_together(pdf, subsection_header_h + _swot_block_height(pdf, col_w, risks))
    _swot_column(pdf, _MARGIN_X, col_w, "Риски", risks)
    pdf.ln(5)


def _swot_column(
    pdf: _AnalysisPdf,
    x: float,
    w: float,
    title: str,
    items: list[str],
) -> float:
    pdf.set_x(x)
    pdf.set_font(_FONT_NAME, size=9)
    pdf.set_text_color(*_ZINC_600)
    pdf.cell(w, 6, title, ln=1)
    pdf.set_font(_FONT_NAME, size=9)
    pdf.set_text_color(*_ZINC_900)
    bullets = items if items else ["—"]
    for item in bullets:
        text = f"– {_paragraph_text(item, max_len=500)}"
        lines = _split_wrapped_lines(pdf, w, 4.5, text, font_size=9)
        block_h = max(1, len(lines)) * 4.5
        _ensure_block_together(pdf, block_h)
        pdf.set_x(x)
        pdf.multi_cell(w, 4.5, text)
    return pdf.get_y()


def _draw_recommendations(pdf: _AnalysisPdf, items: list[str]) -> None:
    body = (
        "\n".join(f"– {_paragraph_text(x, max_len=500)}" for x in items)
        if items
        else "—"
    )
    _draw_text_card(
        pdf,
        label="Рекомендации",
        body=body,
        title="Рекомендации",
        title_icon="◆",
        preserve_line_breaks=True,
    )
