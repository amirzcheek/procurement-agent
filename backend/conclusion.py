"""Заключение по договору (Этап 2, часть 2, раздел 8 ТЗ).

Собирает всё вместе БЕЗ LLM (данные уже посчитаны в checks и Этапе 1):
реквизиты, 4 проверки, по каждой позиции min/max по обоим источникам за период + тренд +
кол-во аналогов, итоговый риск + факторы, рекомендации. Результат — помощник, не вердикт.
"""
from __future__ import annotations

from typing import Optional

import analysis
import repository
from knowledge import resolve_period
from logging_conf import get_logger

log = get_logger("conclusion")

DISCLAIMER = (
    "Предварительное заключение. Это помощник закупщика, а не окончательное решение и не "
    "автоматический отказ поставщику. Все выводы требуют проверки человеком."
)

_REC_BY_FACTOR = {
    "завышение цены": "Запросить обоснование стоимости — цена выше исторического максимума за период.",
    "занижение цены": "Проверить корректность позиции/комплектации — цена существенно ниже минимума.",
    "ценовое отклонение": "Проверить цену — отклонение от исторического диапазона.",
    "изменение характеристик": "Сверить характеристики с аналогом — есть существенные отличия.",
    "изменение количества": "Сверить количество между документами — обнаружены расхождения.",
    "несоответствие КП/спецификации": "Устранить расхождения между договором и КП/спецификацией.",
    "отсутствие обязательных условий": "Добавить обязательные условия (гарантия/срок/оплата).",
    "отсутствие обязательных документов": "Приложить недостающие документы (приложения/техспецификацию).",
}


def _check_dict(c) -> dict:
    return {"type": c.type, "risk_level": c.risk_level, "result": c.result, "findings": c.findings}


def _recommendations(risk_level: str, factors: list) -> list:
    recs = []
    seen = set()
    for f in factors:
        name = f.get("factor")
        rec = _REC_BY_FACTOR.get(name)
        if rec and rec not in seen:
            recs.append(rec)
            seen.add(rec)
    if risk_level == "high" and not recs:
        recs.append("Высокий риск — провести дополнительную проверку и запросить обоснование.")
    if not recs:
        recs.append("Существенных отклонений не выявлено. Финальное решение — за закупщиком.")
    return recs


def build_conclusion(sess, contract, period_months: Optional[int]) -> dict:
    df, dt, label = resolve_period(period_months, None, None)
    line_items = repository.get_line_items(sess, contract.id)

    items = []
    for li in line_items:
        internal = repository.find_internal_observations(
            sess, canonical=li.canonical_name or "", model=li.model,
            manufacturer=li.manufacturer, ntin=li.ntin, embedding=li.embedding,
            date_from=df, date_to=dt)
        web = repository.find_web_observations(
            sess, canonical=li.canonical_name or "", embedding=li.embedding,
            date_from=df, date_to=dt)
        res = analysis.analyze(float(li.unit_price) if li.unit_price else None, internal, web, label)
        d = res.to_dict()
        d.update({"name": li.name, "model": li.model, "manufacturer": li.manufacturer,
                  "qty": float(li.qty) if li.qty is not None else None, "unit": li.unit})
        items.append(d)

    checks = [_check_dict(c) for c in repository.get_checks(sess, contract.id)]
    factors = (contract.risk_factors or {}).get("factors", [])
    risk_level = contract.risk_level or "unknown"

    return {
        "contract": {
            "id": contract.id, "number": contract.number,
            "date": contract.date.isoformat() if contract.date else None,
            "supplier": repository.supplier_name(sess, contract.supplier_id),
            "customer": contract.customer, "subject": contract.subject,
            "funding_source": contract.funding_source,
            "total_sum": float(contract.total_sum) if contract.total_sum else None,
            "status": contract.status,
        },
        "period_label": label, "period_months": period_months,
        "risk_level": risk_level, "risk_factors": factors,
        "checks": checks, "items": items,
        "recommendations": _recommendations(risk_level, factors),
        "disclaimer": DISCLAIMER,
    }
