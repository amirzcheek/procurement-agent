"""Pydantic-модели, общие для всего пайплайна.

LLM галлюцинируют — любой их вывод обязан пройти через эти модели.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Этап 2: извлечённая позиция КП ───────────────────────────────────────────
class Item(BaseModel):
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    ntin: Optional[str] = None  # NTIN / GTIN / KZTIN, если есть в тексте


# ── Этап 3: нормализация под поиск ───────────────────────────────────────────
class NormalizedQuery(BaseModel):
    """Короткий поисковый запрос + множитель приведения к единице КП.

    pack_multiplier — сколько «штук КП» в одной торговой единице, найденной на рынке.
    Пример: КП в штуках, на рынке продаётся упаковкой по 6 → multiplier=6,
    цену упаковки делим на 6, чтобы сравнивать с ценой за штуку.
    Если масштаб неизвестен — 1.0 (сравниваем как есть).
    """

    query: str
    normalized_unit: Optional[str] = None
    pack_multiplier: float = Field(default=1.0)
    note: Optional[str] = None


# ── Этап 4: результат поиска (ссылки) ─────────────────────────────────────────
class SearchResult(BaseModel):
    title: str
    url: str
    source: str  # домен площадки, напр. "technodom.kz"
    # Некоторые провайдеры (Gemini grounding) отдают цену сразу вместе со ссылкой —
    # тогда crawl4ai не нужен, fetch_price берёт цену прямо отсюда. Обычный веб-поиск
    # (Serper) оставляет эти поля пустыми — цена вытягивается на этапе fetch_price.
    price: Optional[float] = None
    currency: Optional[str] = None
    in_stock: Optional[bool] = None


# ── Этап 5: цена со страницы ─────────────────────────────────────────────────
class PriceHit(BaseModel):
    price: Optional[float] = None
    currency: str = "KZT"
    title: str = ""
    in_stock: Optional[bool] = None
    # служебное (не от LLM):
    url: Optional[str] = None
    source: Optional[str] = None
    available: bool = True  # False, если страницу не удалось загрузить


# ── Этап 6: решение матчинга ─────────────────────────────────────────────────
class MatchDecision(BaseModel):
    is_match: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class ConfirmedPrice(BaseModel):
    """Подтверждённая матчингом рыночная цена, приведённая к единице КП."""

    price_market_unit: float          # цена за торговую единицу (как на сайте)
    price_per_kp_unit: float          # цена, приведённая к единице КП (с учётом множителя)
    currency: str = "KZT"
    title: str
    url: str
    source: str
    confidence: float
    in_stock: Optional[bool] = None


# ── Этап 7: итог по позиции ──────────────────────────────────────────────────
Flag = Literal["green", "yellow", "red", "gray"]


class ItemReport(BaseModel):
    item: Item
    query: Optional[NormalizedQuery] = None
    confirmed_prices: List[ConfirmedPrice] = Field(default_factory=list)

    market_min: Optional[float] = None
    market_median: Optional[float] = None
    market_max: Optional[float] = None
    kp_unit_price: Optional[float] = None     # цена КП за единицу
    delta_pct: Optional[float] = None         # (КП - медиана) / медиана * 100
    avg_confidence: Optional[float] = None

    flag: Flag = "gray"
    flag_reason: str = ""
    estimated_overpay: Optional[float] = None  # переплата по позиции (на весь qty)

    # Лог этапов для отладки на реальных КП.
    stage_log: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class Summary(BaseModel):
    total_items: int = 0
    green: int = 0
    yellow: int = 0
    red: int = 0
    gray: int = 0
    estimated_total_overpay: float = 0.0
    currency: str = "KZT"


class AnalysisReport(BaseModel):
    job_id: str
    filename: str
    items: List[ItemReport] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    disclaimer: str = (
        "Предварительный анализ. Цены найдены автоматически и требуют проверки человеком. "
        "Это подсказка, а не окончательное заключение."
    )
