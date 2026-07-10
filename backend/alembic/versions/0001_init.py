"""Инициализация базы знаний закупок: pgvector + все таблицы Этапа 1.

Revision ID: 0001_init
Revises:
Create Date: 2026-07-10
"""
from alembic import op

from db import Base
import models_db  # noqa: F401 — регистрирует таблицы в Base.metadata

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector должен существовать ДО создания таблиц с колонками vector(1024).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Создаём всю схему из ORM-моделей (совпадает с models_db.py).
    Base.metadata.create_all(bind=bind)
    # Векторные индексы для косинусного поиска аналогов (HNSW, pgvector 0.5+).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_line_items_embedding "
        "ON line_items USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_search_embedding "
        "ON price_search_history USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP INDEX IF EXISTS ix_price_search_embedding")
    op.execute("DROP INDEX IF EXISTS ix_line_items_embedding")
    Base.metadata.drop_all(bind=bind)
