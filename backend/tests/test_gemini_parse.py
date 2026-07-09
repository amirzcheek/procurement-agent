"""Тест разбора ответа Gemini grounding в price-словари — без сети."""
import gemini


def test_parse_fenced_json_array():
    text = """```json
[
  {"title": "Бумага SvetoCopy A4", "price": 2150, "currency": "KZT",
   "url": "https://satu.kz/p106606000-bumaga.html", "source": "satu.kz", "in_stock": true},
  {"title": "SvetoCopy A4", "price": null, "currency": "KZT",
   "url": "https://technodom.kz/p/svetocopy-254452", "source": "technodom.kz"}
]
```"""
    items = gemini.parse_price_items(text, allowed_sources=["satu.kz", "technodom.kz"])
    assert len(items) == 2
    assert items[0]["price"] == 2150.0
    assert items[0]["source"] == "satu.kz"
    assert items[1]["price"] is None  # цена не найдена → null сохраняется


def test_source_recovered_from_url():
    text = '[{"title":"X","price":100,"url":"https://www.kaspi.kz/shop/p/x-1/","source":""}]'
    items = gemini.parse_price_items(text)
    assert items[0]["source"] == "kaspi.kz"  # www. срезан, домен восстановлен


def test_skips_items_without_valid_url():
    text = '[{"title":"нет ссылки","price":100,"url":""},{"title":"ok","price":50,"url":"https://satu.kz/p1"}]'
    items = gemini.parse_price_items(text)
    assert len(items) == 1
    assert items[0]["url"] == "https://satu.kz/p1"


def test_price_string_coerced():
    text = '[{"title":"X","price":"3400","url":"https://satu.kz/p2","source":"satu.kz"}]'
    items = gemini.parse_price_items(text)
    assert items[0]["price"] == 3400.0
