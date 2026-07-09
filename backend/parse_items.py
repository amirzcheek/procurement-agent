"""Этап 2. Структурирование сырого текста таблицы в список Item через LLM + Pydantic.

LLM галлюцинируют — сырой вывод НЕ доверяем: всё валидируется через Pydantic,
retry до 2 раз (логика в llm.chat_model_list).
"""
from __future__ import annotations

from typing import List

from llm import chat_model_list
from logging_conf import get_logger
from models import Item

log = get_logger("parse_items")

SYSTEM = (
    "Ты — парсер коммерческих предложений (КП) для закупок университета в Казахстане. "
    "Извлеки позиции товаров из сырого текста таблицы. "
    "Верни ТОЛЬКО JSON-массив объектов, без пояснений и без markdown. "
    "Каждый объект: "
    '{"name": str, "qty": number|null, "unit": str|null, '
    '"unit_price": number|null, "total_price": number|null, "ntin": str|null}. '
    "Правила:\n"
    "- name — полное наименование товара (бренд, модель, характеристики);\n"
    "- qty — количество (число), unit — единица измерения (шт, упак, пачка, кг, м...);\n"
    "- unit_price — цена за единицу, total_price — сумма по позиции;\n"
    "- числа без пробелов и валютных символов (1 250 000 → 1250000), запятая-десятичная → точка;\n"
    "- ntin — код NTIN/GTIN/KZTIN, если он явно присутствует в тексте, иначе null;\n"
    "- НЕ выдумывай значения: если поля нет в тексте — ставь null;\n"
    "- строки-итоги, заголовки, нумерацию столбцов в позиции НЕ включай."
)


def parse_items(raw_text: str) -> List[Item]:
    user = f"Сырой текст таблицы КП:\n\n{raw_text}\n\nВерни JSON-массив позиций."
    items = chat_model_list(SYSTEM, user, Item, retries=2, max_tokens=4096)
    # Отсекаем мусорные строки без наименования.
    items = [it for it in items if it.name and it.name.strip()]
    log.info("Извлечено позиций: %d", len(items))
    return items
