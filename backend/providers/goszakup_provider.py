"""ЗАГЛУШКА (Фаза 2). goszakup.gov.kz — реальные закупочные цены через GraphQL.

Идея: запросить исторические цены контрактов по наименованию/NTIN и использовать как
эталон «справедливой» закупочной цены (надёжнее, чем розница маркетплейсов).

TODO (Фаза 2):
- endpoint: https://ows.goszakup.gov.kz/v3/graphql (нужен токен ЦЭФ);
- заголовок Authorization: Bearer <GOSZAKUP_TOKEN>;
- GraphQL-запрос по lots/contracts с фильтром по наименованию/НТИН/коду ЕНС ТРУ;
- агрегировать цены за единицу → ReferencePrice.
Сейчас провайдер ВЫКЛЮЧЕН и возвращает пустой список — пайплайн это переживает.
"""
from __future__ import annotations

from typing import List

from logging_conf import get_logger
from models import Item

from .base import ReferencePrice, ReferenceProvider

log = get_logger("goszakup")


class GoszakupProvider(ReferenceProvider):
    name = "goszakup.gov.kz"
    enabled = False  # включить в Фазе 2 при наличии токена ЦЭФ

    def lookup(self, item: Item) -> List[ReferencePrice]:
        if not self.enabled:
            return []
        # TODO: реальный GraphQL-запрос.
        log.info("goszakup: заглушка, реальный запрос не реализован")
        return []
