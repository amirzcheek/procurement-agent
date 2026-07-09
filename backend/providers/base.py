"""Единый интерфейс справочных провайдеров (Фаза 2).

Чтобы новые источники (goszakup, НКТ) подключались в каскад без правок пайплайна:
каждый возвращает список «эталонных» цен/идентификаторов по позиции, либо пустой
список, если источник недоступен/не настроен. Источник НИКОГДА не бросает наружу —
сбой одного провайдера не роняет анализ.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional

from models import Item


@dataclass
class ReferencePrice:
    price_per_unit: float
    currency: str = "KZT"
    source: str = ""
    title: str = ""
    url: Optional[str] = None
    confidence: float = 1.0
    meta: dict = field(default_factory=dict)


class ReferenceProvider(abc.ABC):
    """Справочный источник цен/идентификации товара."""

    name: str = "base"
    enabled: bool = False

    @abc.abstractmethod
    def lookup(self, item: Item) -> List[ReferencePrice]:
        ...
