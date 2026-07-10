"""Аналитика, dashboard, поиск, аудит (Этап 2, часть 3) — ТОЛЬКО SQL-агрегаты, без LLM.

Тяжёлая агрегация — в SQL; чистые хелперы (over_range_flags, aggregate_deviations,
employee_stats) вынесены отдельно и покрыты тестами (без БД).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import String, and_, cast, func, or_, select

from logging_conf import get_logger
from models_db import AuditLog, Check, Contract, LineItem, PriceHistory, PriceSearchHistory, Supplier

log = get_logger("analytics")


# ── ЧИСТЫЕ ХЕЛПЕРЫ (тестируются без БД) ──────────────────────────────────────
def over_range_flags(rows: List[dict], min_items: int = 3, threshold: float = 0.30) -> Dict[int, dict]:
    """Доля позиций поставщика, вышедших за исторический max по своему товару.

    rows: [{supplier_id, canonical_key, unit_price}]. «Выше диапазона» = цена поставщика
    строго максимальная по этому товару И по товару есть ≥2 разные цены (есть с чем сравнить).
    Флаг, если доля > threshold и позиций ≥ min_items.
    """
    by_key: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        if r.get("unit_price") is None or not r.get("canonical_key"):
            continue
        by_key[r["canonical_key"]].append(r)

    key_max = {k: max(x["unit_price"] for x in v) for k, v in by_key.items()}
    key_distinct = {k: len({x["unit_price"] for x in v}) for k, v in by_key.items()}

    per_supplier: Dict[int, dict] = defaultdict(lambda: {"items": 0, "above": 0})
    for r in rows:
        sid = r.get("supplier_id")
        k = r.get("canonical_key")
        if sid is None or r.get("unit_price") is None or not k:
            continue
        st = per_supplier[sid]
        st["items"] += 1
        if key_distinct.get(k, 0) >= 2 and r["unit_price"] >= key_max[k]:
            st["above"] += 1

    for sid, st in per_supplier.items():
        st["share"] = round(st["above"] / st["items"], 3) if st["items"] else 0.0
        st["flag"] = st["items"] >= min_items and st["share"] > threshold
    return dict(per_supplier)


def aggregate_deviations(factors_lists: List[list]) -> List[dict]:
    """Считает частоту факторов риска по всем договорам. Вход — список списков факторов."""
    counts: Dict[str, int] = defaultdict(int)
    for factors in factors_lists:
        for f in factors or []:
            name = (f or {}).get("factor")
            if name:
                counts[name] += 1
    return sorted(({"factor": k, "count": v} for k, v in counts.items()),
                  key=lambda x: -x["count"])


def employee_stats(rows: List[dict], only_email: Optional[str] = None) -> List[dict]:
    """Статистика по сотрудникам из audit_log.

    rows: [{user_email, action, entity_id, created_at(datetime|iso)}]. Считает:
    обработано закупок (uploads), запусков проверок, подтверждений, среднее время
    от загрузки до подтверждения (сроки проверки, в часах).
    """
    from datetime import datetime

    def _dt(v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return None

    per: Dict[str, dict] = defaultdict(lambda: {"uploads": 0, "checks": 0, "confirms": 0})
    # для сроков: время загрузки и подтверждения по договору
    upload_at: Dict[str, object] = {}
    durations: Dict[str, list] = defaultdict(list)

    for r in rows:
        email = r.get("user_email") or "—"
        action = r.get("action")
        st = per[email]
        if action == "save_contract":
            st["uploads"] += 1
            if r.get("entity_id"):
                upload_at[r["entity_id"]] = _dt(r.get("created_at"))
        elif action == "run_checks":
            st["checks"] += 1
        elif action == "confirm_contract":
            st["confirms"] += 1
            eid = r.get("entity_id")
            u = upload_at.get(eid)
            c = _dt(r.get("created_at"))
            if u and c and c >= u:
                durations[email].append((c - u).total_seconds() / 3600.0)

    out = []
    for email, st in per.items():
        if only_email and email != only_email:
            continue
        durs = durations.get(email, [])
        st2 = dict(st)
        st2["email"] = email
        st2["avg_hours_to_confirm"] = round(sum(durs) / len(durs), 1) if durs else None
        out.append(st2)
    return sorted(out, key=lambda x: -(x["uploads"] + x["checks"]))


# ── SQL-АГРЕГАТЫ ─────────────────────────────────────────────────────────────
def _sname(sess, cache: dict, sid: Optional[int]) -> Optional[str]:
    if sid is None:
        return None
    if sid not in cache:
        s = sess.get(Supplier, sid)
        cache[sid] = s.name if s else None
    return cache[sid]


def suppliers_overview(sess, date_from: Optional[date] = None) -> List[dict]:
    q = (select(PriceHistory.supplier_id,
                func.count().label("items"),
                func.min(PriceHistory.unit_price).label("min_price"),
                func.max(PriceHistory.unit_price).label("max_price"))
         .where(PriceHistory.supplier_id.isnot(None)))
    if date_from:
        q = q.where(PriceHistory.purchase_date >= date_from)
    q = q.group_by(PriceHistory.supplier_id)
    agg = {r.supplier_id: r for r in sess.execute(q)}

    cq = (select(Contract.supplier_id, func.count())
          .where(Contract.supplier_id.isnot(None)).group_by(Contract.supplier_id))
    ccount = {sid: n for sid, n in sess.execute(cq)}

    rows = [{"supplier_id": s, "canonical_key": k, "unit_price": float(p)}
            for s, k, p in sess.execute(
                select(PriceHistory.supplier_id, PriceHistory.canonical_key, PriceHistory.unit_price)
                .where(PriceHistory.supplier_id.isnot(None)))]
    flags = over_range_flags(rows)

    cache: dict = {}
    out = []
    for sid, a in agg.items():
        f = flags.get(sid, {})
        out.append({
            "id": sid, "name": _sname(sess, cache, sid),
            "contracts": ccount.get(sid, 0), "items": a.items,
            "min_price": float(a.min_price) if a.min_price is not None else None,
            "max_price": float(a.max_price) if a.max_price is not None else None,
            "over_share": f.get("share", 0.0), "flag": bool(f.get("flag")),
        })
    return sorted(out, key=lambda x: -x["contracts"])


def supplier_card(sess, supplier_id: int) -> dict:
    sup = sess.get(Supplier, supplier_id)
    if sup is None:
        return {}
    series = [{"date": d.isoformat() if d else None, "price": float(p), "item": name}
              for p, d, name in sess.execute(
                  select(PriceHistory.unit_price, PriceHistory.purchase_date, PriceHistory.item_name)
                  .where(PriceHistory.supplier_id == supplier_id)
                  .order_by(PriceHistory.purchase_date))]
    products = [{"canonical": k, "count": n} for k, n in sess.execute(
        select(PriceHistory.canonical_key, func.count())
        .where(PriceHistory.supplier_id == supplier_id)
        .group_by(PriceHistory.canonical_key))]
    contracts = [{"id": c.id, "number": c.number, "date": c.date.isoformat() if c.date else None,
                  "risk_level": c.risk_level, "status": c.status}
                 for c in sess.scalars(select(Contract).where(Contract.supplier_id == supplier_id)
                                       .order_by(Contract.date.desc().nullslast())).all()]
    return {"id": sup.id, "name": sup.name, "bin_iin": sup.bin_iin,
            "price_series": series, "products": products, "contracts": contracts}


def items_analytics(sess, date_from: Optional[date] = None) -> List[dict]:
    """По позициям: цена vs исторический max по товару → в диапазоне / вне."""
    key_max = {k: float(m) for k, m in sess.execute(
        select(PriceHistory.canonical_key, func.max(PriceHistory.unit_price))
        .group_by(PriceHistory.canonical_key))}
    q = select(LineItem, Contract).join(Contract, LineItem.contract_id == Contract.id)
    if date_from:
        q = q.where(LineItem.purchase_date >= date_from)
    q = q.order_by(LineItem.purchase_date.desc().nullslast()).limit(500)
    cache: dict = {}
    out = []
    for li, c in sess.execute(q):
        gmax = key_max.get(li.canonical_name)
        price = float(li.unit_price) if li.unit_price is not None else None
        in_range = None
        if price is not None and gmax is not None:
            in_range = price <= gmax
        out.append({
            "contract_id": c.id, "contract_number": c.number,
            "supplier": _sname(sess, cache, c.supplier_id),
            "name": li.name, "model": li.model, "category": li.category,
            "price": price, "date": li.purchase_date.isoformat() if li.purchase_date else None,
            "hist_max": gmax, "in_range": in_range, "canonical": li.canonical_name,
        })
    return out


def item_history(sess, canonical: str) -> List[dict]:
    """Динамика всех цен по товару во времени (внутренняя + веб)."""
    series = []
    for p, d in sess.execute(
            select(PriceHistory.unit_price, PriceHistory.purchase_date)
            .where(PriceHistory.canonical_key == canonical)):
        series.append({"date": d.isoformat() if d else None, "price": float(p), "source": "внутренняя"})
    for p, d, site in sess.execute(
            select(PriceSearchHistory.unit_price, PriceSearchHistory.found_at, PriceSearchHistory.source_site)
            .where(PriceSearchHistory.canonical_key == canonical)):
        series.append({"date": d.isoformat() if d else None, "price": float(p), "source": site or "web"})
    return sorted([s for s in series if s["date"]], key=lambda x: x["date"])


def _month(col):
    return func.to_char(func.date_trunc("month", col), "YYYY-MM")


def dashboard(sess, date_from: Optional[date] = None) -> dict:
    cfilter = [Contract.date >= date_from] if date_from else []

    checked = sess.scalar(select(func.count()).select_from(Contract)
                          .where(Contract.status == "checked", *cfilter)) or 0
    high = sess.scalar(select(func.count()).select_from(Contract)
                       .where(Contract.risk_level == "high", *cfilter)) or 0
    total = sess.scalar(select(func.count()).select_from(Contract).where(*cfilter)) or 0

    factors = [rf.get("factors", []) for (rf,) in sess.execute(
        select(Contract.risk_factors).where(Contract.risk_factors.isnot(None), *cfilter))]
    deviations = aggregate_deviations(factors)

    pfilter = [PriceHistory.purchase_date >= date_from] if date_from else []
    price_min = sess.scalar(select(func.min(PriceHistory.unit_price)).where(*pfilter))
    price_max = sess.scalar(select(func.max(PriceHistory.unit_price)).where(*pfilter))

    purchases = [{"month": m, "count": n} for m, n in sess.execute(
        select(_month(Contract.date), func.count()).where(Contract.date.isnot(None), *cfilter)
        .group_by(_month(Contract.date)).order_by(_month(Contract.date)))]

    dynamics = [{"month": m, "min": float(mn), "max": float(mx)} for m, mn, mx in sess.execute(
        select(_month(PriceHistory.purchase_date), func.min(PriceHistory.unit_price),
               func.max(PriceHistory.unit_price))
        .where(PriceHistory.purchase_date.isnot(None), *pfilter)
        .group_by(_month(PriceHistory.purchase_date)).order_by(_month(PriceHistory.purchase_date)))]

    by_category = [{"category": cat or "—", "count": n,
                    "min": float(mn) if mn is not None else None,
                    "max": float(mx) if mx is not None else None}
                   for cat, n, mn, mx in sess.execute(
                       select(LineItem.category, func.count(), func.min(LineItem.unit_price),
                              func.max(LineItem.unit_price))
                       .group_by(LineItem.category).order_by(func.count().desc()).limit(15))]

    by_department = [{"customer": cust or "—", "count": n} for cust, n in sess.execute(
        select(Contract.customer, func.count()).where(*cfilter)
        .group_by(Contract.customer).order_by(func.count().desc()).limit(15))]

    suppliers = suppliers_overview(sess, date_from)[:10]

    return {
        "contracts_total": total, "contracts_checked": checked, "high_risk": high,
        "deviations": deviations, "price_min": float(price_min) if price_min is not None else None,
        "price_max": float(price_max) if price_max is not None else None,
        "purchases_by_month": purchases, "price_dynamics": dynamics,
        "by_category": by_category, "by_department": by_department,
        "supplier_rating": suppliers,
    }


def employees(sess, date_from: Optional[date] = None, only_email: Optional[str] = None) -> List[dict]:
    q = select(AuditLog.user_email, AuditLog.action, AuditLog.entity_id, AuditLog.created_at)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    rows = [{"user_email": e, "action": a, "entity_id": eid, "created_at": ts}
            for e, a, eid, ts in sess.execute(q)]
    return employee_stats(rows, only_email=only_email)


def search(sess, *, number=None, supplier=None, product=None, model=None, manufacturer=None,
           category=None, date_from=None, date_to=None, price_min=None, price_max=None,
           risk_level=None, employee=None, limit=200) -> List[dict]:
    """Комбинируемый поиск договоров (trigram ILIKE по тексту)."""
    q = select(Contract).distinct()
    need_items = any([product, model, manufacturer, category, price_min, price_max])
    if need_items:
        q = q.join(LineItem, LineItem.contract_id == Contract.id)
    if supplier:
        q = q.join(Supplier, Contract.supplier_id == Supplier.id)

    conds = []
    if number:
        conds.append(Contract.number.ilike(f"%{number}%"))
    if supplier:
        conds.append(Supplier.name.ilike(f"%{supplier}%"))
    if product:
        conds.append(or_(LineItem.name.ilike(f"%{product}%"),
                         LineItem.canonical_name.ilike(f"%{product}%")))
    if model:
        conds.append(LineItem.model.ilike(f"%{model}%"))
    if manufacturer:
        conds.append(LineItem.manufacturer.ilike(f"%{manufacturer}%"))
    if category:
        conds.append(LineItem.category.ilike(f"%{category}%"))
    if date_from:
        conds.append(Contract.date >= date_from)
    if date_to:
        conds.append(Contract.date <= date_to)
    if price_min is not None:
        conds.append(LineItem.unit_price >= price_min)
    if price_max is not None:
        conds.append(LineItem.unit_price <= price_max)
    if risk_level:
        conds.append(Contract.risk_level == risk_level)
    if employee:
        conds.append(Contract.created_by.ilike(f"%{employee}%"))
    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(Contract.date.desc().nullslast()).limit(limit)

    cache: dict = {}
    out = []
    for c in sess.scalars(q).all():
        out.append({"id": c.id, "number": c.number,
                    "date": c.date.isoformat() if c.date else None,
                    "supplier": _sname(sess, cache, c.supplier_id), "customer": c.customer,
                    "risk_level": c.risk_level, "status": c.status})
    return out


def audit_query(sess, *, user=None, action=None, date_from=None, date_to=None, limit=300) -> List[dict]:
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user:
        q = q.where(AuditLog.user_email.ilike(f"%{user}%"))
    if action:
        q = q.where(AuditLog.action == action)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    q = q.limit(limit)
    return [{"id": a.id, "user_email": a.user_email, "action": a.action,
             "entity_type": a.entity_type, "entity_id": a.entity_id, "details": a.details,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in sess.scalars(q).all()]
