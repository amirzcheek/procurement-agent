# Образ агента «Анализатор закупок»: единый сервис — FastAPI отдаёт и API,
# и собранный React. Контекст сборки — корень репозитория.

# ── Стадия 1: сборка React-фронтенда ──
FROM node:20-slim AS frontend
WORKDIR /fe

# Префикс под-пути на портале и базовый адрес API (тот же префикс) — аргументы
# сборки (см. docker-compose.yml). Vite подхватывает VITE_*-переменные из окружения.
ARG VITE_BASE=/agents/procurement/
ARG VITE_API_BASE=/agents/procurement
ENV VITE_BASE=$VITE_BASE \
    VITE_API_BASE=$VITE_API_BASE

COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Стадия 2: бэкенд + браузер для crawl4ai + статика ──
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости Python (слой кешируется, пока requirements.txt не меняется).
COPY backend/requirements.txt backend/requirements-crawl.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# crawl4ai + Chromium ставятся ТОЛЬКО если нужен SEARCH_PROVIDER=serper.
# Для gemini/mock (по умолчанию) образ остаётся лёгким. Включить:
#   docker build --build-arg INSTALL_CRAWL=true ...
ARG INSTALL_CRAWL=false
RUN if [ "$INSTALL_CRAWL" = "true" ]; then \
        pip install --no-cache-dir -r requirements-crawl.txt && \
        python -m playwright install --with-deps chromium ; \
    fi

# Код бэкенда.
COPY backend/ ./

# Собранный фронтенд кладём в каталог, который отдаёт FastAPI.
COPY --from=frontend /fe/dist ./static
ENV FRONTEND_DIST=/app/static

EXPOSE 8080

# Точка входа: применяет миграции БД знаний (если DATABASE_URL задан), затем uvicorn.
# Наружу порт — только во внутреннюю сеть; доступ снаружи через nginx/Caddy под слагом.
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
