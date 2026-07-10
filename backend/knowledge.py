"""База знаний закупок: разрешение периода, исторический анализ по job и приём договоров.

Связывает пайплайн (контексты позиций), репозиторий (наблюдения из БД) и analysis.py
(чистая статистика/риск). Всё guarded: если БД выключена — понятное сообщение, не падаем.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

import analysis
import db
import embeddings
import pipeline
import repository
from config import get_settings
from logging_conf import get_logger

log = get_logger("knowledge")

_MONTH_NAMES = ("", "янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def _minus_months(d: date, months: int) -> date:
    m = d.month - 1 - months
    y = d.year + m // 12
    m = m % 12 + 1
    # день ставим 1, чтобы не выпасть за границы месяца
    return date(y, m, 1)


def resolve_period(period_months: Optional[int], date_from: Optional[str],
                   date_to: Optional[str]) -> Tuple[Optional[date], Optional[date], str]:
    """Возвращает (date_from, date_to, ru-метка). Приоритет — явный диапазон дат."""
    if date_from or date_to:
        df = date.fromisoformat(date_from) if date_from else None
        dt = date.fromisoformat(date_to) if date_to else None
        label = "период " + (f"с {df.strftime('%d.%m.%Y')}" if df else "") + \
                (f" по {dt.strftime('%d.%m.%Y')}" if dt else "")
        return df, dt, label.strip()
    if period_months and period_months > 0:
        df = _minus_months(date.today(), period_months)
        return df, None, f"за {period_months} мес"
    return None, None, "за всё время"


def historical_for_job(job_id: str, period_months: Optional[int],
                       date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Исторический ценовой анализ по всем позициям job за выбранный период."""
    df, dt, label = resolve_period(period_months, date_from, date_to)

    if not db.is_enabled():
        return {"enabled": False, "period_label": label, "items": [],
                "message": "База знаний выключена (DATABASE_URL не задан)."}

    contexts = pipeline.JOB_CONTEXTS.get(job_id)
    if contexts is None:
        return {"enabled": True, "period_label": label, "items": [],
                "message": "Анализ не найден — сначала выполните анализ КП."}

    items_out: List[dict] = []
    with db.session_scope() as sess:
        for ctx in contexts:
            try:
                internal = repository.find_internal_observations(
                    sess, canonical=ctx.canonical_key, model=ctx.model,
                    manufacturer=ctx.manufacturer, ntin=ctx.ntin,
                    embedding=ctx.embedding, date_from=df, date_to=dt)
                web = repository.find_web_observations(
                    sess, canonical=ctx.canonical_key, embedding=ctx.embedding,
                    date_from=df, date_to=dt)
                res = analysis.analyze(ctx.kp_unit_price, internal, web, label)
                d = res.to_dict()
                d["name"] = ctx.name
                items_out.append(d)
            except Exception as e:
                log.warning("исторический анализ «%s» упал: %s", ctx.name[:30], e)
                items_out.append({"name": ctx.name, "risk_level": "unknown",
                                  "message": f"ошибка анализа: {e}", "period_label": label})
    return {"enabled": True, "period_label": label,
            "period_months": period_months, "date_from": df.isoformat() if df else None,
            "date_to": dt.isoformat() if dt else None, "items": items_out}


def ingest_contract(header: dict, items: List[dict], user_email: Optional[str]) -> dict:
    """Сохраняет подтверждённый договор/КП в базу знаний (с эмбеддингами позиций)."""
    if not db.is_enabled():
        raise RuntimeError("База знаний выключена (DATABASE_URL не задан).")

    # обогащаем позиции каноническим ключом и эмбеддингом
    for it in items:
        canonical = repository.canonical_key(
            it.get("name", ""), it.get("model"), it.get("manufacturer"), it.get("ntin"))
        it["canonical_name"] = it.get("canonical_name") or canonical
        it["embedding"] = embeddings.embed(it.get("canonical_name") or it.get("name", ""))

    # дата закупки
    if header.get("date") and isinstance(header["date"], str):
        try:
            header["date"] = date.fromisoformat(header["date"])
        except ValueError:
            header["date"] = None

    with db.session_scope() as sess:
        contract = repository.save_contract(sess, header=header, items=items, created_by=user_email)
        sess.flush()
        cid = contract.id
    log.info("договор сохранён в базу знаний: id=%s, позиций=%d", cid, len(items))
    return {"contract_id": cid, "items": len(items)}
