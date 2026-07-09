"""Этап 5. Извлечение цены со страницы товара.

- грузим страницу через crawl4ai (рендер JS, выход — markdown);
- если crawl4ai не справился/заблокировано — помечаем источник недоступным, НЕ падаем;
- markdown отдаём LLM → Pydantic-модель PriceHit, retry при невалидном.

В режиме SEARCH_PROVIDER=mock сеть и LLM не трогаем: синтезируем детерминированную
цену, чтобы прогнать весь пайплайн без API и без интернета.
"""
from __future__ import annotations

import asyncio
import hashlib

from config import get_settings
from llm import chat_model
from logging_conf import get_logger
from models import PriceHit, SearchResult

log = get_logger("fetch_price")

SYSTEM = (
    "Найди ЦЕНУ товара на этой странице интернет-магазина. "
    "Верни ТОЛЬКО JSON, без пояснений: "
    '{"price": number|null, "currency": str, "title": str, "in_stock": bool|null}. '
    "price — основная цена товара числом, без пробелов и символов валюты "
    "(1 250 000 ₸ → 1250000). currency обычно \"KZT\". "
    "title — наименование товара со страницы. "
    "in_stock — есть ли в наличии (true/false), если непонятно — null. "
    "Если цены на странице нет — price=null."
)

_MAX_MD_CHARS = 12000  # не перегружаем CPU-LLM огромными страницами


async def _crawl_markdown(url: str) -> str | None:
    """Возвращает markdown страницы или None, если загрузить не удалось."""
    try:
        from crawl4ai import AsyncWebCrawler  # ленивый импорт — тяжёлая зависимость
    except Exception as e:  # pragma: no cover
        log.error("crawl4ai недоступен: %s", e)
        return None
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, page_timeout=45000, word_count_threshold=5)
        if not result or not getattr(result, "success", False):
            log.warning("crawl4ai не загрузил %s", url)
            return None
        md = result.markdown or ""
        if isinstance(md, object) and hasattr(md, "raw_markdown"):
            md = md.raw_markdown  # на новых версиях markdown — объект
        return md or None
    except Exception as e:
        log.warning("crawl4ai ошибка на %s: %s", url, e)
        return None


def _mock_price(sr: SearchResult) -> PriceHit:
    """Детерминированная фиктивная цена для отладки пайплайна."""
    seed = int(hashlib.md5(sr.url.encode("utf-8")).hexdigest(), 16)
    price = 5000 + (seed % 95000)  # 5 000 – 100 000
    return PriceHit(
        price=float(price),
        currency="KZT",
        title=sr.title,
        in_stock=bool(seed % 4),
        url=sr.url,
        source=sr.source,
        available=True,
    )


def fetch_price(sr: SearchResult) -> PriceHit:
    """Синхронно: краулим страницу и извлекаем цену. Не бросает исключений наружу."""
    s = get_settings()

    # Провайдер уже дал цену вместе со ссылкой (Gemini grounding) — crawl4ai не нужен.
    if sr.price is not None:
        return PriceHit(
            price=float(sr.price),
            currency=sr.currency or "KZT",
            title=sr.title,
            in_stock=sr.in_stock,
            url=sr.url,
            source=sr.source,
            available=True,
        )

    if (s.search_provider or "mock").lower() == "mock":
        return _mock_price(sr)

    markdown = asyncio.run(_crawl_markdown(sr.url))
    if not markdown:
        return PriceHit(title=sr.title, url=sr.url, source=sr.source, available=False)

    md = markdown[:_MAX_MD_CHARS]
    user = f"URL: {sr.url}\nИсточник: {sr.source}\n\nMARKDOWN СТРАНИЦЫ:\n{md}"
    try:
        hit = chat_model(SYSTEM, user, PriceHit, retries=2, max_tokens=512)
    except Exception as e:
        log.warning("LLM не извлёк цену с %s: %s", sr.url, e)
        return PriceHit(title=sr.title, url=sr.url, source=sr.source, available=False)

    hit.url = sr.url
    hit.source = sr.source
    hit.available = True
    log.info("fetch_price: %s → %s %s", sr.source, hit.price, hit.currency)
    return hit
