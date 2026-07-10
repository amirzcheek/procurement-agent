#!/bin/sh
# Точка входа контейнера: применяем миграции БД знаний, затем запускаем сервис.
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint] applying DB migrations (alembic upgrade head)..."
  alembic upgrade head
else
  echo "[entrypoint] DATABASE_URL не задан — база знаний выключена, миграции пропущены."
fi

exec uvicorn app:app --host 0.0.0.0 --port 8080
