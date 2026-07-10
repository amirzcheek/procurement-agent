"""Оркестрация пайплайна. Позиции обрабатываются ПОСЛЕДОВАТЕЛЬНО (LLM на CPU медленный).

Изоляция ошибок: сбой на одной позиции или одном источнике не роняет весь анализ.
Каждый этап логируется (извлечено / запрос / найдено / решение матчинга).

analyze() — генератор событий прогресса для SSE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterator, List, Optional, Tuple

import compare
import db
import embeddings
import extract as extract_mod
import repository
from config import get_settings
from logging_conf import get_logger
from match import get_matcher
from models import AnalysisReport, Item, ItemReport, MatchDecision, PriceHit
from normalize import normalize_item
from parse_items import parse_items
from search import get_provider

log = get_logger("pipeline")


@dataclass
class ItemContext:
    """Серверный контекст позиции для повторного исторического анализа по периоду.
    Эмбеддинг тяжёлый — держим на сервере, клиенту не отдаём."""

    name: str
    canonical_key: str
    canonical_name: str
    ntin: Optional[str]
    kp_unit_price: Optional[float]
    embedding: Optional[List[float]] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None


# Контексты позиций по job_id — для эндпоинта исторического анализа (пересчёт по периоду).
JOB_CONTEXTS: Dict[str, List[ItemContext]] = {}


def _persist_search_history(item: Item, query, report: ItemReport,
                            embedding: Optional[List[float]], canonical: str) -> None:
    """Сохраняет подтверждённые (matched) рыночные цены в price_search_history."""
    s = get_settings()
    if not db.is_enabled() or (s.search_provider or "mock").lower() == "mock":
        return
    if not report.confirmed_prices:
        return
    try:
        with db.session_scope() as sess:
            for cp in report.confirmed_prices:
                repository.record_search_result(
                    sess,
                    query=query.query if query else item.name,
                    item_name=item.name,
                    canonical=canonical,
                    model=None,
                    unit_price=cp.price_per_kp_unit,   # нормализовано к единице КП
                    currency=cp.currency,
                    source_url=cp.url,
                    source_site=cp.source,
                    found_at=date.today(),
                    embedding=embedding,
                )
    except Exception as e:  # БД не должна ронять анализ
        log.warning("не сохранил историю поиска: %s", e)


def _process_item(item: Item) -> Tuple[ItemReport, ItemContext]:
    """Полный цикл по одной позиции. Не бросает исключений наружу.
    Возвращает отчёт + серверный контекст для исторического анализа."""
    stage_log: List[str] = []
    canonical = repository.canonical_key(item.name, item.model, item.manufacturer, item.ntin)
    ctx = ItemContext(name=item.name, canonical_key=canonical, canonical_name=item.name,
                      ntin=item.ntin, kp_unit_price=compare._kp_unit_price(item),
                      model=item.model, manufacturer=item.manufacturer)
    try:
        # 3) нормализация
        query = normalize_item(item)
        ctx.canonical_name = query.query
        # canonical_key приоритетно по manufacturer+model (если LLM их выделил),
        # иначе по нормализованному запросу.
        ctx.canonical_key = canonical = repository.canonical_key(
            query.query, item.model, item.manufacturer, item.ntin)
        stage_log.append(f"запрос: «{query.query}» (множитель x{query.pack_multiplier:g})")

        # эмбеддинг канонического имени (для семантического поиска аналогов)
        ctx.embedding = embeddings.embed(query.query) if (db.is_enabled() or embeddings.is_enabled()) else None

        # 4) поиск ссылок
        provider = get_provider()
        results = provider.search(query.query)
        stage_log.append(f"найдено ссылок: {len(results)} [{provider.__class__.__name__}]")

        # 5) + 6) цена и матчинг по каждому результату
        matcher = get_matcher()
        hits_with_decisions: List[Tuple[PriceHit, MatchDecision]] = []
        from fetch_price import fetch_price

        for sr in results:
            try:
                hit = fetch_price(sr)
            except Exception as e:  # источник изолирован
                log.warning("источник %s упал: %s", sr.source, e)
                stage_log.append(f"источник {sr.source}: ошибка ({e})")
                continue
            if not hit.available:
                stage_log.append(f"источник {sr.source}: недоступен")
                continue
            if hit.price is None:
                stage_log.append(f"источник {sr.source}: цена не найдена")
                continue
            try:
                decision = matcher.match(item, hit)
            except Exception as e:
                log.warning("матчинг %s упал: %s", sr.source, e)
                decision = MatchDecision(is_match=False, confidence=0.0, reason=f"ошибка: {e}")
            stage_log.append(
                f"источник {sr.source}: цена {hit.price} {hit.currency}, "
                f"match={decision.is_match} conf={decision.confidence:.2f}"
            )
            hits_with_decisions.append((hit, decision))

        # 7) сравнение и флаг
        report = compare.build_item_report(item, query, hits_with_decisions, stage_log=stage_log)

        # сохраняем найденные рыночные цены в историю веб-поиска (с датой)
        _persist_search_history(item, query, report, ctx.embedding, canonical)
        return report, ctx

    except Exception as e:
        log.exception("позиция «%s» упала целиком", item.name[:40])
        return compare.build_item_report(item, None, [], stage_log=stage_log, error=str(e)), ctx


def analyze(job_id: str, filename: str, content: bytes) -> Iterator[dict]:
    """Генератор событий прогресса. Последнее событие type=done содержит полный отчёт."""
    report = AnalysisReport(job_id=job_id, filename=filename)

    # 1) извлечение
    try:
        raw_text = extract_mod.extract(filename, content)
    except extract_mod.ExtractionError as e:
        yield {"type": "error", "message": str(e)}
        return
    except Exception as e:
        log.exception("extract упал")
        yield {"type": "error", "message": f"Ошибка извлечения: {e}"}
        return
    yield {"type": "extract", "chars": len(raw_text)}

    # 2) парсинг позиций
    try:
        items = parse_items(raw_text)
    except Exception as e:
        log.exception("parse_items упал")
        yield {"type": "error", "message": f"Не удалось распарсить позиции: {e}"}
        return
    if not items:
        yield {"type": "error", "message": "В файле не найдено ни одной позиции."}
        return
    total = len(items)
    yield {"type": "parsed", "count": total}

    # 3–7) по позициям, последовательно
    contexts: List[ItemContext] = []
    for idx, item in enumerate(items):
        yield {"type": "item_start", "index": idx, "total": total, "name": item.name}
        item_report, ctx = _process_item(item)
        report.items.append(item_report)
        contexts.append(ctx)
        yield {
            "type": "item_done",
            "index": idx,
            "total": total,
            "report": item_report.model_dump(),
        }

    # сохраняем контексты позиций для последующего исторического анализа по периоду
    JOB_CONTEXTS[job_id] = contexts

    # 8) сводка
    report.summary = compare.build_summary(report.items)
    yield {"type": "done", "report": report.model_dump()}
