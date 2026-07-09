"""Клиент Google Gemini (AI Studio).

Две роли:
1) grounded_search — поиск цен через Gemini с включённым Google Search grounding.
   Один вызов gemini-3.1-flash-lite отдаёт цену + прямую ссылку по каждому магазину,
   заменяя связку Serper + crawl4ai. Дёшево (сотни токенов на позицию).
2) openai_client — OpenAI-совместимый клиент Gemini для использования как резервной
   LLM, когда локальный OVMS недоступен (см. llm.py).
"""
from __future__ import annotations

from typing import List, Optional

import httpx
from openai import OpenAI

from config import get_settings
from logging_conf import get_logger

log = get_logger("gemini")

_oai: Optional[OpenAI] = None


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key)


def openai_client() -> Optional[OpenAI]:
    """OpenAI-совместимый клиент Gemini (для резервной LLM). None, если ключа нет."""
    global _oai
    if not is_configured():
        return None
    if _oai is None:
        s = get_settings()
        # У Gemini есть OpenAI-совместимый эндпоинт /openai/.
        base = s.gemini_base_url.rstrip("/")
        if not base.endswith("/openai"):
            base = base + "/openai"
        _oai = OpenAI(base_url=base, api_key=s.gemini_api_key, timeout=s.llm_timeout, max_retries=0)
    return _oai


def _domain(url: str) -> str:
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def parse_price_items(raw_text: str, allowed_sources: List[str] | None = None) -> List[dict]:
    """Разбирает JSON-массив цен из текстового ответа Gemini.

    Чистая функция (без сети) — легко тестируется. Возвращает список словарей
    {title, price, currency, url, source, in_stock}; source восстанавливается из url.
    """
    # Локальный импорт, чтобы не тянуть зависимость при простом использовании клиента.
    from llm import extract_json

    data = extract_json(raw_text)
    if isinstance(data, dict):
        for key in ("items", "results", "prices", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []

    out: List[dict] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        url = (it.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        source = (it.get("source") or _domain(url)).strip()
        if allowed_sources and not any(src in source or source in src for src in allowed_sources):
            # источник не из наших площадок — оставляем, но помечаем реальным доменом
            source = _domain(url)
        price = it.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        out.append(
            {
                "title": (it.get("title") or "").strip(),
                "price": price,
                "currency": (it.get("currency") or "KZT").strip() or "KZT",
                "url": url,
                "source": source,
                "in_stock": it.get("in_stock"),
            }
        )
    return out


def grounded_search(query: str) -> List[dict]:
    """Grounded-поиск цен по позиции. Возвращает список price-словарей (см. parse_price_items).

    Не бросает наружу: при любой ошибке возвращает пустой список.
    """
    s = get_settings()
    if not is_configured():
        log.warning("gemini не настроен (нет GEMINI_API_KEY)")
        return []

    markets = ", ".join(s.marketplaces)
    prompt = (
        f"Используя поиск Google, найди актуальные цены на товар: «{query}» "
        f"на казахстанских маркетплейсах ({markets}). "
        f"Верни ТОЛЬКО JSON-массив (максимум {s.max_prices_per_item} объектов), без пояснений и без markdown. "
        'Каждый объект: {"title": str, "price": number|null, "currency": "KZT", '
        '"url": str, "source": str, "in_stock": bool|null}. '
        "price — число в тенге за фасовку из названия товара, без пробелов и символов валюты "
        "(1 250 ₸ → 1250); если цену не нашёл — null. "
        "url — ПРЯМАЯ ссылка на страницу товара в магазине. source — домен магазина. "
        "Бери только реально существующие страницы из результатов поиска."
    )
    url = f"{s.gemini_base_url.rstrip('/')}/models/{s.gemini_model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    headers = {"Content-Type": "application/json", "X-goog-api-key": s.gemini_api_key}
    try:
        with httpx.Client(timeout=s.llm_timeout) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.error("gemini grounded_search ошибка для «%s»: %s", query, e)
        return []

    try:
        cand = (data.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts)
    except Exception as e:
        log.error("gemini: неожиданный формат ответа: %s", e)
        return []

    items = parse_price_items(text, allowed_sources=s.marketplaces)[: s.max_prices_per_item]
    _resolve_redirects(items)
    log.info("gemini grounded_search: «%s» → %d цен", query, len(items))
    return items


_REDIRECT_HOST = "vertexaisearch.cloud.google.com"


def _resolve_redirects(items: List[dict]) -> None:
    """Grounding иногда отдаёт ссылки-редиректы Google. Разворачиваем их в прямой
    URL магазина и восстанавливаем настоящий домен-источник. Побочный бонус —
    проверяем, что страница реально существует. Ошибки игнорируем (оставляем как есть).
    """
    if not any(_REDIRECT_HOST in (it.get("url") or "") for it in items):
        return
    try:
        with httpx.Client(follow_redirects=True, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0"}) as client:
            for it in items:
                url = it.get("url") or ""
                if _REDIRECT_HOST not in url:
                    continue
                try:
                    resp = client.head(url)
                    final = str(resp.url)
                    if _REDIRECT_HOST not in final:
                        it["url"] = final
                        it["source"] = _domain(final)
                except Exception as e:  # один битый редирект не должен ронять остальное
                    log.debug("не развернул редирект %s: %s", url[:60], e)
    except Exception as e:
        log.warning("resolve redirects: %s", e)
