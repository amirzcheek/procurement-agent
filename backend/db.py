"""Подключение к базе знаний закупок (PostgreSQL 16 + pgvector).

БД опциональна: если DATABASE_URL пуст — функции базы знаний выключены, агент работает
как раньше (только рыночный поиск). Это даёт локальную разработку без поднятого Postgres.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings
from logging_conf import get_logger

log = get_logger("db")


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: Optional[sessionmaker] = None


def is_enabled() -> bool:
    return bool(get_settings().database_url)


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        if not s.database_url:
            raise RuntimeError("DATABASE_URL не задан — база знаний выключена")
        _engine = create_engine(s.database_url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
        log.info("БД подключена: %s", s.database_url.rsplit("@", 1)[-1])
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Транзакционная сессия: commit при успехе, rollback при ошибке."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    sess = _SessionLocal()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
