"""Тесты каскада извлечения с OCR-веткой (Gemini замокан, без сети)."""
import config
import extract
import gemini
import pytest


def _cfg(monkeypatch, **kw):
    s = config.get_settings()
    for k, v in kw.items():
        monkeypatch.setattr(s, k, v)
    return s


def test_image_goes_ocr(monkeypatch):
    _cfg(monkeypatch, ocr_enabled=True, ocr_mode="text", ocr_provider="gemini")
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "ocr_page_text", lambda img, mime="image/png": "Бумага А4 | 10 | 1850")
    res = extract.extract("scan.png", b"\x89PNG-fake")
    assert res.source_type == "ocr"
    assert "Бумага А4" in res.text


def test_pdf_with_text_no_ocr(monkeypatch):
    _cfg(monkeypatch, ocr_min_chars_per_page=100)
    monkeypatch.setattr(extract, "_pdf_text", lambda content: ("x" * 500, 1))

    def _boom(*a, **k):
        raise AssertionError("OCR не должен вызываться для текстового PDF")

    monkeypatch.setattr(extract, "_render_pdf_pages", _boom)
    res = extract.extract("doc.pdf", b"%PDF")
    assert res.source_type == "pdf_text"
    assert len(res.text) == 500


def test_pdf_scan_goes_ocr(monkeypatch):
    _cfg(monkeypatch, ocr_enabled=True, ocr_min_chars_per_page=100, ocr_mode="text", ocr_provider="gemini")
    monkeypatch.setattr(extract, "_pdf_text", lambda content: ("", 2))  # пустой текст → скан
    monkeypatch.setattr(extract, "_render_pdf_pages", lambda c, dpi: [b"img1", b"img2"])
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "ocr_page_text", lambda img, mime="image/png": "текст страницы")
    res = extract.extract("scan.pdf", b"%PDF")
    assert res.source_type == "ocr"
    assert "Страница 1" in res.text and "Страница 2" in res.text


def test_short_text_pdf_treated_as_scan(monkeypatch):
    # текст есть, но куцый (< порога) → считаем сканом
    _cfg(monkeypatch, ocr_enabled=True, ocr_min_chars_per_page=100, ocr_mode="text", ocr_provider="gemini")
    monkeypatch.setattr(extract, "_pdf_text", lambda content: ("абв", 1))  # 3 символа < 100
    monkeypatch.setattr(extract, "_render_pdf_pages", lambda c, dpi: [b"img"])
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "ocr_page_text", lambda img, mime="image/png": "распознано")
    res = extract.extract("scan.pdf", b"%PDF")
    assert res.source_type == "ocr"


def test_ocr_disabled_raises(monkeypatch):
    _cfg(monkeypatch, ocr_enabled=False)
    with pytest.raises(extract.NeedsOCRError):
        extract.extract("scan.png", b"img")


def test_structured_mode_returns_items(monkeypatch):
    _cfg(monkeypatch, ocr_enabled=True, ocr_mode="structured", ocr_provider="gemini")
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "ocr_page_items",
                        lambda img, mime="image/png": [{"name": "Картридж", "unit_price": 42000}])
    res = extract.extract("scan.png", b"img")
    assert res.source_type == "ocr"
    assert res.items and res.items[0]["name"] == "Картридж"


def test_empty_ocr_raises(monkeypatch):
    _cfg(monkeypatch, ocr_enabled=True, ocr_mode="text", ocr_provider="gemini")
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "ocr_page_text", lambda img, mime="image/png": "")
    with pytest.raises(extract.ExtractionError):
        extract.extract("scan.png", b"img")
