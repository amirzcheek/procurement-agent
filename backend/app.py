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

from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

import knowledge
import pipeline
import report as report_mod
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
async def knowledge_extract(file: UploadFile):
    """Извлечь позиции из договора/КП для подтверждения перед записью в базу знаний."""
    import extract as extract_mod
    import parse_items as parse_mod

    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл."}, status_code=400)
    try:
        raw = extract_mod.extract(file.filename or "upload", content)
        items = parse_mod.parse_items(raw)
    except extract_mod.ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.exception("knowledge_extract упал")
        return JSONResponse({"error": f"Не удалось разобрать файл: {e}"}, status_code=500)
    return {"filename": file.filename, "items": [it.model_dump() for it in items]}


@app.post("/knowledge/confirm")
def knowledge_confirm(req: ConfirmRequest, request: Request):
    """Подтверждение и запись договора/КП в базу знаний."""
    user = current_user(request)
    if not settings.database_url:
        return JSONResponse({"error": "База знаний выключена (DATABASE_URL не задан)."}, status_code=503)
    if not req.items:
        return JSONResponse({"error": "Нет позиций для сохранения."}, status_code=400)
    try:
        res = knowledge.ingest_contract(req.header, req.items, user["email"] or None)
    except Exception as e:
        log.exception("knowledge_confirm упал")
        return JSONResponse({"error": f"Ошибка сохранения: {e}"}, status_code=500)
    return {"ok": True, **res}


@app.post("/analysis/historical")
def analysis_historical(req: HistoricalRequest):
    """Исторический ценовой анализ по job за выбранный период (пересчёт при смене периода)."""
    return knowledge.historical_for_job(req.job_id, req.period_months, req.date_from, req.date_to)


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
