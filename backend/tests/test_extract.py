"""Тест извлечения xlsx: шапка не в первой строке + объединённые ячейки."""
import io

import openpyxl
import pytest

import extract


def _make_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "КП"
    # Строки-мусор сверху (шапка таблицы не в первой строке).
    ws["A1"] = "Коммерческое предложение"
    ws.merge_cells("A1:E1")  # объединённая ячейка-заголовок
    ws["A2"] = "ТОО Поставщик"
    # Шапка таблицы в 4-й строке.
    ws.append([])  # row 3 пустая
    ws.append(["№", "Наименование", "Кол-во", "Ед.", "Цена"])  # row 4
    ws.append([1, "Бумага А4 SvetoCopy 500л", 10, "пачка", 1850])  # row 5
    ws.append([2, "Картридж HP CF259A", 3, "шт", 42000])  # row 6
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_xlsx_finds_rows():
    text = extract.extract("kp.xlsx", _make_xlsx())
    assert "Бумага А4 SvetoCopy 500л" in text
    assert "Картридж HP CF259A" in text
    assert "Коммерческое предложение" in text  # merged-заголовок развёрнут


def test_unsupported_format():
    with pytest.raises(extract.ExtractionError):
        extract.extract("file.docx", b"123")


def test_pdf_without_text_raises_ocr(monkeypatch):
    # Подменяем pdfplumber на «пустой» PDF без текста.
    class FakePage:
        def extract_tables(self):
            return []

        def extract_text(self):
            return ""

    class FakePDF:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import pdfplumber

    monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: FakePDF())
    with pytest.raises(extract.NeedsOCRError):
        extract.extract("scan.pdf", b"%PDF-1.4 fake")
