"""Тест логики флагов и приведения цен к единице КП — без LLM/сети."""
import compare
from models import Item, MatchDecision, NormalizedQuery, PriceHit


def _hits(prices, conf=0.9, multiplier_ok=True):
    out = []
    for i, p in enumerate(prices):
        hit = PriceHit(price=float(p), currency="KZT", title=f"товар {i}",
                       url=f"https://satu.kz/{i}", source="satu.kz", available=True)
        out.append((hit, MatchDecision(is_match=True, confidence=conf, reason="ok")))
    return out


def _q(mult=1.0):
    return NormalizedQuery(query="q", pack_multiplier=mult)


def test_green():
    item = Item(name="X", qty=2, unit_price=1000)
    r = compare.build_item_report(item, _q(), _hits([1000, 1000, 1000]))
    assert r.flag == "green"
    assert r.market_median == 1000
    assert r.estimated_overpay in (None, 0)


def test_yellow():
    item = Item(name="X", qty=1, unit_price=1200)
    r = compare.build_item_report(item, _q(), _hits([1000, 1000, 1000]))
    assert r.flag == "yellow"


def test_red_and_overpay():
    item = Item(name="X", qty=10, unit_price=1500)
    r = compare.build_item_report(item, _q(), _hits([1000, 1000, 1000]))
    assert r.flag == "red"
    # переплата = (1500 - 1000) * 10
    assert r.estimated_overpay == 5000


def test_gray_no_matches():
    item = Item(name="X", qty=1, unit_price=1000)
    # все хиты — не совпадение
    hits = [(PriceHit(price=999, source="satu.kz", available=True),
             MatchDecision(is_match=False, confidence=0.1, reason="другой товар"))]
    r = compare.build_item_report(item, _q(), hits)
    assert r.flag == "gray"
    assert r.confirmed_prices == []


def test_pack_multiplier_applied():
    # Цена упаковки 6000 за упаковку из 6 шт → 1000 за шт; КП за шт = 1000 → green.
    item = Item(name="X", qty=1, unit="шт", unit_price=1000)
    r = compare.build_item_report(item, _q(mult=6.0), _hits([6000, 6000, 6000]))
    assert r.market_median == 1000
    assert r.flag == "green"


def test_low_confidence_is_gray():
    item = Item(name="X", qty=1, unit_price=1000)
    r = compare.build_item_report(item, _q(), _hits([1000, 1000], conf=0.4))
    # conf 0.4 < порог 0.6 → хиты отсеяны, нет подтверждённых → gray
    assert r.flag == "gray"


def test_summary_counts():
    reports = [
        compare.build_item_report(Item(name="a", qty=1, unit_price=1000), _q(), _hits([1000, 1000, 1000])),
        compare.build_item_report(Item(name="b", qty=1, unit_price=1500), _q(), _hits([1000, 1000, 1000])),
    ]
    s = compare.build_summary(reports)
    assert s.total_items == 2
    assert s.green == 1 and s.red == 1
