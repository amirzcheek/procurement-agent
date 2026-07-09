"""Оркестрация пайплайна. Позиции обрабатываются ПОСЛЕДОВАТЕЛЬНО (LLM на CPU медленный).

Изоляция ошибок: сбой на одной позиции или одном источнике не роняет весь анализ.
Каждый этап логируется (извлечено / запрос / найдено / решение матчинга).

analyze() — генератор событий прогресса для SSE.
"""
from __future__ import annotations

from typing import Iterator, List, Tuple

import compare
import extract as extract_mod
from logging_conf import get_logger
from match import get_matcher
from models import AnalysisReport, Item, ItemReport, MatchDecision, PriceHit
from normalize import normalize_item
from parse_items import parse_items
from search import get_provider

log = get_logger("pipeline")


def _process_item(item: Item) -> ItemReport:
    """Полный цикл по одной позиции. Не бросает исключений наружу."""
    stage_log: List[str] = []
    try:
        # 3) нормализация
        query = normalize_item(item)
        stage_log.append(f"запрос: «{query.query}» (множитель x{query.pack_multiplier:g})")

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
        return compare.build_item_report(item, query, hits_with_decisions, stage_log=stage_log)

    except Exception as e:
        log.exception("позиция «%s» упала целиком", item.name[:40])
        return compare.build_item_report(item, None, [], stage_log=stage_log, error=str(e))


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
    for idx, item in enumerate(items):
        yield {"type": "item_start", "index": idx, "total": total, "name": item.name}
        item_report = _process_item(item)
        report.items.append(item_report)
        yield {
            "type": "item_done",
            "index": idx,
            "total": total,
            "report": item_report.model_dump(),
        }

    # 8) сводка
    report.summary = compare.build_summary(report.items)
    yield {"type": "done", "report": report.model_dump()}
