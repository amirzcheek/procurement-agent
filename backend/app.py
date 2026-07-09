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
from typing import Dict
from urllib.parse import unquote

from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sse_starlette.sse import EventSourceResponse

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


@app.get("/auth/session")
def auth_session(request: Request):
    """Текущий пользователь для навбара (имя + флаг админа).

    Авторизацию делает платформа на уровне Caddy (forward_auth) и прокидывает
    данные пользователя заголовками (copy_headers). Здесь читаем их; если нет —
    возвращаем «гостя» (навбар просто не покажет имя/админку). Значения приходят
    URL-кодированными — раскодируем через unquote.
    """
    h = request.headers
    display_name = ""
    for name in settings.auth_user_headers.split(","):
        value = h.get(name.strip())
        if value:
            display_name = unquote(value)
            break

    email = ""
    for name in ("x-user-email", "x-forwarded-email", "remote-email"):
        value = h.get(name)
        if value:
            email = unquote(value)
            break

    groups = (h.get("remote-groups") or h.get("x-forwarded-groups") or "").lower()
    is_admin = h.get(settings.auth_admin_header, "").lower() in ("1", "true", "yes") or "admin" in groups
    return {"user": {"displayName": display_name, "email": email, "isAdmin": is_admin}}


@app.get("/config")
def config_public():
    return {
        "search_provider": settings.search_provider,
        "marketplaces": settings.marketplaces,
        "match_confidence_min": settings.match_confidence_min,
        "max_prices_per_item": settings.max_prices_per_item,
        "llm_model": settings.llm_model,
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
def export(job_id: str):
    report = JOBS.get(job_id)
    if report is None:
        return JSONResponse(
            {"error": "Отчёт не найден или ещё не готов. Сначала выполните анализ."},
            status_code=404,
        )
    data = report_mod.build_xlsx(report)
    safe_name = f"procurement_{job_id[:8]}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


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
