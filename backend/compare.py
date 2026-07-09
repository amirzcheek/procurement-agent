"""Этап 7. Сравнение цены КП с рынком и выставление флага.

- найденные цены приводим к единице КП через pack_multiplier (цена за упаковку → за штуку);
- считаем медиану/мин/макс рынка, дельту % (КП vs медиана);
- флаг: green ≤ медиана*1.1; yellow ≤ *1.3; red выше *1.3;
  gray — нет подтверждённых совпадений ИЛИ низкий средний confidence (на ручную проверку).
"""
from __future__ import annotations

import statistics
from typing import List, Optional, Tuple

from config import get_settings
from logging_conf import get_logger
from models import (
    ConfirmedPrice,
    Item,
    ItemReport,
    MatchDecision,
    NormalizedQuery,
    PriceHit,
    Summary,
)

log = get_logger("compare")


def _kp_unit_price(item: Item) -> Optional[float]:
    """Цена КП за единицу: берём unit_price, иначе total/qty."""
    if item.unit_price and item.unit_price > 0:
        return float(item.unit_price)
    if item.total_price and item.qty and item.qty > 0:
        return float(item.total_price) / float(item.qty)
    return None


def build_item_report(
    item: Item,
    query: Optional[NormalizedQuery],
    hits_with_decisions: List[Tuple[PriceHit, MatchDecision]],
    stage_log: Optional[List[str]] = None,
    error: Optional[str] = None,
) -> ItemReport:
    s = get_settings()
    multiplier = query.pack_multiplier if query and query.pack_multiplier > 0 else 1.0

    report = ItemReport(item=item, query=query, stage_log=stage_log or [], error=error)
    report.kp_unit_price = _kp_unit_price(item)

    # Оставляем только подтверждённые матчингом цены с достаточной уверенностью.
    confirmed: List[ConfirmedPrice] = []
    for hit, decision in hits_with_decisions:
        if not decision.is_match:
            continue
        if decision.confidence < s.match_confidence_min:
            continue
        if not hit.available or hit.price is None or hit.price <= 0:
            continue
        confirmed.append(
            ConfirmedPrice(
                price_market_unit=float(hit.price),
                price_per_kp_unit=float(hit.price) / multiplier,
                currency=hit.currency or "KZT",
                title=hit.title or "",
                url=hit.url or "",
                source=hit.source or "",
                confidence=decision.confidence,
                in_stock=hit.in_stock,
            )
        )
    report.confirmed_prices = confirmed

    if not confirmed:
        report.flag = "gray"
        report.flag_reason = "Нет подтверждённых рыночных совпадений — нужна ручная проверка."
        return report

    prices = [c.price_per_kp_unit for c in confirmed]
    report.market_min = min(prices)
    report.market_max = max(prices)
    report.market_median = statistics.median(prices)
    report.avg_confidence = sum(c.confidence for c in confirmed) / len(confirmed)

    # Низкий средний confidence → на ручную проверку.
    if report.avg_confidence < s.match_confidence_min:
        report.flag = "gray"
        report.flag_reason = f"Низкий средний confidence ({report.avg_confidence:.2f}) — ручная проверка."
        return report

    kp = report.kp_unit_price
    if kp is None:
        report.flag = "gray"
        report.flag_reason = "В КП нет цены за единицу — сравнение невозможно."
        return report

    median = report.market_median
    report.delta_pct = (kp - median) / median * 100.0 if median > 0 else None

    if kp <= median * 1.1:
        report.flag = "green"
        report.flag_reason = "Цена КП в пределах рынка (≤ медиана +10%)."
    elif kp <= median * 1.3:
        report.flag = "yellow"
        report.flag_reason = "Цена КП выше медианы на 10–30% — стоит проверить."
    else:
        report.flag = "red"
        report.flag_reason = "Цена КП выше медианы более чем на 30% — вероятное завышение."

    # Оценочная переплата по позиции на весь объём.
    if kp > median:
        qty = item.qty if item.qty and item.qty > 0 else 1.0
        report.estimated_overpay = (kp - median) * qty

    log.info(
        "compare: «%s» КП=%.2f медиана=%.2f Δ=%.1f%% → %s",
        item.name[:30], kp, median, report.delta_pct or 0.0, report.flag,
    )
    return report


def build_summary(items: List[ItemReport]) -> Summary:
    summary = Summary(total_items=len(items))
    for r in items:
        setattr(summary, r.flag, getattr(summary, r.flag) + 1)
        if r.estimated_overpay:
            summary.estimated_total_overpay += r.estimated_overpay
    return summary
