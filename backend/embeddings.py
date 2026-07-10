"""Эмбеддинги для семантического поиска аналогов (Ollama, snowflake-arctic-embed2, 1024d).

Не бросает наружу: при недоступности Ollama возвращает None — тогда семантический поиск
просто пропускается, а точный поиск аналогов (model/manufacturer/ntin) продолжает работать.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from config import get_settings
from logging_conf import get_logger

log = get_logger("embeddings")


def is_enabled() -> bool:
    return bool(get_settings().embedding_url)


def embed(text: str) -> Optional[List[float]]:
    s = get_settings()
    if not s.embedding_url or not text or not text.strip():
        return None
    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                s.embedding_url,
                json={"model": s.embedding_model, "prompt": text.strip()},
            )
            r.raise_for_status()
            data = r.json()
        vec = data.get("embedding") or (data.get("embeddings") or [None])[0]
        if not vec:
            log.warning("Ollama вернул пустой эмбеддинг для «%s»", text[:40])
            return None
        if len(vec) != s.embedding_dim:
            log.warning("размерность эмбеддинга %d ≠ ожидаемой %d", len(vec), s.embedding_dim)
        return vec
    except Exception as e:
        log.warning("Ollama embeddings недоступен: %s", e)
        return None
