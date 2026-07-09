"""Этап 4. Поиск цен через обычный веб-поиск google.kz (НЕ Google Shopping).

Абстрактный интерфейс PriceSearchProvider + реализации:
- MockProvider     — фиктивные результаты без расхода API (отладка пайплайна);
- SerperProvider   — google.serper.dev/search, фильтр по площадкам через site:;
- DataForSEOProvider — заглушка с TODO (главное — единый интерфейс).
"""
from __future__ import annotations

import abc
import hashlib
from typing import List
from urllib.parse import quote_plus

import httpx

from config import Settings, get_settings
from logging_conf import get_logger
from models import SearchResult

log = get_logger("search")


def _site_filter(marketplaces: List[str]) -> str:
    """'(site:satu.kz OR site:technodom.kz OR ...)'"""
    if not marketplaces:
        return ""
    return "(" + " OR ".join(f"site:{m}" for m in marketplaces) + ")"


def _domain(url: str) -> str:
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


class PriceSearchProvider(abc.ABC):
    """Единый интерфейс поиска. search(query) -> list[SearchResult]."""

    def __init__(self, settings: Settings):
        self.s = settings

    @abc.abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        ...


class MockProvider(PriceSearchProvider):
    """Детерминированные фиктивные результаты — для прогона пайплайна без API."""

    def search(self, query: str) -> List[SearchResult]:
        markets = self.s.marketplaces or ["satu.kz", "technodom.kz", "sulpak.kz"]
        n = min(self.s.max_prices_per_item, len(markets))
        seed = int(hashlib.md5(query.encode("utf-8")).hexdigest(), 16)
        results: List[SearchResult] = []
        for i in range(n):
            src = markets[i % len(markets)]
            slug = quote_plus(query.lower())[:60]
            results.append(
                SearchResult(
                    title=f"{query} — купить в Казахстане | {src}",
                    url=f"https://{src}/p/{slug}-{(seed + i) % 100000}",
                    source=src,
                )
            )
        log.info("MockProvider: «%s» → %d результатов", query, len(results))
        return results


class SerperProvider(PriceSearchProvider):
    """google.serper.dev — обычная органика google.kz, ru."""

    ENDPOINT = "https://google.serper.dev/search"

    def search(self, query: str) -> List[SearchResult]:
        if not self.s.serper_api_key:
            raise RuntimeError("SERPER_API_KEY не задан, но SEARCH_PROVIDER=serper")
        q = f"{query} {_site_filter(self.s.marketplaces)}".strip()
        payload = {"q": q, "gl": self.s.search_gl, "hl": self.s.search_hl}
        headers = {"X-API-KEY": self.s.serper_api_key, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(self.ENDPOINT, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            log.error("Serper ошибка для «%s»: %s", query, e)
            return []

        organic = data.get("organic", []) or []
        results: List[SearchResult] = []
        for item in organic[: self.s.max_prices_per_item]:
            url = item.get("link", "")
            if not url:
                continue
            results.append(
                SearchResult(
                    title=item.get("title", "") or query,
                    url=url,
                    source=_domain(url),
                )
            )
        log.info("SerperProvider: «%s» → %d результатов", query, len(results))
        return results


class GeminiGroundedProvider(PriceSearchProvider):
    """Gemini (3.1-flash-lite) с Google Search grounding.

    Один вызов сразу отдаёт цену + прямую ссылку по каждому магазину — заменяет
    Serper И crawl4ai. Цена кладётся прямо в SearchResult, поэтому fetch_price
    не гоняет браузер (см. fetch_price.py).
    """

    def search(self, query: str) -> List[SearchResult]:
        import gemini

        if not gemini.is_configured():
            log.error("SEARCH_PROVIDER=gemini, но GEMINI_API_KEY не задан")
            return []
        items = gemini.grounded_search(query)
        results: List[SearchResult] = []
        for it in items:
            results.append(
                SearchResult(
                    title=it.get("title") or query,
                    url=it["url"],
                    source=it.get("source") or _domain(it["url"]),
                    price=it.get("price"),
                    currency=it.get("currency") or "KZT",
                    in_stock=it.get("in_stock"),
                )
            )
        log.info("GeminiGroundedProvider: «%s» → %d результатов", query, len(results))
        return results


class DataForSEOProvider(PriceSearchProvider):
    """ЗАГЛУШКА. Google Organic Live, locale KZ/ru.

    TODO (Фаза 2): POST на
      https://api.dataforseo.com/v3/serp/google/organic/live/advanced
    с Basic-auth (DATAFORSEO_LOGIN/PASSWORD), тело:
      [{"keyword": q, "location_code": <KZ>, "language_code": "ru"}]
    Разобрать tasks[].result[].items[type=organic] → SearchResult.
    Главное сейчас — соблюсти интерфейс, чтобы провайдер подключался без правок пайплайна.
    """

    def search(self, query: str) -> List[SearchResult]:
        log.warning("DataForSEOProvider — заглушка (Фаза 2). Возвращаю пустой список.")
        return []


_PROVIDERS = {
    "mock": MockProvider,
    "serper": SerperProvider,
    "gemini": GeminiGroundedProvider,
    "dataforseo": DataForSEOProvider,
}


def get_provider(settings: Settings | None = None) -> PriceSearchProvider:
    s = settings or get_settings()
    key = (s.search_provider or "mock").lower()
    cls = _PROVIDERS.get(key)
    if cls is None:
        log.warning("Неизвестный SEARCH_PROVIDER=%s, использую mock", key)
        cls = MockProvider
    return cls(s)
