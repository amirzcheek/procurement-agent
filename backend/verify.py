"""Обязательная верификация КАЖДОЙ цены-кандидата (ключевой слой точности).

ГЛАВНОЕ ПРАВИЛО: цена без подтверждённой ссылки на карточку товара — ОТБРАСЫВАЕТСЯ.
Для каждого кандидата: грузим страницу (crawl4ai, рендер JS) → извлекаем со страницы
фактическую цену и название → проверяем: страница открылась, это карточка товара
(не категория/каталог/главная), бренд/модель совпадают (LLM), есть цена. Прошёл всё →
принимаем (с ценой и url СО СТРАНИЦЫ). Не прошёл любое → отбрасываем полностью.

Верификация параллельная (asyncio-пул), с общим таймаутом на позицию и ранней остановкой
при достижении PRICES_ENOUGH.
"""
from __future__ import annotations

import asyncio
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlsplit

from config import get_settings
from llm import chat_model
from logging_conf import get_logger
from models import MatchDecision, PageExtract, PriceHit, SearchResult

log = get_logger("verify")

_PAGE_SYSTEM = (
    "Ты проверяешь страницу интернет-магазина. Определи, это ли страница КОНКРЕТНОГО товара "
    "(карточка товара с ценой), а НЕ категория/каталог/список/страница поиска. "
    "Извлеки цену и название. Верни ТОЛЬКО JSON: "
    '{"is_product_page": bool, "price": number|null, "currency": str, "title": str, "in_stock": bool|null}. '
    "is_product_page=true только если на странице ОДИН конкретный товар с ценой. "
    "price — основная цена товара числом без пробелов и символов валюты; если цены нет — null."
)

_MAX_MD_CHARS = 12000


def _is_home_or_listing(url: str) -> bool:
    """Пустой путь / корень / очевидные категории-поиск — не карточка товара."""
    try:
        path = urlsplit(url).path.strip("/")
    except Exception:
        return True
    if path == "":
        return True
    low = path.lower()
    for bad in ("/search", "search?", "/catalog", "/category", "/categories"):
        if bad.strip("/") in low and not any(ch.isdigit() for ch in low):
            return True
    return False


def _domain(url: str) -> str:
    try:
        host = urlsplit(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def evaluate_candidate(page: PageExtract, decision: MatchDecision, final_url: str,
                       candidate_price: Optional[float], min_conf: float,
                       tolerance: float) -> dict:
    """ЧИСТАЯ логика приёмки (тестируется без сети). Возвращает {accepted, reason, price, divergence}."""
    if _is_home_or_listing(final_url):
        return {"accepted": False, "reason": "ссылка ведёт на главную/категорию, не на карточку"}
    if not page.is_product_page:
        return {"accepted": False, "reason": "это не карточка товара"}
    if page.price is None or page.price <= 0:
        return {"accepted": False, "reason": "на странице нет цены"}
    if not decision.is_match or decision.confidence < min_conf:
        return {"accepted": False, "reason": f"бренд/модель не совпадают (conf {decision.confidence:.2f})"}
    # Цена берётся СО СТРАНИЦЫ (достовернее сниппета). Расхождение — только для лога.
    divergence = None
    if candidate_price and candidate_price > 0:
        divergence = abs(page.price - candidate_price) / candidate_price
    return {"accepted": True, "reason": "verified", "price": float(page.price), "divergence": divergence}


async def _crawl(crawler, url: str) -> Tuple[Optional[str], str]:
    """(markdown, финальный_url). Пусто — если страница не открылась."""
    try:
        res = await crawler.arun(url=url, page_timeout=20000, word_count_threshold=5)
    except Exception as e:
        log.debug("crawl упал %s: %s", url[:60], e)
        return None, url
    if not res or not getattr(res, "success", False):
        return None, getattr(res, "url", url) or url
    md = res.markdown
    if hasattr(md, "raw_markdown"):
        md = md.raw_markdown
    return (md or None), (getattr(res, "url", url) or url)


async def _verify_one(crawler, matcher, item, sr: SearchResult, s) -> Optional[Tuple[PriceHit, MatchDecision]]:
    md, final_url = await _crawl(crawler, sr.url)
    if not md:
        return None
    try:
        page = await asyncio.to_thread(
            chat_model, _PAGE_SYSTEM,
            f"URL: {final_url}\nИскомый товар: {item.name}\n\nMARKDOWN СТРАНИЦЫ:\n{md[:_MAX_MD_CHARS]}",
            PageExtract,
        )
    except Exception as e:
        log.debug("extract страницы упал %s: %s", final_url[:60], e)
        return None
    hit_for_match = PriceHit(title=page.title or sr.title, source=_domain(final_url))
    try:
        decision = await asyncio.to_thread(matcher.match, item, hit_for_match)
    except Exception as e:
        decision = MatchDecision(is_match=False, confidence=0.0, reason=str(e))

    verdict = evaluate_candidate(page, decision, final_url, sr.price,
                                 s.match_confidence_min, s.price_match_tolerance)
    if not verdict["accepted"]:
        log.info("verify: отброшен %s — %s", _domain(final_url), verdict["reason"])
        return None
    if verdict.get("divergence") and verdict["divergence"] > s.price_match_tolerance:
        log.info("verify: цена страницы отличается от сниппета на %.0f%% — беру со страницы",
                 verdict["divergence"] * 100)
    hit = PriceHit(price=verdict["price"], currency=page.currency or "KZT", title=page.title or sr.title,
                   in_stock=page.in_stock, url=final_url, source=_domain(final_url), available=True)
    log.info("verify: ПОДТВЕРЖДЕНО %s — %s", _domain(final_url), verdict["price"])
    return hit, decision


async def verify_candidates_async(item, candidates: List[SearchResult],
                                  progress_cb: Optional[Callable[[int, int], None]] = None
                                  ) -> Tuple[List[Tuple[PriceHit, MatchDecision]], dict]:
    s = get_settings()
    cands = candidates[: s.link_verify_max]
    total = len(cands)
    if total == 0:
        return [], {"found": 0, "verified": 0}

    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as e:
        log.error("crawl4ai недоступен — верификация невозможна: %s", e)
        return [], {"found": total, "verified": 0}

    from match import LLMMatcher
    matcher = LLMMatcher()  # реальная LLM-сверка бренда/модели (не mock!)

    verified: List[Tuple[PriceHit, MatchDecision]] = []
    done = 0
    sem = asyncio.Semaphore(max(1, s.verify_concurrency))

    async def guarded(sr):
        async with sem:
            return await _verify_one(crawler, matcher, item, sr, s)

    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            tasks = [asyncio.create_task(guarded(sr)) for sr in cands]
            try:
                for fut in asyncio.as_completed(tasks, timeout=s.link_verify_timeout):
                    try:
                        r = await fut
                    except Exception:
                        r = None
                    done += 1
                    if progress_cb:
                        progress_cb(done, total)
                    if r:
                        verified.append(r)
                        if len(verified) >= s.prices_enough:
                            for t in tasks:
                                t.cancel()
                            break
            except asyncio.TimeoutError:
                log.info("verify: общий таймаут %dс на позицию", s.link_verify_timeout)
                for t in tasks:
                    t.cancel()
    except Exception as e:
        log.warning("verify: краулер упал: %s", e)

    stats = {"found": total, "verified": len(verified)}
    log.info("verify: найдено %d, подтверждено %d", total, len(verified))
    return verified, stats


def verify_candidates(item, candidates, progress_cb=None):
    """Синхронная обёртка (запускается в рабочем потоке пайплайна)."""
    return asyncio.run(verify_candidates_async(item, candidates, progress_cb))
