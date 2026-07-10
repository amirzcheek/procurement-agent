"""FastAPI-приложение «Анализатор закупок».

Единый сервис (как другие агенты портала ai.knus.edu.kz): FastAPI отдаёт и API,
и собранный React под слагом /agents/procurement.

POST /analyze         — multipart upload → пайплайн, прогресс по позициям через SSE.
GET  /export/{job_id} — xlsx-отчёт по завершённому анализу.
GET  /config          — безопасная часть конфигурации для UI.
GET  /auth/session    — текущий пользователь (имя+админ) из заголовков forward_auth.
GET  /health          — проверка живости.
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

import analytics as analytics_mod
import checks as checks_mod
import conclusion as conclusion_mod
import db
import knowledge
import pipeline
import report as report_mod
import repository
from config import get_settings
from logging_conf import get_logger
from models import AnalysisReport

log = get_logger("app")
settings = get_settings()

app = FastAPI(
    title="Анализатор закупок",
    description="Procurement price-check для университета (Казахстан). Предварительный анализ.",
    version="0.1.0",
    # Префикс под-пути на портале (/agents/procurement). Локально — пусто.
    root_path=settings.root_path or "",
)

# CORS. За nginx/Caddy обычно не нужен (same-origin). Для локальной разработки
# добавляем Vite (5173), плюс всё из CORS_ORIGINS.
_origins = list(settings.cors_origins) + [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Завершённые отчёты в памяти процесса (для экспорта). Для прода — заменить на стор.
JOBS: Dict[str, AnalysisReport] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


def current_user(request: Request) -> dict:
    """Текущий пользователь из заголовков forward_auth платформы: имя, email, роль.

    Роль: admin (X-Is-Admin/группа admin или email в ADMIN_EMAILS) → manager
    (email в MANAGER_EMAILS) → procurer (по умолчанию).
    """
    h = request.headers
    display_name = ""
    for name in settings.auth_user_headers.split(","):
        value = h.get(name.strip())
        if value:
            display_name = unquote(value)
            break

    email = ""
    for name in settings.auth_email_headers.split(","):
        value = h.get(name.strip())
        if value:
            email = unquote(value).strip().lower()
            break

    groups = (h.get("remote-groups") or h.get("x-forwarded-groups") or "").lower()
    is_admin = (
        h.get(settings.auth_admin_header, "").lower() in ("1", "true", "yes")
        or "admin" in groups
        or (email and email in [e.lower() for e in settings.admin_emails])
    )
    if is_admin:
        role = "admin"
    elif email and email in [e.lower() for e in settings.manager_emails]:
        role = "manager"
    else:
        role = "procurer"
    return {"displayName": display_name, "email": email, "isAdmin": is_admin, "role": role}


def require_role(request: Request, allowed: tuple) -> dict:
    """Гейтинг по роли. Роль не из списка → 403. Запись/подтверждение — procurer/admin."""
    user = current_user(request)
    if user["role"] not in allowed:
        raise HTTPException(status_code=403,
                            detail=f"Действие недоступно для роли «{user['role']}».")
    return user


WRITERS = ("procurer", "admin")  # кто может загружать/подтверждать/запускать проверки
VIEWERS = ("manager", "admin")   # кто видит аналитику/поиск/dashboard


@app.get("/auth/session")
def auth_session(request: Request):
    """Текущий пользователь для навбара (имя, роль, флаг админа)."""
    return {"user": current_user(request)}


@app.get("/config")
def config_public():
    return {
        "search_provider": settings.search_provider,
        "marketplaces": settings.marketplaces,
        "match_confidence_min": settings.match_confidence_min,
        "max_prices_per_item": settings.max_prices_per_item,
        "llm_model": settings.llm_model,
        "db_enabled": bool(settings.database_url),
        "default_price_period_months": settings.default_price_period_months,
    }


def _sse(ev: dict) -> dict:
    return {"event": ev.get("type", "message"), "data": json.dumps(ev, ensure_ascii=False)}


def _friendly_error(e: Exception) -> str:
    """Короткое человекочитаемое сообщение вместо сырого SQL/трейсбека.
    Полная ошибка уходит в лог; пользователю — суть (первая строка первопричины)."""
    cause = getattr(e, "orig", None) or e   # у SQLAlchemy-ошибок исходная — в .orig
    msg = str(cause).split("\n")[0].strip()
    return msg[:300] if msg else e.__class__.__name__


@app.post("/analyze")
async def analyze(file: UploadFile):
    content = await file.read()
    filename = file.filename or "upload"
    job_id = uuid.uuid4().hex

    if not content:
        return JSONResponse({"error": "Пустой файл."}, status_code=400)

    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def worker():
            try:
                for ev in pipeline.analyze(job_id, filename, content):
                    if ev.get("type") == "done":
                        try:
                            JOBS[job_id] = AnalysisReport.model_validate(ev["report"])
                        except Exception as e:  # хранение не должно ронять стрим
                            log.warning("не удалось сохранить отчёт job=%s: %s", job_id, e)
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            except Exception as e:
                log.exception("worker упал")
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()

        # Сразу отдаём job_id, чтобы UI знал, что экспортировать.
        yield _sse({"type": "job", "job_id": job_id, "filename": filename})

        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield _sse(ev)

    # X-Accel-Buffering: no — просим nginx не буферизировать SSE (иначе события
    # придут пачкой в конце). Для Caddy буферизацию отключает flush_interval -1.
    return EventSourceResponse(
        event_gen(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/export/{job_id}")
def export(job_id: str, period_months: Optional[int] = None,
           date_from: Optional[str] = None, date_to: Optional[str] = None):
    report = JOBS.get(job_id)
    if report is None:
        return JSONResponse(
            {"error": "Отчёт не найден или ещё не готов. Сначала выполните анализ."},
            status_code=404,
        )
    # Исторический анализ за период добавляется листом, если база знаний включена.
    historical = None
    if settings.database_url:
        try:
            historical = knowledge.historical_for_job(job_id, period_months, date_from, date_to)
        except Exception as e:
            log.warning("export: исторический анализ не добавлен: %s", e)
    data = report_mod.build_xlsx(report, historical=historical)
    safe_name = f"procurement_{job_id[:8]}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ── База знаний закупок (Этап 1) ────────────────────────────────────────────
class HistoricalRequest(BaseModel):
    job_id: str
    period_months: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class ConfirmRequest(BaseModel):
    header: dict = Field(default_factory=dict)
    items: list = Field(default_factory=list)


@app.post("/knowledge/extract")
async def knowledge_extract(file: UploadFile, request: Request):
    """Извлечь позиции из договора/КП для подтверждения перед записью в базу знаний."""
    require_role(request, WRITERS)
    import extract as extract_mod
    import parse_items as parse_mod

    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл."}, status_code=400)
    try:
        res = extract_mod.extract(file.filename or "upload", content)
        if res.items is not None:  # OCR_MODE=structured — позиции уже готовы
            from models import Item as _Item
            items = [_Item.model_validate(x) for x in res.items if (x.get("name") or "").strip()]
        else:
            items = parse_mod.parse_items(res.text)
    except extract_mod.ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.exception("knowledge_extract упал")
        return JSONResponse({"error": f"Не удалось разобрать файл: {_friendly_error(e)}"}, status_code=500)
    return {"filename": file.filename, "items": [it.model_dump() for it in items],
            "source_type": res.source_type}


@app.post("/knowledge/confirm")
def knowledge_confirm(req: ConfirmRequest, request: Request):
    """Подтверждение и запись договора/КП в базу знаний."""
    user = require_role(request, WRITERS)
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена (DATABASE_URL не задан)."}, status_code=503)
    if not req.items:
        return JSONResponse({"error": "Нет позиций для сохранения."}, status_code=400)
    try:
        res = knowledge.ingest_contract(req.header, req.items, user["email"] or None)
    except Exception as e:
        log.exception("knowledge_confirm упал")
        return JSONResponse({"error": f"Не удалось сохранить: {_friendly_error(e)}"}, status_code=500)
    return {"ok": True, **res}


@app.post("/analysis/historical")
def analysis_historical(req: HistoricalRequest):
    """Исторический ценовой анализ по job за выбранный период (пересчёт при смене периода)."""
    return knowledge.historical_for_job(req.job_id, req.period_months, req.date_from, req.date_to)


# ── Договоры и проверки (Этап 2) ────────────────────────────────────────────
class CheckRequest(BaseModel):
    period_months: Optional[int] = None


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _line_item_dict(li) -> dict:
    return {
        "id": li.id, "name": li.name, "model": li.model, "manufacturer": li.manufacturer,
        "category": li.category, "specs": li.specs,
        "qty": float(li.qty) if li.qty is not None else None, "unit": li.unit,
        "unit_price": float(li.unit_price) if li.unit_price is not None else None,
        "ntin": li.ntin,
    }


def _check_dict(c) -> dict:
    return {"type": c.type, "risk_level": c.risk_level, "result": c.result,
            "findings": c.findings, "created_at": _iso(c.created_at)}


@app.get("/contracts")
def contracts_list():
    if not settings.database_url:
        return {"enabled": False, "contracts": []}
    out = []
    with db.session_scope() as sess:
        for c in repository.list_contracts(sess):
            items = repository.get_line_items(sess, c.id)
            out.append({
                "id": c.id, "number": c.number, "date": _iso(c.date),
                "supplier": repository.supplier_name(sess, c.supplier_id),
                "customer": c.customer, "status": c.status, "risk_level": c.risk_level,
                "items": len(items), "created_at": _iso(c.created_at),
            })
    return {"enabled": True, "contracts": out}


@app.get("/contracts/{contract_id}")
def contract_detail(contract_id: int):
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена."}, status_code=503)
    with db.session_scope() as sess:
        c = repository.get_contract(sess, contract_id)
        if c is None:
            return JSONResponse({"error": "Договор не найден."}, status_code=404)
        return {
            "id": c.id, "number": c.number, "date": _iso(c.date),
            "supplier": repository.supplier_name(sess, c.supplier_id), "customer": c.customer,
            "funding_source": c.funding_source, "warranty": c.warranty,
            "delivery_term": c.delivery_term, "payment_terms": c.payment_terms,
            "conditions": c.conditions, "status": c.status,
            "risk_level": c.risk_level,
            "risk_factors": (c.risk_factors or {}).get("factors", []),
            "items": [_line_item_dict(li) for li in repository.get_line_items(sess, contract_id)],
            "checks": [_check_dict(ch) for ch in repository.get_checks(sess, contract_id)],
        }


@app.post("/contracts/{contract_id}/check")
def contract_check(contract_id: int, req: CheckRequest, request: Request):
    """Запуск 4 проверок договора → запись в checks + агрегированный риск → возврат."""
    require_role(request, WRITERS)
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена."}, status_code=503)
    try:
        with db.session_scope() as sess:
            c = repository.get_contract(sess, contract_id)
            if c is None:
                return JSONResponse({"error": "Договор не найден."}, status_code=404)
            user = current_user(request)
            result = checks_mod.run_all_checks(sess, c, req.period_months, user["email"] or None)
        return {"ok": True, "contract_id": contract_id, **result}
    except Exception as e:
        log.exception("contract_check упал")
        return JSONResponse({"error": f"Ошибка проверки: {_friendly_error(e)}"}, status_code=500)


@app.post("/contracts/{contract_id}/confirm")
def contract_confirm(contract_id: int, request: Request):
    """Подтверждение заключения закупщиком: статус draft → checked, запись в audit_log."""
    user = require_role(request, WRITERS)
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена."}, status_code=503)
    with db.session_scope() as sess:
        c = repository.get_contract(sess, contract_id)
        if c is None:
            return JSONResponse({"error": "Договор не найден."}, status_code=404)
        c.status = "checked"
        repository.audit(sess, user["email"] or None, "confirm_contract", "contract", contract_id,
                         {"risk_level": c.risk_level})
    return {"ok": True, "status": "checked"}


@app.get("/contracts/{contract_id}/conclusion")
def contract_conclusion(contract_id: int, period_months: Optional[int] = None):
    """Полное заключение по договору за выбранный период (пересчёт при смене периода)."""
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена."}, status_code=503)
    with db.session_scope() as sess:
        c = repository.get_contract(sess, contract_id)
        if c is None:
            return JSONResponse({"error": "Договор не найден."}, status_code=404)
        return conclusion_mod.build_conclusion(sess, c, period_months)


@app.get("/contracts/{contract_id}/export")
def contract_export(contract_id: int, period_months: Optional[int] = None):
    """Заключение по договору в xlsx (листы «Заключение», «Проверки», «История цен»)."""
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена."}, status_code=503)
    with db.session_scope() as sess:
        c = repository.get_contract(sess, contract_id)
        if c is None:
            return JSONResponse({"error": "Договор не найден."}, status_code=404)
        conc = conclusion_mod.build_conclusion(sess, c, period_months)
    data = report_mod.build_conclusion_xlsx(conc)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="contract_{contract_id}.xlsx"'},
    )


# ── Аналитика / dashboard / поиск / аудит (Этап 2, часть 3) ─────────────────
def _period_from(period_months: Optional[int]):
    df, _dt, _label = knowledge.resolve_period(period_months, None, None)
    return df


def _db_guard():
    return None if settings.database_url else JSONResponse(
        {"error": "База знаний выключена."}, status_code=503)


@app.get("/analytics/dashboard")
def analytics_dashboard(request: Request, period_months: Optional[int] = None):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    with db.session_scope() as sess:
        return analytics_mod.dashboard(sess, _period_from(period_months))


@app.get("/analytics/suppliers")
def analytics_suppliers(request: Request, period_months: Optional[int] = None):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    with db.session_scope() as sess:
        return {"suppliers": analytics_mod.suppliers_overview(sess, _period_from(period_months))}


@app.get("/analytics/suppliers/{supplier_id}")
def analytics_supplier_card(supplier_id: int, request: Request):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    with db.session_scope() as sess:
        return analytics_mod.supplier_card(sess, supplier_id)


@app.get("/analytics/offers")
def analytics_offers(request: Request, period_months: Optional[int] = None):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    with db.session_scope() as sess:
        return {"items": analytics_mod.items_analytics(sess, _period_from(period_months))}


@app.get("/analytics/item-history")
def analytics_item_history(canonical: str, request: Request):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    with db.session_scope() as sess:
        return {"series": analytics_mod.item_history(sess, canonical)}


@app.get("/analytics/employees")
def analytics_employees(request: Request, period_months: Optional[int] = None):
    # manager/admin — все; procurer — только своя статистика.
    user = current_user(request)
    if user["role"] not in ("manager", "admin", "procurer"):
        raise HTTPException(status_code=403, detail="Недоступно.")
    if (g := _db_guard()):
        return g
    only = user["email"] if user["role"] == "procurer" else None
    with db.session_scope() as sess:
        return {"employees": analytics_mod.employees(sess, _period_from(period_months), only_email=only),
                "self_only": only is not None}


@app.get("/search")
def search_endpoint(request: Request, number: Optional[str] = None, supplier: Optional[str] = None,
                    product: Optional[str] = None, model: Optional[str] = None,
                    manufacturer: Optional[str] = None, category: Optional[str] = None,
                    date_from: Optional[str] = None, date_to: Optional[str] = None,
                    price_min: Optional[float] = None, price_max: Optional[float] = None,
                    risk_level: Optional[str] = None, employee: Optional[str] = None):
    require_role(request, VIEWERS)
    if (g := _db_guard()):
        return g
    from datetime import date as _date
    df = _date.fromisoformat(date_from) if date_from else None
    dt = _date.fromisoformat(date_to) if date_to else None
    with db.session_scope() as sess:
        return {"results": analytics_mod.search(
            sess, number=number, supplier=supplier, product=product, model=model,
            manufacturer=manufacturer, category=category, date_from=df, date_to=dt,
            price_min=price_min, price_max=price_max, risk_level=risk_level, employee=employee)}


@app.get("/audit")
def audit_endpoint(request: Request, user: Optional[str] = None, action: Optional[str] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None):
    require_role(request, ("admin",))  # журнал аудита — только admin
    if (g := _db_guard()):
        return g
    from datetime import date as _date
    df = _date.fromisoformat(date_from) if date_from else None
    dt = _date.fromisoformat(date_to) if date_to else None
    with db.session_scope() as sess:
        return {"records": analytics_mod.audit_query(sess, user=user, action=action,
                                                     date_from=df, date_to=dt)}


# ── Раздача собранного веб-интерфейса (React) ───────────────────────────────
# Когда агент развёрнут единым сервисом под /agents/procurement/, FastAPI отдаёт
# и API (выше), и статику собранного React. Каталог задаётся FRONTEND_DIST
# (по умолчанию backend/static, куда кладётся dist при сборке образа). Нет
# каталога — сервис работает как чистый API (локальная разработка через Vite).
#
# ВАЖНО: этот блок ПОСЛЕ объявления API-маршрутов — /health, /analyze, /export,
# /config, /auth/session (и /docs, /openapi.json) имеют приоритет, а catch-all
# отдаёт SPA только на остальные GET-запросы.
_dist_env = settings.frontend_dist or str(Path(__file__).parent / "static")
FRONTEND_DIST = Path(_dist_env)

if FRONTEND_DIST.is_dir():
    _index_file = FRONTEND_DIST / "index.html"
    _dist_root = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Любой прочий GET → реальный файл из сборки (js/css/favicon),
        иначе index.html. Есть защита от выхода за пределы каталога сборки."""
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and _dist_root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_index_file)
