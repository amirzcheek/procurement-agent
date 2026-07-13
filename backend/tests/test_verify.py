"""Тесты чистой логики приёмки цены-кандидата (без сети/crawl)."""
import verify
from models import MatchDecision, PageExtract

_OK_MATCH = MatchDecision(is_match=True, confidence=0.9, reason="ok")
_BAD_MATCH = MatchDecision(is_match=False, confidence=0.2, reason="другой товар")
_URL = "https://shop.kz/p123-cisco-c9115.html"


def _page(**kw):
    d = dict(is_product_page=True, price=100000.0, currency="KZT", title="Cisco C9115AXI-E")
    d.update(kw)
    return PageExtract(**d)


def test_accepts_valid_card():
    v = verify.evaluate_candidate(_page(), _OK_MATCH, _URL, 98000, 0.6, 0.05)
    assert v["accepted"] is True
    assert v["price"] == 100000.0  # цена берётся СО СТРАНИЦЫ


def test_rejects_non_product_page():
    v = verify.evaluate_candidate(_page(is_product_page=False), _OK_MATCH, _URL, 98000, 0.6, 0.05)
    assert v["accepted"] is False


def test_rejects_home_url():
    v = verify.evaluate_candidate(_page(), _OK_MATCH, "https://shop.kz/", 98000, 0.6, 0.05)
    assert v["accepted"] is False and "главную" in v["reason"]


def test_rejects_listing_url():
    v = verify.evaluate_candidate(_page(), _OK_MATCH, "https://shop.kz/category/laptops", 98000, 0.6, 0.05)
    assert v["accepted"] is False


def test_rejects_no_price():
    v = verify.evaluate_candidate(_page(price=None), _OK_MATCH, _URL, 98000, 0.6, 0.05)
    assert v["accepted"] is False


def test_rejects_brand_mismatch():
    v = verify.evaluate_candidate(_page(), _BAD_MATCH, _URL, 98000, 0.6, 0.05)
    assert v["accepted"] is False


def test_rejects_low_confidence():
    v = verify.evaluate_candidate(_page(), MatchDecision(is_match=True, confidence=0.4, reason="?"),
                                  _URL, 98000, 0.6, 0.05)
    assert v["accepted"] is False


def test_divergence_reported_but_accepted():
    # цена страницы сильно отличается от сниппета → всё равно принимаем цену СО СТРАНИЦЫ
    v = verify.evaluate_candidate(_page(price=150000.0), _OK_MATCH, _URL, 100000, 0.6, 0.05)
    assert v["accepted"] is True
    assert v["price"] == 150000.0
    assert v["divergence"] == 0.5


def test_is_home_or_listing():
    assert verify._is_home_or_listing("https://satu.kz/") is True
    assert verify._is_home_or_listing("https://satu.kz/p106-tovar.html") is False
    assert verify._is_home_or_listing("https://shop.kz/search?q=x") is True
