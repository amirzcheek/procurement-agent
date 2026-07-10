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


# ── OCR сканов (Gemini vision) ───────────────────────────────────────────────
_OCR_PROMPT_TEXT = (
    "Извлеки ВЕСЬ текст с этого изображения документа (коммерческое предложение/договор/"
    "спецификация). Сохрани структуру таблиц: каждая строка позиции — на отдельной строке, "
    "колонки разделяй символом |. Языки: русский, казахский, английский. "
    "Верни только распознанный текст, без комментариев и пояснений."
)
_OCR_PROMPT_JSON = (
    "Распознай таблицу позиций на изображении документа (КП/договор). "
    "Верни ТОЛЬКО JSON-массив объектов, без пояснений: "
    '{"name": str, "model": str|null, "manufacturer": str|null, "category": str|null, '
    '"qty": number|null, "unit": str|null, "unit_price": number|null, "total_price": number|null}. '
    "Числа без пробелов и валютных символов. Языки: русский/казахский/английский. "
    "Чего нет на изображении — null. Строки-итоги и заголовки не включай."
)


def _vision_generate(image_bytes: bytes, prompt: str, mime: str = "image/png") -> str:
    """Один мультимодальный вызов Gemini: изображение + промпт → текст."""
    import base64

    s = get_settings()
    if not is_configured():
        raise RuntimeError("OCR через Gemini недоступен: не задан GEMINI_API_KEY")
    model = s.ocr_model or s.gemini_model
    url = f"{s.gemini_base_url.rstrip('/')}/models/{model}:generateContent"
    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(image_bytes).decode("ascii")}},
    ]
    headers = {"Content-Type": "application/json", "X-goog-api-key": s.gemini_api_key}
    with httpx.Client(timeout=s.llm_timeout) as client:
        r = client.post(url, json={"contents": [{"parts": parts}]}, headers=headers)
        r.raise_for_status()
        data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) or [])


def ocr_page_text(image_bytes: bytes, mime: str = "image/png") -> str:
    """OCR страницы → текст с сохранённой табличной разметкой (режим text)."""
    return _vision_generate(image_bytes, _OCR_PROMPT_TEXT, mime).strip()


def ocr_page_items(image_bytes: bytes, mime: str = "image/png") -> List[dict]:
    """OCR страницы → сразу структурированные позиции (режим structured)."""
    from llm import extract_json

    raw = _vision_generate(image_bytes, _OCR_PROMPT_JSON, mime)
    try:
        data = extract_json(raw)
    except ValueError:
        return []
    if isinstance(data, dict):
        for k in ("items", "positions", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    return [x for x in data if isinstance(x, dict) and (x.get("name") or "").strip()] if isinstance(data, list) else []


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
        f"на казахстанских сайтах и маркетплейсах — в первую очередь {markets}, "
        f"но можно и любые другие казахстанские магазины (цены в тенге). "
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
        chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    except Exception as e:
        log.error("gemini: неожиданный формат ответа: %s", e)
        return []

    items = parse_price_items(text, allowed_sources=s.marketplaces)[: s.max_prices_per_item]
    # Ссылки берём из grounding-метаданных (реальные страницы из выдачи Google),
    # а не из «прямых» URL, которые модель может выдумать. Домен — из title чанка.
    items = _attach_grounding_urls(items, chunks)
    # Один проход: разворачиваем Google-редирект в прямой URL магазина, восстанавливаем
    # домен-источник и отсеиваем реально мёртвые ссылки (404/410).
    items = _resolve_and_filter(items)
    log.info("gemini grounded_search: «%s» → %d цен", query, len(items))
    return items


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def _resolve_and_filter(items: List[dict]) -> List[dict]:
    """Один GET-проход на ссылку: разворачивает Google-редирект в прямой URL магазина,
    восстанавливает домен-источник и отсеивает реально мёртвые ссылки (404/410).
    Сомнительные случаи (таймаут/блок ботов/иные коды) НЕ отбрасываем."""
    if not items:
        return items
    cache: dict = {}  # orig_url -> (alive, final_url, final_domain)
    out: List[dict] = []
    try:
        with httpx.Client(follow_redirects=True, timeout=12, headers=_BROWSER_HEADERS) as client:
            for it in items:
                u = it.get("url") or ""
                if u not in cache:
                    cache[u] = _probe(client, u)
                alive, final, fdom = cache[u]
                if not alive:
                    log.info("gemini: отброшена мёртвая ссылка %s", u[:70])
                    continue
                if final:
                    it["url"] = final
                if fdom and _REDIRECT_HOST not in fdom:
                    it["source"] = fdom
                out.append(it)
    except Exception as e:
        log.warning("проверка ссылок не удалась (%s) — оставляю как есть", e)
        return items
    return out


def _probe(client: httpx.Client, url: str):
    """(жива?, финальный_url, финальный_домен). Тело не скачиваем."""
    if not url:
        return (False, None, None)
    try:
        with client.stream("GET", url) as r:
            final = str(r.url)
            return (r.status_code not in (404, 410), final, _domain(final))
    except Exception:
        return (True, None, None)  # сеть/таймаут — не блокируем и не меняем URL


_REDIRECT_HOST = "vertexaisearch.cloud.google.com"


def _title_domain(title: Optional[str]) -> str:
    t = (title or "").strip().lower()
    return t[4:] if t.startswith("www.") else t


def _grounding_pool(chunks: List[dict]) -> List[dict]:
    """Список реальных источников из grounding: [{url, domain, used}] (без сети).

    URL из groundingChunks — ссылки-редиректы Google на реально процитированные
    страницы; домен магазина берём из title чанка (satu.kz, artvance.kz и т.п.).
    Разворот редиректа и проверка живости — позже, в _resolve_and_filter (один GET).
    """
    pool: List[dict] = []
    for ch in chunks or []:
        web = ch.get("web") or {}
        uri = (web.get("uri") or "").strip()
        if not uri:
            continue
        pool.append({"url": uri, "domain": _title_domain(web.get("title")), "used": False})
    return pool


def _attach_grounding_urls(items: List[dict], chunks: List[dict]) -> List[dict]:
    """Присваивает каждой цене реальную ссылку из grounding (по совпадению домена).

    Если grounding-ссылок нет вовсе — оставляем как есть (лучше, чем ничего). Если
    grounding есть, но конкретной цене реальный источник не нашёлся — эту цену
    отбрасываем, чтобы не показывать недействительную ссылку.
    """
    pool = _grounding_pool(chunks)
    if not pool:
        return items

    def take(match_domain: Optional[str]) -> Optional[dict]:
        for e in pool:
            if e["used"]:
                continue
            if match_domain is None:
                e["used"] = True
                return e
            d = e["domain"] or ""
            if d and (d in match_domain or match_domain in d):
                e["used"] = True
                return e
        return None

    out: List[dict] = []
    for it in items:
        dom = (it.get("source") or _domain(it.get("url") or "")).lower()
        e = take(dom) or take(None)  # сперва по домену, иначе любой оставшийся реальный
        if not e:
            continue  # реального источника не осталось — цену без валидной ссылки не показываем
        it["url"] = e["url"]
        if e["domain"]:
            it["source"] = e["domain"]
        out.append(it)
    return out
