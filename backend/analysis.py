"""Исторический ценовой анализ (Этап 1, ключевой модуль).

Чистая логика (тестируется без БД): по списку наблюдений цены (цена+дата) за ВЫБРАННЫЙ
период считает min/max/диапазон/count и ТРЕНД — отдельно по внутренней истории и по
веб-истории. Средняя НЕ используется. Риск — по попаданию в исторический диапазон за период.

При недостатке данных за период возвращает insufficient=True и не выдаёт ложный вердикт.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import List, Optional

from repository import PriceObservation

# Насколько «существенно ниже минимума» считается подозрительным занижением.
_LOW_FACTOR = 0.75
# Доля диапазона, выше которой цена внутри диапазона считается «в верхней части» → medium.
_UPPER_RATIO = 0.66
# Минимум наблюдений, чтобы вообще считать диапазон.
_MIN_OBS = 2


@dataclass
class TrendPoint:
    date: Optional[str]  # ISO
    price: float


@dataclass
class SourceStats:
    source: str                # 'internal' | 'web'
    count: int = 0
    min: Optional[float] = None
    max: Optional[float] = None
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    trend_direction: Optional[str] = None   # 'rising' | 'falling' | 'flat' | None
    trend_pct: Optional[float] = None       # % изменения от первого к последнему по линии тренда
    points: List[TrendPoint] = field(default_factory=list)


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _trend(points: List[TrendPoint]):
    """Направление и % изменения по методу наименьших квадратов (x — порядковый индекс дат)."""
    dated = [p for p in points if p.date]
    if len(dated) < 2:
        return None, None
    dated.sort(key=lambda p: p.date)
    xs = list(range(len(dated)))
    ys = [p.price for p in dated]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return "flat", 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    start = mean_y - slope * mean_x
    end = slope * (n - 1) + start
    pct = ((end - start) / start * 100.0) if start else 0.0
    eps = 0.5  # % — порог «плоского» тренда
    direction = "rising" if pct > eps else "falling" if pct < -eps else "flat"
    return direction, round(pct, 1)


def _stats(source: str, obs: List[PriceObservation]) -> SourceStats:
    valid = [o for o in obs if o.unit_price and o.unit_price > 0]
    st = SourceStats(source=source, count=len(valid))
    if not valid:
        return st
    prices = [o.unit_price for o in valid]
    st.min = min(prices)
    st.max = max(prices)
    dated = sorted([o for o in valid if o.obs_date], key=lambda o: o.obs_date)
    if dated:
        st.first_date = _iso(dated[0].obs_date)
        st.last_date = _iso(dated[-1].obs_date)
    st.points = [TrendPoint(date=_iso(o.obs_date), price=o.unit_price) for o in valid]
    st.trend_direction, st.trend_pct = _trend(st.points)
    return st


@dataclass
class HistoricalAnalysis:
    period_label: str
    internal: SourceStats
    web: SourceStats
    combined_min: Optional[float] = None
    combined_max: Optional[float] = None
    combined_count: int = 0
    kp_unit_price: Optional[float] = None
    risk_level: str = "unknown"          # low | medium | high | unknown
    recommendation: str = ""
    insufficient: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def analyze(
    kp_unit_price: Optional[float],
    internal_obs: List[PriceObservation],
    web_obs: List[PriceObservation],
    period_label: str,
) -> HistoricalAnalysis:
    internal = _stats("internal", internal_obs)
    web = _stats("web", web_obs)

    res = HistoricalAnalysis(period_label=period_label, internal=internal, web=web,
                             kp_unit_price=kp_unit_price)

    mins = [s.min for s in (internal, web) if s.min is not None]
    maxs = [s.max for s in (internal, web) if s.max is not None]
    res.combined_count = internal.count + web.count
    res.combined_min = min(mins) if mins else None
    res.combined_max = max(maxs) if maxs else None

    # Мало данных за период — честно сообщаем, вердикт не выдаём.
    if res.combined_count < _MIN_OBS or res.combined_min is None:
        res.insufficient = True
        res.risk_level = "unknown"
        res.message = (
            f"За период «{period_label}» найдено наблюдений: {res.combined_count}. "
            "Недостаточно для надёжного вывода — расширьте период сравнения."
        )
        return res

    if kp_unit_price is None or kp_unit_price <= 0:
        res.risk_level = "unknown"
        res.message = "В договоре/КП нет цены за единицу — сравнение невозможно."
        return res

    lo, hi = res.combined_min, res.combined_max
    if kp_unit_price > hi:
        res.risk_level = "high"
        res.recommendation = (
            f"Цена ({kp_unit_price:g}) выше исторического максимума за период ({hi:g}) — "
            "запросить обоснование стоимости."
        )
    elif kp_unit_price < lo * _LOW_FACTOR:
        res.risk_level = "high"
        res.recommendation = (
            f"Цена ({kp_unit_price:g}) существенно ниже исторического минимума за период ({lo:g}) — "
            "проверить корректность позиции/комплектации, запросить обоснование."
        )
    elif kp_unit_price < lo:
        res.risk_level = "medium"
        res.recommendation = "Цена ниже исторического диапазона, но не критично — проверить."
    else:
        ratio = (kp_unit_price - lo) / (hi - lo) if hi > lo else 0.0
        if ratio > _UPPER_RATIO:
            res.risk_level = "medium"
            res.recommendation = "Цена в верхней части исторического диапазона — обратить внимание."
        else:
            res.risk_level = "low"
            res.recommendation = "Цена в пределах исторического диапазона за период."
    return res
