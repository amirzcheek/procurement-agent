"""Слой доступа к базе знаний: сохранение закупок/поиска и поиск аналогов по периоду.

Аналоги ищем двумя способами: точно (ntin ИЛИ model+manufacturer) и семантически
(pgvector cosine по эмбеддингу). Наблюдения (цена+дата) возвращаем сырыми — статистику
и риск считает analysis.py (чистая логика, тестируется без БД).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from logging_conf import get_logger
from models_db import (
    AuditLog,
    Check,
    Contract,
    LineItem,
    PriceHistory,
    PriceSearchHistory,
    Supplier,
    User,
)

log = get_logger("repository")

# Порог косинусной дистанции для семантических аналогов (0 — идентичны, 2 — противоположны).
_COSINE_MAX_DISTANCE = 0.35
_ANALOG_LIMIT = 200


@dataclass
class PriceObservation:
    """Одно наблюдение цены (внутреннее или из веб-поиска) для анализа."""

    unit_price: float
    obs_date: Optional[date]
    source: str          # домен площадки или «внутренняя»
    unit: Optional[str] = None
    url: Optional[str] = None
    supplier: Optional[str] = None


def canonical_key(name: str, model: Optional[str], manufacturer: Optional[str],
                  ntin: Optional[str]) -> str:
    """Стабильный ключ идентичности товара для склейки наблюдений во времени.

    Приоритет — NTIN/GTIN (надёжнее всего). Иначе — нормализованные бренд+модель,
    иначе — нормализованное имя.
    """
    if ntin and ntin.strip():
        return f"ntin:{ntin.strip()}"
    parts = [p for p in (manufacturer, model) if p and p.strip()]
    if parts:
        base = " ".join(parts)
    else:
        base = name or ""
    norm = re.sub(r"\s+", " ", base.lower()).strip()
    return f"name:{norm}"


# ── Аудит ────────────────────────────────────────────────────────────────────
def audit(sess: Session, user_email: Optional[str], action: str,
          entity_type: Optional[str] = None, entity_id: Optional[str] = None,
          details: Optional[dict] = None) -> None:
    sess.add(AuditLog(user_email=user_email, action=action, entity_type=entity_type,
                      entity_id=str(entity_id) if entity_id is not None else None,
                      details=details))


# ── Пользователи/поставщики ─────────────────────────────────────────────────
def upsert_user(sess: Session, email: str, display_name: str, role: str) -> User:
    user = sess.get(User, email)
    if user is None:
        user = User(email=email, display_name=display_name, role=role)
        sess.add(user)
    else:
        user.display_name = display_name or user.display_name
        if role:
            user.role = role
    return user


def get_or_create_supplier(sess: Session, name: Optional[str],
                           bin_iin: Optional[str] = None) -> Optional[Supplier]:
    if not name or not name.strip():
        return None
    q = select(Supplier).where(Supplier.name == name.strip())
    sup = sess.scalars(q).first()
    if sup is None:
        sup = Supplier(name=name.strip(), bin_iin=bin_iin)
        sess.add(sup)
        sess.flush()
    return sup


# ── Сохранение веб-поиска цен ────────────────────────────────────────────────
def record_search_result(sess: Session, *, query: str, item_name: str, canonical: str,
                         model: Optional[str], unit_price: float, currency: str,
                         source_url: Optional[str], source_site: Optional[str],
                         found_at: date, embedding: Optional[List[float]]) -> None:
    sess.add(PriceSearchHistory(
        query=query, item_name=item_name, canonical_key=canonical, model=model,
        unit_price=unit_price, currency=currency or "KZT", source_url=source_url,
        source_site=source_site, found_at=found_at, embedding=embedding,
    ))


# ── Сохранение подтверждённой закупки в базу знаний ─────────────────────────
def save_contract(sess: Session, *, header: dict, items: List[dict],
                  created_by: Optional[str]) -> Contract:
    """header — поля договора; items — список позиций (dict с полями LineItem + embedding)."""
    supplier = get_or_create_supplier(sess, header.get("supplier"), header.get("supplier_bin"))
    contract = Contract(
        number=header.get("number"),
        date=header.get("date"),
        customer=header.get("customer"),
        supplier_id=supplier.id if supplier else None,
        subject=header.get("subject"),
        funding_source=header.get("funding_source"),
        total_sum=header.get("total_sum"),
        delivery_term=header.get("delivery_term"),
        warranty=header.get("warranty"),
        payment_terms=header.get("payment_terms"),
        conditions=header.get("conditions"),
        status="checked",
        created_by=created_by,
    )
    sess.add(contract)
    sess.flush()

    pdate = header.get("date")
    for it in items:
        canonical = it.get("canonical_name") or canonical_key(
            it.get("name", ""), it.get("model"), it.get("manufacturer"), it.get("ntin"))
        sess.add(LineItem(
            contract_id=contract.id,
            name=it.get("name", ""),
            canonical_name=canonical,
            model=it.get("model"),
            manufacturer=it.get("manufacturer"),
            category=it.get("category"),
            specs=it.get("specs"),
            qty=it.get("qty"),
            unit=it.get("unit"),
            unit_price=it.get("unit_price"),
            total_price=it.get("total_price"),
            ntin=it.get("ntin"),
            embedding=it.get("embedding"),
            purchase_date=pdate,
        ))
        if it.get("unit_price"):
            sess.add(PriceHistory(
                canonical_key=canonical,
                item_name=it.get("name", ""),
                model=it.get("model"),
                manufacturer=it.get("manufacturer"),
                unit_price=it.get("unit_price"),
                unit=it.get("unit"),
                supplier_id=supplier.id if supplier else None,
                contract_id=contract.id,
                purchase_date=pdate,
            ))
    audit(sess, created_by, "save_contract", "contract", contract.id,
          {"items": len(items), "number": header.get("number")})
    return contract


# ── Поиск аналогов по периоду ────────────────────────────────────────────────
def _date_clause(column, date_from: Optional[date], date_to: Optional[date]):
    clauses = []
    if date_from:
        clauses.append(column >= date_from)
    if date_to:
        clauses.append(column <= date_to)
    return clauses


def find_internal_observations(sess: Session, *, canonical: str, model: Optional[str],
                               manufacturer: Optional[str], ntin: Optional[str],
                               embedding: Optional[List[float]],
                               date_from: Optional[date], date_to: Optional[date]
                               ) -> List[PriceObservation]:
    """Внутренняя история (price_history) по аналогам за период."""
    # Точное совпадение: ntin ИЛИ (model+manufacturer) ИЛИ canonical_key.
    exact = [PriceHistory.canonical_key == canonical]
    if ntin:
        exact.append(PriceHistory.canonical_key == f"ntin:{ntin.strip()}")
    if model and manufacturer:
        exact.append((PriceHistory.model.ilike(model)) & (PriceHistory.manufacturer.ilike(manufacturer)))
    q = select(PriceHistory).where(or_(*exact))
    for c in _date_clause(PriceHistory.purchase_date, date_from, date_to):
        q = q.where(c)
    rows = sess.scalars(q.limit(_ANALOG_LIMIT)).all()

    out = [PriceObservation(unit_price=float(r.unit_price), obs_date=r.purchase_date,
                            source="внутренняя", unit=r.unit) for r in rows]
    return out


# ── Договоры / позиции / проверки (Этап 2) ──────────────────────────────────
def list_contracts(sess: Session, limit: int = 200) -> List[Contract]:
    q = select(Contract).order_by(Contract.created_at.desc()).limit(limit)
    return list(sess.scalars(q).all())


def get_contract(sess: Session, contract_id: int) -> Optional[Contract]:
    return sess.get(Contract, contract_id)


def get_line_items(sess: Session, contract_id: int) -> List[LineItem]:
    q = select(LineItem).where(LineItem.contract_id == contract_id).order_by(LineItem.id)
    return list(sess.scalars(q).all())


def supplier_name(sess: Session, supplier_id: Optional[int]) -> Optional[str]:
    if not supplier_id:
        return None
    sup = sess.get(Supplier, supplier_id)
    return sup.name if sup else None


def find_analog_line_item(sess: Session, li: LineItem) -> Optional[LineItem]:
    """Лучший исторический аналог позиции (для сравнения характеристик).
    Точное совпадение (ntin ИЛИ manufacturer+model) → иначе семантика pgvector.
    Исключает саму позицию и её договор."""
    # 1) точное
    exact = []
    if li.ntin:
        exact.append(LineItem.ntin == li.ntin)
    if li.model and li.manufacturer:
        exact.append((LineItem.model.ilike(li.model)) & (LineItem.manufacturer.ilike(li.manufacturer)))
    if li.canonical_name:
        exact.append(LineItem.canonical_name == li.canonical_name)
    if exact:
        q = (select(LineItem)
             .where(or_(*exact), LineItem.id != li.id,
                    LineItem.contract_id != li.contract_id)
             .order_by(LineItem.purchase_date.desc().nullslast())
             .limit(1))
        found = sess.scalars(q).first()
        if found:
            return found
    # 2) семантика
    if li.embedding is not None:
        q = (select(LineItem)
             .where(LineItem.embedding.isnot(None), LineItem.id != li.id,
                    LineItem.contract_id != li.contract_id,
                    LineItem.embedding.cosine_distance(li.embedding) < _COSINE_MAX_DISTANCE)
             .order_by(LineItem.embedding.cosine_distance(li.embedding))
             .limit(1))
        return sess.scalars(q).first()
    return None


def save_check(sess: Session, *, contract_id: int, type: str, result: dict,
               risk_level: str, findings: dict) -> Check:
    chk = Check(contract_id=contract_id, type=type, result=result,
                risk_level=risk_level, findings=findings)
    sess.add(chk)
    sess.flush()
    return chk


def replace_checks(sess: Session, contract_id: int) -> None:
    """Удаляет прежние проверки договора перед перезапуском (идемпотентность)."""
    for chk in sess.scalars(select(Check).where(Check.contract_id == contract_id)).all():
        sess.delete(chk)


def get_checks(sess: Session, contract_id: int) -> List[Check]:
    q = select(Check).where(Check.contract_id == contract_id).order_by(Check.type)
    return list(sess.scalars(q).all())


def find_web_observations(sess: Session, *, canonical: str, embedding: Optional[List[float]],
                          date_from: Optional[date], date_to: Optional[date]
                          ) -> List[PriceObservation]:
    """История веб-поиска (price_search_history) по аналогам за период.

    Сначала точный ключ; если задан эмбеддинг — добавляем семантические соседи (pgvector).
    """
    seen_ids = set()
    out: List[PriceObservation] = []

    base = select(PriceSearchHistory).where(PriceSearchHistory.canonical_key == canonical)
    for c in _date_clause(PriceSearchHistory.found_at, date_from, date_to):
        base = base.where(c)
    for r in sess.scalars(base.limit(_ANALOG_LIMIT)).all():
        seen_ids.add(r.id)
        out.append(PriceObservation(unit_price=float(r.unit_price), obs_date=r.found_at,
                                    source=r.source_site or "web", url=r.source_url))

    if embedding is not None:
        sem = select(PriceSearchHistory).where(
            PriceSearchHistory.embedding.isnot(None),
            PriceSearchHistory.embedding.cosine_distance(embedding) < _COSINE_MAX_DISTANCE,
        )
        for c in _date_clause(PriceSearchHistory.found_at, date_from, date_to):
            sem = sem.where(c)
        sem = sem.order_by(PriceSearchHistory.embedding.cosine_distance(embedding)).limit(_ANALOG_LIMIT)
        for r in sess.scalars(sem).all():
            if r.id in seen_ids:
                continue
            seen_ids.add(r.id)
            out.append(PriceObservation(unit_price=float(r.unit_price), obs_date=r.found_at,
                                        source=r.source_site or "web", url=r.source_url))
    return out
