"""Общий клиент LLM (OpenAI-совместимый OVMS/Qwen3) + надёжный разбор JSON.

Все обращения к модели идут через этот модуль:
- enable_thinking=false (для Qwen3, чтобы не было <think>-блоков и было быстрее);
- извлечение JSON из «грязного» ответа;
- retry до N раз с валидацией через Pydantic.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from config import get_settings
from logging_conf import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = OpenAI(
            base_url=s.llm_base_url,
            api_key=s.llm_api_key or "not-needed",
            timeout=s.llm_timeout,
            max_retries=0,  # ретраи делаем сами, с валидацией
        )
    return _client


def _messages(system: str, user: str):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def chat(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """Один вызов чата. enable_thinking=false для Qwen3.

    Если локальный OVMS недоступен (сеть/таймаут) и настроен Gemini — автопереход
    на резервную модель Gemini (как в других агентах вуза).
    """
    from openai import APIConnectionError, APITimeoutError

    s = get_settings()
    try:
        resp = get_client().chat.completions.create(
            model=s.llm_model,
            messages=_messages(system, user),
            temperature=temperature,
            max_tokens=max_tokens,
            # Qwen3: отключаем reasoning-режим. Большинство OpenAI-совместимых
            # серверов (vLLM/OVMS) принимают это в extra_body.chat_template_kwargs.
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except (APIConnectionError, APITimeoutError) as e:
        import gemini

        fb = gemini.openai_client()
        if fb is None:
            raise
        log.warning("OVMS недоступен (%s) — переключаюсь на резервную Gemini (%s)", e, s.gemini_model)
        resp = fb.chat.completions.create(
            model=s.gemini_model,
            messages=_messages(system, user),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()


# ── Извлечение JSON из ответа модели ─────────────────────────────────────────
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _strip(text: str) -> str:
    text = _THINK_RE.sub("", text)
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def extract_json(text: str):
    """Достаёт первый валидный JSON-объект или массив из текста ответа."""
    cleaned = _strip(text)
    # Прямой парс
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Поиск по сбалансированным скобкам — берём самую раннюю открывающую.
    starts = [i for i, ch in enumerate(cleaned) if ch in "[{"]
    for start in starts:
        opener = cleaned[start]
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    raise ValueError("В ответе LLM не найден валидный JSON")


def chat_model(
    system: str,
    user: str,
    schema: Type[T],
    retries: int = 2,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> T:
    """Вызов LLM с обязательной Pydantic-валидацией и retry.

    schema — Pydantic-модель ожидаемого объекта. При ошибке парсинга/валидации
    повторяем (retries раз), добавляя в подсказку прошлую ошибку.
    """
    last_err: Optional[Exception] = None
    extra = ""
    for attempt in range(retries + 1):
        try:
            raw = chat(system, user + extra, temperature=temperature, max_tokens=max_tokens)
            data = extract_json(raw)
            return schema.model_validate(data)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            log.warning("LLM попытка %d/%d не прошла валидацию: %s", attempt + 1, retries + 1, e)
            extra = (
                f"\n\nПРЕДЫДУЩИЙ ОТВЕТ БЫЛ НЕВАЛИДЕН ({e}). "
                "Верни СТРОГО валидный JSON по требуемой схеме, без пояснений и без markdown."
            )
    raise ValueError(f"LLM не вернул валидный JSON после {retries + 1} попыток: {last_err}")


def chat_model_list(
    system: str,
    user: str,
    schema: Type[T],
    retries: int = 2,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> List[T]:
    """То же, но ожидаем JSON-массив объектов схемы."""
    last_err: Optional[Exception] = None
    extra = ""
    for attempt in range(retries + 1):
        try:
            raw = chat(system, user + extra, temperature=temperature, max_tokens=max_tokens)
            data = extract_json(raw)
            if isinstance(data, dict):
                # Иногда модель оборачивает массив в {"items": [...]}.
                for key in ("items", "data", "result", "positions"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
                else:
                    data = [data]
            if not isinstance(data, list):
                raise ValueError("Ожидался JSON-массив")
            return [schema.model_validate(x) for x in data]
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            log.warning("LLM(list) попытка %d/%d: %s", attempt + 1, retries + 1, e)
            extra = (
                f"\n\nПРЕДЫДУЩИЙ ОТВЕТ БЫЛ НЕВАЛИДЕН ({e}). "
                "Верни СТРОГО валидный JSON-МАССИВ объектов, без пояснений и без markdown."
            )
    raise ValueError(f"LLM не вернул валидный JSON-массив после {retries + 1} попыток: {last_err}")
