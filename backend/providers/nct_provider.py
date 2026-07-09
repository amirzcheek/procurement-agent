"""ЗАГЛУШКА (Фаза 2). НКТ (Национальный каталог товаров) Open API — идентификация по NTIN/GTIN.

Идея: по коду NTIN/GTIN из КП получить эталонное наименование, характеристики и единицу,
что резко повышает точность матчинга (сверяем не строки, а идентификаторы).

TODO (Фаза 2):
- Open API НКТ (ucp/nct), идентификация товара по NTIN/GTIN;
- вернуть эталонное наименование/атрибуты → использовать в match.py как «якорь».
Сейчас ВЫКЛЮЧЕН, возвращает пустой список — каскад источников это переживает.
"""
from __future__ import annotations

from typing import List, Optional

from logging_conf import get_logger
from models import Item

from .base import ReferencePrice, ReferenceProvider

log = get_logger("nct")


class NctProvider(ReferenceProvider):
    name = "НКТ Open API"
    enabled = False  # включить в Фазе 2

    def lookup(self, item: Item) -> List[ReferencePrice]:
        if not self.enabled:
            return []
        return []

    def identify(self, ntin: Optional[str]) -> Optional[dict]:
        """TODO: вернуть эталонные атрибуты товара по NTIN/GTIN."""
        if not self.enabled or not ntin:
            return None
        log.info("НКТ: заглушка идентификации по NTIN=%s", ntin)
        return None
