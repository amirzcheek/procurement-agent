"""Тесты исторического ценового анализа и ключа идентичности — без БД."""
from datetime import date

import analysis
import knowledge
import repository
from repository import PriceObservation


def _obs(prices_dates, source="web"):
    return [PriceObservation(unit_price=p, obs_date=d, source=source) for p, d in prices_dates]


# ── canonical_key ────────────────────────────────────────────────────────────
def test_canonical_key_ntin_priority():
    k = repository.canonical_key("Бумага А4", "X", "Y", "KZ123")
    assert k == "ntin:KZ123"


def test_canonical_key_name_normalized():
    k = repository.canonical_key("  Бумага   А4  ", None, None, None)
    assert k == "name:бумага а4"


def test_canonical_key_brand_model():
    k = repository.canonical_key("что-то", "C9115", "Cisco", None)
    assert k == "name:cisco c9115"


# ── analyze: недостаточно данных ─────────────────────────────────────────────
def test_insufficient_data():
    r = analysis.analyze(1000, _obs([(900, date(2026, 1, 1))]), [], "за 6 мес")
    assert r.insufficient is True
    assert r.risk_level == "unknown"


# ── analyze: попадание в диапазон ────────────────────────────────────────────
def test_low_within_range():
    web = _obs([(1000, date(2026, 1, 1)), (1200, date(2026, 2, 1)), (1400, date(2026, 3, 1))])
    r = analysis.analyze(1100, [], web, "за 6 мес")
    assert r.risk_level == "low"
    assert r.combined_min == 1000 and r.combined_max == 1400
    assert r.web.count == 3


def test_medium_upper_part():
    web = _obs([(1000, date(2026, 1, 1)), (1100, date(2026, 2, 1)), (2000, date(2026, 3, 1))])
    # kp=1900 → ratio (1900-1000)/(2000-1000)=0.9 > 0.66 → medium
    r = analysis.analyze(1900, [], web, "за 6 мес")
    assert r.risk_level == "medium"


def test_high_above_max():
    web = _obs([(1000, date(2026, 1, 1)), (1500, date(2026, 2, 1))])
    r = analysis.analyze(2000, [], web, "за 6 мес")
    assert r.risk_level == "high"
    assert "максимума" in r.recommendation


def test_high_suspiciously_low():
    web = _obs([(1000, date(2026, 1, 1)), (1200, date(2026, 2, 1))])
    r = analysis.analyze(500, [], web, "за 6 мес")  # 500 < 1000*0.75
    assert r.risk_level == "high"


def test_two_sources_combined():
    internal = _obs([(900, date(2026, 1, 1)), (950, date(2026, 2, 1))], source="внутренняя")
    web = _obs([(1100, date(2026, 3, 1))])
    r = analysis.analyze(1000, internal, web, "за 6 мес")
    assert r.internal.count == 2 and r.web.count == 1
    assert r.combined_min == 900 and r.combined_max == 1100


# ── тренд ────────────────────────────────────────────────────────────────────
def test_trend_rising():
    web = _obs([(1000, date(2026, 1, 1)), (1100, date(2026, 3, 1)), (1300, date(2026, 6, 1))])
    r = analysis.analyze(1200, [], web, "за 6 мес")
    assert r.web.trend_direction == "rising"
    assert r.web.trend_pct > 0


def test_trend_falling():
    web = _obs([(1500, date(2026, 1, 1)), (1300, date(2026, 3, 1)), (1000, date(2026, 6, 1))])
    r = analysis.analyze(1200, [], web, "за 6 мес")
    assert r.web.trend_direction == "falling"


# ── период ───────────────────────────────────────────────────────────────────
def test_resolve_period_all_time():
    df, dt, label = knowledge.resolve_period(0, None, None)
    assert df is None and dt is None and label == "за всё время"


def test_resolve_period_months():
    df, dt, label = knowledge.resolve_period(6, None, None)
    assert df is not None and dt is None
    assert label == "за 6 мес"
    assert df < date.today()


def test_resolve_period_explicit_range():
    df, dt, label = knowledge.resolve_period(None, "2026-01-01", "2026-06-30")
    assert df == date(2026, 1, 1) and dt == date(2026, 6, 30)
    assert "01.01.2026" in label and "30.06.2026" in label
