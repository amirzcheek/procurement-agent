"""Этап 2. Структурирование сырого текста таблицы в список Item через LLM + Pydantic.

LLM галлюцинируют — сырой вывод НЕ доверяем: всё валидируется через Pydantic,
retry до 2 раз (логика в llm.chat_model_list).
"""
from __future__ import annotations

from typing import List

from llm import chat_model, chat_model_list
from logging_conf import get_logger
from models import Item, ItemAttrs

log = get_logger("parse_items")

SYSTEM = (
    "Ты — парсер коммерческих предложений (КП) и договоров для закупок университета в Казахстане. "
    "Извлеки позиции товаров из сырого текста таблицы. "
    "Верни ТОЛЬКО JSON-массив объектов, без пояснений и без markdown. "
    "Каждый объект: "
    '{"name": str, "model": str|null, "manufacturer": str|null, "category": str|null, '
    '"specs": object|null, "qty": number|null, "unit": str|null, '
    '"unit_price": number|null, "total_price": number|null, "ntin": str|null}. '
    "Правила:\n"
    "- name — полное наименование товара как в документе;\n"
    "- ВАЖНО: ОТДЕЛЬНО выдели model — артикул/серию/модель производителя "
    "(например «PC16250», «S3221QSA», «OmniBook 7 16-ay0005ci», «CF259A»); "
    "если явной модели нет — null;\n"
    "- manufacturer — бренд/производитель (Dell, HP, Lenovo, Samsung, SvetoCopy…); если нет — null;\n"
    "- category — тип товара обобщённо (ноутбук, монитор, картридж, бумага, кресло…);\n"
    "- specs — объект ключевых характеристик из наименования "
    '(например {"процессор":"Core Ultra 5","озу":"16 ГБ","экран":"16\\""}); если нет — null;\n'
    "- qty — количество (число), unit — единица (шт, упак, пачка, кг, м…);\n"
    "- unit_price — цена за единицу, total_price — сумма по позиции;\n"
    "- числа без пробелов и валютных символов (1 250 000 → 1250000), запятая-десятичная → точка;\n"
    "- ntin — код NTIN/GTIN/KZTIN, если явно присутствует, иначе null;\n"
    "- НЕ выдумывай значения: чего нет в тексте — ставь null;\n"
    "- строки-итоги, заголовки, нумерацию столбцов в позиции НЕ включай."
)


def parse_items(raw_text: str) -> List[Item]:
    user = f"Сырой текст таблицы КП:\n\n{raw_text}\n\nВерни JSON-массив позиций."
    items = chat_model_list(SYSTEM, user, Item, retries=2, max_tokens=4096)
    # Отсекаем мусорные строки без наименования.
    items = [it for it in items if it.name and it.name.strip()]
    log.info("Извлечено позиций: %d", len(items))
    return items


_ATTR_SYSTEM = (
    "Из наименования товара выдели атрибуты. Верни ТОЛЬКО JSON без пояснений: "
    '{"model": str|null, "manufacturer": str|null, "category": str|null, "specs": object|null}. '
    "model — артикул/серия/модель производителя (PC16250, S3221QSA, CF259A, OmniBook 7 16-ay0005ci); "
    "manufacturer — бренд (Dell, HP, Lenovo, SvetoCopy…); category — тип товара обобщённо; "
    "specs — объект ключевых характеристик. Чего нет — null."
)


def extract_attributes(name: str) -> ItemAttrs:
    """До-извлечение model/manufacturer/category/specs из одного наименования (для бэкофилла).
    При ошибке — пустой ItemAttrs."""
    user = f"Наименование: {name}\n\nВыдели атрибуты."
    try:
        return chat_model(_ATTR_SYSTEM, user, ItemAttrs, retries=2, max_tokens=400)
    except Exception as e:
        log.warning("extract_attributes не удалось для «%s»: %s", name[:40], e)
        return ItemAttrs()
