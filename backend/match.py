"""Этап 6. Product matching — тот ли это товар.

Вариант 1: простой LLM-matching (БЕЗ Qdrant). LLM сравнивает наименование из КП с
title найденного товара и решает, тот ли он, с учётом бренда, модели, объёма/размера,
комплектации и единиц.

Точка расширения: интерфейс Matcher. Позже можно добавить QdrantMatcher
(эмбеддинги Ollama + векторный поиск) НЕ переписывая остальной пайплайн —
достаточно вернуть другой объект из get_matcher().
"""
from __future__ import annotations

import abc

from llm import chat_model
from logging_conf import get_logger
from models import Item, MatchDecision, PriceHit

log = get_logger("match")

SYSTEM = (
    "Ты сверяешь, один и тот же ли это товар. Сравни позицию из коммерческого предложения "
    "с найденным в магазине товаром. Учитывай: бренд, модель/артикул, объём/размер/вес, "
    "комплектацию, единицу измерения. Разные бренды или разные объёмы — это РАЗНЫЕ товары. "
    "Верни ТОЛЬКО JSON: "
    '{"is_match": bool, "confidence": number, "reason": str}. '
    "confidence — число 0..1, насколько уверенно это тот же товар. "
    "reason — короткое объяснение на русском."
)


class Matcher(abc.ABC):
    """Единый интерфейс матчинга. Реализации: LLMMatcher (сейчас), QdrantMatcher (Фаза 2)."""

    @abc.abstractmethod
    def match(self, item: Item, hit: PriceHit) -> MatchDecision:
        ...


class LLMMatcher(Matcher):
    def match(self, item: Item, hit: PriceHit) -> MatchDecision:
        found_title = hit.title or ""
        if not found_title.strip():
            return MatchDecision(is_match=False, confidence=0.0, reason="пустой заголовок найденного товара")
        user = (
            f"Товар из КП: {item.name}\n"
            f"Единица КП: {item.unit or 'не указана'}\n\n"
            f"Найденный товар: {found_title}\n"
            f"Источник: {hit.source or 'неизвестен'}\n\n"
            "Это один и тот же товар?"
        )
        try:
            decision = chat_model(SYSTEM, user, MatchDecision, retries=2, max_tokens=400)
        except Exception as e:
            log.warning("matcher LLM не дал валидный ответ (%s): считаем НЕ совпадением", e)
            return MatchDecision(is_match=False, confidence=0.0, reason=f"ошибка матчинга: {e}")
        # confidence в [0,1]
        decision.confidence = max(0.0, min(1.0, decision.confidence))
        log.info("match: «%s» ~ «%s» → %s (%.2f)",
                 item.name[:30], found_title[:30], decision.is_match, decision.confidence)
        return decision


# ── Точка расширения (Фаза 2) ────────────────────────────────────────────────
# class QdrantMatcher(Matcher):
#     """TODO: эмбеддинги через Ollama + векторный поиск в Qdrant.
#     Тот же интерфейс match(item, hit) -> MatchDecision, остальной пайплайн не меняется."""
#     def match(self, item: Item, hit: PriceHit) -> MatchDecision: ...


class MockMatcher(Matcher):
    """Для режима mock: считаем все найденные товары совпадением с высокой уверенностью,
    чтобы прогнать сравнение и флаги без обращения к LLM."""

    def match(self, item: Item, hit: PriceHit) -> MatchDecision:
        return MatchDecision(is_match=True, confidence=0.85, reason="mock: автоматическое совпадение")


def get_matcher() -> Matcher:
    # Здесь в Фазе 2 будет выбор по конфигу (llm | qdrant).
    from config import get_settings
    if (get_settings().search_provider or "mock").lower() == "mock":
        return MockMatcher()
    return LLMMatcher()
