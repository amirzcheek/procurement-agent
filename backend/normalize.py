"""Этап 3. Нормализация позиции в короткий поисковый запрос (LLM).

Из «Бумага А4 80г/м2 SvetoCopy 500л» делаем короткий запрос: бренд + ключевые
характеристики + категория. Нормализуем единицу и фиксируем pack_multiplier —
он нужен на этапе сравнения, чтобы привести цену торговой единицы к единице КП.
"""
from __future__ import annotations

from llm import chat_model
from logging_conf import get_logger
from models import Item, NormalizedQuery

log = get_logger("normalize")

SYSTEM = (
    "Ты готовишь поисковый запрос для поиска товара на казахстанских маркетплейсах. "
    "По наименованию из КП сформируй КОРОТКИЙ запрос (бренд + ключевые характеристики + "
    "категория), которым товар реально ищут в Google. Убери лишние слова, артикулы-мусор, "
    "слова вроде «поставка», «оригинал». "
    "Также определи единицу и множитель приведения к единице КП.\n"
    "Верни ТОЛЬКО JSON: "
    '{"query": str, "normalized_unit": str|null, "pack_multiplier": number, "note": str|null}.\n'
    "pack_multiplier — сколько единиц КП содержится в типичной торговой единице товара. "
    "Если КП в штуках, а товар обычно продаётся упаковкой по 6 штук — multiplier=6. "
    "Если единица совпадает или неизвестно — multiplier=1. "
    "query пиши на русском."
)


def normalize_item(item: Item) -> NormalizedQuery:
    unit = item.unit or "не указана"
    user = (
        f"Наименование из КП: {item.name}\n"
        f"Единица КП: {unit}\n"
        f"Количество: {item.qty}\n\n"
        "Сформируй поисковый запрос и множитель."
    )
    try:
        nq = chat_model(SYSTEM, user, NormalizedQuery, retries=2, max_tokens=512)
    except Exception as e:
        log.warning("normalize LLM не дал валидный ответ (%s), fallback на исходное имя", e)
        nq = NormalizedQuery(query=item.name, normalized_unit=item.unit, pack_multiplier=1.0,
                             note="fallback: LLM-нормализация не удалась")
    if not nq.query.strip():
        nq.query = item.name
    if nq.pack_multiplier <= 0:
        nq.pack_multiplier = 1.0
    log.info("normalize: «%s» → «%s» (x%.3g)", item.name[:40], nq.query, nq.pack_multiplier)
    return nq
