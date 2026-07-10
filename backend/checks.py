"""Проверки договора (Этап 2, раздел 6 ТЗ) → таблица checks.

Четыре типа проверок:
  characteristics — смысловое сравнение характеристик с историческим аналогом (LLM);
  price           — ценовой анализ Этапа 1 (min/max/диапазон/count по периоду, без средней);
  quantity        — сверка количеств между документами договора (данные/правила);
  conditions      — наличие обязательных условий (данные/правила).

Результат — ПОМОЩНИК закупщика, не автоматический отказ. Чистая логика (quantity/conditions)
вынесена в отдельные функции и покрыта тестами.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import analysis
import repository
from knowledge import resolve_period
from llm import chat_model
from logging_conf import get_logger
from models import SpecCompare

log = get_logger("checks")

_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


def _worst(risks: List[str]) -> str:
    return max(risks, key=lambda r: _RANK.get(r, 0)) if risks else "unknown"


# ── (d) conditions — чистая логика ───────────────────────────────────────────
_CRITICAL = {"warranty": "гарантия", "delivery_term": "срок поставки",
             "payment_terms": "условия оплаты"}
_EXTRA = {"penalties": "штрафные санкции", "appendices": "приложения",
          "tech_spec": "техническая спецификация"}


def check_conditions(fields: dict) -> dict:
    """fields: warranty, delivery_term, payment_terms (str) + conditions (dict флагов)."""
    cond = fields.get("conditions") or {}
    missing_critical = [lbl for k, lbl in _CRITICAL.items()
                        if not str(fields.get(k) or "").strip()]
    missing_extra = [lbl for k, lbl in _EXTRA.items() if not cond.get(k)]
    present = [lbl for k, lbl in {**_CRITICAL, **_EXTRA}.items()
               if (str(fields.get(k) or "").strip() or cond.get(k))]

    if missing_critical:
        risk = "high"
    elif missing_extra:
        risk = "medium"
    else:
        risk = "low"
    return {
        "type": "conditions",
        "risk_level": risk,
        "result": {"present": present, "missing_count": len(missing_critical) + len(missing_extra)},
        "findings": {"missing_critical": missing_critical, "missing_extra": missing_extra},
    }


# ── (c) quantity — чистая логика ─────────────────────────────────────────────
def check_quantity(groups: List[dict]) -> dict:
    """groups: [{'label': str, 'items': {canonical: qty}}]. Сверяет кол-ва между документами."""
    real = [g for g in groups if g.get("items")]
    if len(real) < 2:
        return {
            "type": "quantity",
            "risk_level": "low",
            "result": {"sources": len(real), "note": "сверка невозможна: один источник"},
            "findings": {"mismatches": []},
        }
    keys = set()
    for g in real:
        keys.update(g["items"].keys())
    mismatches = []
    for k in sorted(keys):
        per = {g["label"]: g["items"].get(k) for g in real if k in g["items"]}
        vals = [v for v in per.values() if v is not None]
        if len(vals) >= 2 and len(set(vals)) > 1:
            mismatches.append({"item": k, "per_source": per})
    risk = "medium" if mismatches else "low"
    return {
        "type": "quantity",
        "risk_level": risk,
        "result": {"sources": len(real), "compared_items": len(keys)},
        "findings": {"mismatches": mismatches},
    }


# ── (a) characteristics — LLM ────────────────────────────────────────────────
_SPEC_SYSTEM = (
    "Ты сверяешь характеристики двух товаров — новой закупки и исторического аналога. "
    "Учитывай модель, производителя, комплектацию, мощность, объём, размеры, ключевые параметры. "
    "Верни ТОЛЬКО JSON: "
    '{"differs": bool, "significant": bool, "differences": [str], "reason": str}. '
    "differences — конкретные отличия (что и как отличается). "
    "significant=true, если отличается модель/производитель/важные параметры (не косметика)."
)


def _compare_specs(new_desc: str, new_specs: Optional[dict],
                   analog_desc: str, analog_specs: Optional[dict]) -> SpecCompare:
    user = (
        f"НОВЫЙ товар: {new_desc}\nХарактеристики: {new_specs or '—'}\n\n"
        f"ИСТОРИЧЕСКИЙ аналог: {analog_desc}\nХарактеристики: {analog_specs or '—'}\n\n"
        "Сравни и верни JSON."
    )
    try:
        return chat_model(_SPEC_SYSTEM, user, SpecCompare, retries=2, max_tokens=500)
    except Exception as e:
        log.warning("сравнение характеристик не удалось: %s", e)
        return SpecCompare(differs=False, significant=False, reason=f"ошибка сравнения: {e}")


def _check_characteristics(sess, line_items) -> dict:
    findings = []
    compared = 0
    risks = []
    for li in line_items:
        analog = repository.find_analog_line_item(sess, li)
        if analog is None:
            continue
        compared += 1
        cmp = _compare_specs(li.name, li.specs, analog.name, analog.specs)
        if cmp.differs:
            findings.append({
                "item": li.name,
                "analog": analog.name,
                "significant": cmp.significant,
                "differences": cmp.differences,
                "reason": cmp.reason,
            })
            risks.append("medium" if cmp.significant else "low")
    if compared == 0:
        return {
            "type": "characteristics",
            "risk_level": "low",
            "result": {"compared": 0, "note": "нет исторических данных для сравнения"},
            "findings": {"items": []},
        }
    return {
        "type": "characteristics",
        "risk_level": _worst(risks) if risks else "low",
        "result": {"compared": compared, "with_differences": len(findings)},
        "findings": {"items": findings},
    }


# ── (b) price — ценовой анализ Этапа 1 как проверка ─────────────────────────
def _check_price(sess, line_items, period_months: Optional[int]) -> dict:
    df, dt, label = resolve_period(period_months, None, None)
    per_item = []
    risks = []
    for li in line_items:
        internal = repository.find_internal_observations(
            sess, canonical=li.canonical_name or "", model=li.model,
            manufacturer=li.manufacturer, ntin=li.ntin, embedding=li.embedding,
            date_from=df, date_to=dt)
        web = repository.find_web_observations(
            sess, canonical=li.canonical_name or "", embedding=li.embedding,
            date_from=df, date_to=dt)
        res = analysis.analyze(float(li.unit_price) if li.unit_price else None,
                               internal, web, label)
        risks.append(res.risk_level)
        per_item.append({
            "item": li.name,
            "kp_unit_price": float(li.unit_price) if li.unit_price else None,
            "combined_min": res.combined_min, "combined_max": res.combined_max,
            "combined_count": res.combined_count, "risk_level": res.risk_level,
            "recommendation": res.recommendation or res.message,
        })
    flagged = [p for p in per_item if p["risk_level"] == "high"]
    return {
        "type": "price",
        "risk_level": _worst(risks) if risks else "unknown",
        "result": {"period_label": label, "items": per_item},
        "findings": {"high": flagged},
    }


# ── Оркестрация ──────────────────────────────────────────────────────────────
def run_all_checks(sess, contract, period_months: Optional[int]) -> List[dict]:
    """Выполняет 4 проверки договора, перезаписывает записи в checks, возвращает их."""
    line_items = repository.get_line_items(sess, contract.id)

    checks = [
        _check_characteristics(sess, line_items),
        _check_price(sess, line_items, period_months),
        check_quantity(_quantity_groups(line_items)),
        check_conditions({
            "warranty": contract.warranty,
            "delivery_term": contract.delivery_term,
            "payment_terms": contract.payment_terms,
            "conditions": contract.conditions,
        }),
    ]

    repository.replace_checks(sess, contract.id)
    for c in checks:
        repository.save_check(sess, contract_id=contract.id, type=c["type"],
                              result=c["result"], risk_level=c["risk_level"],
                              findings=c["findings"])
    repository.audit(sess, None, "run_checks", "contract", contract.id,
                     {"risks": {c["type"]: c["risk_level"] for c in checks}})
    log.info("проверки договора #%s: %s", contract.id,
             {c["type"]: c["risk_level"] for c in checks})
    return checks


def _quantity_groups(line_items) -> List[dict]:
    """Группирует позиции по документу-источнику (contract vs offer)."""
    groups: Dict[Tuple, dict] = {}
    for li in line_items:
        key = ("contract", li.contract_id) if li.contract_id else ("offer", li.offer_id)
        label = "договор" if key[0] == "contract" else f"КП/спец. #{key[1]}"
        g = groups.setdefault(key, {"label": label, "items": {}})
        ckey = li.canonical_name or li.name
        if li.qty is not None:
            g["items"][ckey] = float(li.qty)
    return list(groups.values())
