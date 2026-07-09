"""Этап 1. Извлечение сырого текста таблицы из файла (xlsx или текстовый PDF).

- xlsx: openpyxl. Разворачиваем объединённые ячейки (значение → во все слитые),
  пропускаем пустые строки, обрабатываем несколько таблиц/листов. Шапка может быть
  не в первой строке — мы не вычисляем структуру здесь, отдаём весь грид как текст,
  структурирование делает LLM на этапе parse_items.
- pdf: pdfplumber, ТОЛЬКО текстовые PDF. Если текста нет — понятная ошибка (нужен OCR).

Выход: сырой текст таблицы (str).
"""
from __future__ import annotations

import io
from typing import List

from logging_conf import get_logger

log = get_logger("extract")


class ExtractionError(Exception):
    """Понятная пользователю ошибка извлечения."""


class NeedsOCRError(ExtractionError):
    """PDF без текстового слоя — нужен OCR, не поддерживается в этой версии."""


def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def extract_xlsx(content: bytes) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=False)
    out: List[str] = []

    for ws in wb.worksheets:
        # Разворачиваем объединённые ячейки: значение из верхне-левой → во все ячейки диапазона.
        merged_ranges = list(ws.merged_cells.ranges)
        fill = {}
        for rng in merged_ranges:
            top_left = ws.cell(row=rng.min_row, column=rng.min_col).value
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    fill[(r, c)] = top_left

        rows_text: List[str] = []
        for row in ws.iter_rows():
            cells = []
            any_value = False
            for cell in row:
                key = (cell.row, cell.column)
                val = fill.get(key, cell.value)
                txt = _cell_text(val)
                if txt:
                    any_value = True
                cells.append(txt)
            if any_value:
                # Убираем висящие пустые хвосты столбцов.
                while cells and cells[-1] == "":
                    cells.pop()
                rows_text.append("\t".join(cells))

        if rows_text:
            out.append(f"### Лист: {ws.title}")
            out.extend(rows_text)
            out.append("")

    text = "\n".join(out).strip()
    if not text:
        raise ExtractionError("В xlsx-файле не найдено непустых ячеек.")
    log.info("xlsx: извлечено %d строк текста", text.count("\n") + 1)
    return text


def extract_pdf(content: bytes) -> str:
    import pdfplumber

    parts: List[str] = []
    has_text = False
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for pi, page in enumerate(pdf.pages, start=1):
            page_chunks: List[str] = []

            # 1) Пытаемся вытащить структурированные таблицы.
            try:
                tables = page.extract_tables() or []
            except Exception as e:  # pragma: no cover - защита от кривых PDF
                log.warning("pdfplumber: ошибка extract_tables на стр.%d: %s", pi, e)
                tables = []
            for table in tables:
                for trow in table:
                    cells = [(_cell_text(c)) for c in trow]
                    if any(cells):
                        page_chunks.append("\t".join(cells))

            # 2) Плюс обычный текст страницы (на случай таблиц без линий).
            txt = page.extract_text() or ""
            if txt.strip():
                page_chunks.append(txt.strip())

            if page_chunks:
                has_text = True
                parts.append(f"### Страница {pi}")
                parts.extend(page_chunks)
                parts.append("")

    if not has_text:
        raise NeedsOCRError(
            "В PDF нет текстового слоя (вероятно, скан/изображение). "
            "Нужен OCR — не поддерживается в этой версии. "
            "Загрузите текстовый PDF или xlsx."
        )

    text = "\n".join(parts).strip()
    log.info("pdf: извлечено %d строк текста", text.count("\n") + 1)
    return text


def extract(filename: str, content: bytes) -> str:
    """Диспетчер по расширению файла. Возвращает сырой текст таблицы."""
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return extract_xlsx(content)
    if name.endswith(".pdf"):
        return extract_pdf(content)
    if name.endswith(".xls"):
        raise ExtractionError("Старый формат .xls не поддерживается. Сохраните как .xlsx.")
    raise ExtractionError(f"Неподдерживаемый формат файла: {filename}. Нужен .xlsx или текстовый .pdf.")
