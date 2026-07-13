"""Оркестрация пайплайна. Позиции обрабатываются ПОСЛЕДОВАТЕЛЬНО (LLM на CPU медленный).

Поток по позиции: нормализация → ШИРОКИЙ поиск кандидатов → ОБЯЗАТЕЛЬНАЯ верификация
каждой цены (crawl4ai + сверка карточки товара) → сравнение только по verified-ценам.
Цена без подтверждённой карточки товара отбрасывается (не показываем, не сохраняем).

Изоляция ошибок: сбой на позиции/источнике не роняет весь анализ.
analyze() — генератор событий прогресса для SSE (включая прогресс верификации).
"""
from __future__ import annotations

import queue as _queue
import threading
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterator, List, Optional, Tuple

import compare
import db
import embeddings
import extract as extract_mod
import repository
import verify
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
    name: str
    canonical_key: str
    canonical_name: str
    ntin: Optional[str]
    kp_unit_price: Optional[float]
    embedding: Optional[List[float]] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None


JOB_CONTEXTS: Dict[str, List[ItemContext]] = {}


def _persist_search_history(item: Item, query, report: ItemReport,
                            embedding: Optional[List[float]], canonical: str) -> None:
    """Сохраняет ТОЛЬКО подтверждённые (verified) рыночные цены в price_search_history."""
    s = get_settings()
    if not db.is_enabled() or (s.search_provider or "mock").lower() == "mock":
        return
    if not report.confirmed_prices:
        return
    try:
        with db.session_scope() as sess:
            for cp in report.confirmed_prices:
                repository.record_search_result(
                    sess, query=query.query if query else item.name, item_name=item.name,
                    canonical=canonical, model=None, unit_price=cp.price_per_kp_unit,
                    currency=cp.currency, source_url=cp.url, source_site=cp.source,
                    found_at=date.today(), embedding=embedding)
    except Exception as e:
        log.warning("не сохранил историю поиска: %s", e)


def _process_mock(item: Item, query, stage_log: List[str]) -> ItemReport:
    """Старый mock-путь (без верификации) — для отладки пайплайна без интернета."""
    from fetch_price import fetch_price

    provider = get_provider()
    results = provider.search(query.query)
    matcher = get_matcher()
    hits: List[Tuple[PriceHit, MatchDecision]] = []
    for sr in results:
        hit = fetch_price(sr)
        if hit.available and hit.price is not None:
            hits.append((hit, matcher.match(item, hit)))
    stage_log.append(f"mock: {len(hits)} цен")
    return compare.build_item_report(item, query, hits, stage_log=stage_log)


def _process_item_stream(item: Item, idx: int, total: int, out: list) -> Iterator[dict]:
    """Генератор: yield-ит события прогресса верификации; в out кладёт (ItemReport, ItemContext)."""
    stage_log: List[str] = []
    canonical = repository.canonical_key(item.name, item.model, item.manufacturer, item.ntin)
    ctx = ItemContext(name=item.name, canonical_key=canonical, canonical_name=item.name,
                      ntin=item.ntin, kp_unit_price=compare._kp_unit_price(item),
                      model=item.model, manufacturer=item.manufacturer)
    try:
        query = normalize_item(item)
        ctx.canonical_name = query.query
        ctx.canonical_key = canonical = repository.canonical_key(
            query.query, item.model, item.manufacturer, item.ntin)
        ctx.embedding = embeddings.embed(query.query) if (db.is_enabled() or embeddings.is_enabled()) else None
        stage_log.append(f"запрос: «{query.query}» (множитель x{query.pack_multiplier:g})")

        s = get_settings()
        if (s.search_provider or "mock").lower() == "mock":
            out.append((_process_mock(item, query, stage_log), ctx))
            return

        # 1) широкий поиск кандидатов
        provider = get_provider()
        candidates = provider.search(query.query)
        stage_log.append(f"кандидатов найдено: {len(candidates)} [{provider.__class__.__name__}]")
        if not candidates:
            report = compare.build_item_report(item, query, [], stage_log=stage_log)
            report.flag = "gray"
            report.flag_reason = "рыночные цены не подтверждены (кандидаты не найдены)"
            out.append((report, ctx))
            return

        # 2) обязательная верификация каждого кандидата (в отдельном потоке + прогресс)
        pq: _queue.Queue = _queue.Queue()
        holder: dict = {}

        def worker():
            try:
                holder["res"] = verify.verify_candidates(item, candidates, lambda d, t: pq.put((d, t)))
            except Exception as e:
                holder["err"] = e

        th = threading.Thread(target=worker, daemon=True)
        th.start()
        while th.is_alive() or not pq.empty():
            try:
                d, t = pq.get(timeout=0.25)
                yield {"type": "verify_progress", "index": idx, "total": total,
                       "done": d, "verify_total": t}
            except _queue.Empty:
                continue
        th.join()
        if "err" in holder:
            raise holder["err"]
        verified, stats = holder["res"]
        stage_log.append(f"подтверждено: {stats['verified']}/{stats['found']}")

        report = compare.build_item_report(item, query, verified, stage_log=stage_log)
        report.candidates_found = stats["found"]
        report.candidates_verified = stats["verified"]
        if not verified:
            report.flag = "gray"
            report.flag_reason = "рыночные цены не подтверждены"
        _persist_search_history(item, query, report, ctx.embedding, canonical)
        out.append((report, ctx))

    except Exception as e:
        log.exception("позиция «%s» упала целиком", item.name[:40])
        report = compare.build_item_report(item, None, [], stage_log=stage_log, error=str(e))
        out.append((report, ctx))


def analyze(job_id: str, filename: str, content: bytes) -> Iterator[dict]:
    """Генератор событий прогресса. Последнее событие type=done содержит полный отчёт."""
    report = AnalysisReport(job_id=job_id, filename=filename)

    # 1) извлечение (xlsx / текстовый PDF / скан через OCR)
    try:
        result = extract_mod.extract(filename, content)
    except extract_mod.ExtractionError as e:
        yield {"type": "error", "message": str(e)}
        return
    except Exception as e:
        log.exception("extract упал")
        yield {"type": "error", "message": f"Ошибка извлечения: {e}"}
        return
    yield {"type": "extract", "chars": len(result.text), "source_type": result.source_type}

    # 2) структурирование позиций
    try:
        if result.items is not None:
            items = [Item.model_validate(x) for x in result.items]
            items = [it for it in items if it.name and it.name.strip()]
        else:
            items = parse_items(result.text)
    except Exception as e:
        log.exception("parse_items упал")
        yield {"type": "error", "message": f"Не удалось распарсить позиции: {e}"}
        return
    if not items:
        yield {"type": "error", "message": "В файле не найдено ни одной позиции."}
        return
    total = len(items)
    yield {"type": "parsed", "count": total}

    # 3) по позициям, последовательно
    contexts: List[ItemContext] = []
    for idx, item in enumerate(items):
        yield {"type": "item_start", "index": idx, "total": total, "name": item.name}
        box: list = []
        for ev in _process_item_stream(item, idx, total, box):
            yield ev
        item_report, ctx = box[0]
        report.items.append(item_report)
        contexts.append(ctx)
        yield {"type": "item_done", "index": idx, "total": total, "report": item_report.model_dump()}

    JOB_CONTEXTS[job_id] = contexts
    report.summary = compare.build_summary(report.items)
    yield {"type": "done", "report": report.model_dump()}
