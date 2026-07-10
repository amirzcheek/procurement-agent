"""Бэкофилл атрибутов позиций (Этап 2, Блок A).

Проходит line_items с пустым model, до-извлекает model/manufacturer/category/specs
из name через LLM, обновляет строки, пересчитывает canonical_name + embedding и
согласует canonical_key в price_history. Идемпотентный, запускается ВРУЧНУ (не при старте).

Запуск (из каталога backend):
    python -m scripts.backfill_models             # все строки без model
    python -m scripts.backfill_models --limit 50  # первые 50
    python -m scripts.backfill_models --dry-run    # без записи
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Позволяем запускать как `python scripts/backfill_models.py` и как модуль.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
import embeddings
import repository
from logging_conf import get_logger
from models_db import LineItem, PriceHistory
from parse_items import extract_attributes
from sqlalchemy import or_, select, update

log = get_logger("backfill")


def run(limit: int | None, dry_run: bool) -> int:
    if not db.is_enabled():
        log.error("DATABASE_URL не задан — бэкофилл невозможен.")
        return 0

    processed = 0
    updated = 0
    with db.session_scope() as sess:
        q = select(LineItem).where(or_(LineItem.model.is_(None), LineItem.model == ""))
        q = q.order_by(LineItem.id)
        if limit:
            q = q.limit(limit)
        rows = sess.scalars(q).all()
        log.info("к обработке строк без model: %d", len(rows))

        for li in rows:
            processed += 1
            attrs = extract_attributes(li.name)
            if not (attrs.model or attrs.manufacturer or attrs.category):
                log.info("[%d/%d] «%s» — атрибуты не выделены, пропуск",
                         processed, len(rows), li.name[:40])
                continue

            canonical = repository.canonical_key(li.name, attrs.model, attrs.manufacturer, li.ntin)
            emb = embeddings.embed(li.canonical_name or li.name)

            if dry_run:
                log.info("[dry] #%s model=%s manuf=%s cat=%s key=%s",
                         li.id, attrs.model, attrs.manufacturer, attrs.category, canonical)
                updated += 1
                continue

            old_canonical = li.canonical_name
            li.model = attrs.model
            li.manufacturer = attrs.manufacturer
            li.category = attrs.category or li.category
            if attrs.specs:
                li.specs = attrs.specs
            li.canonical_name = canonical
            if emb is not None:
                li.embedding = emb

            # Согласуем canonical_key в price_history для этого договора+позиции.
            sess.execute(
                update(PriceHistory)
                .where(PriceHistory.contract_id == li.contract_id,
                       PriceHistory.item_name == li.name)
                .values(canonical_key=canonical, model=attrs.model, manufacturer=attrs.manufacturer)
            )
            updated += 1
            log.info("[%d/%d] #%s обновлён: %s → model=%s manuf=%s",
                     processed, len(rows), li.id, (old_canonical or li.name)[:30],
                     attrs.model, attrs.manufacturer)

    log.info("ГОТОВО: обработано %d, обновлено %d%s", processed, updated,
             " (dry-run, без записи)" if dry_run else "")
    return updated


def main() -> None:
    ap = argparse.ArgumentParser(description="Бэкофилл model/manufacturer/category в line_items")
    ap.add_argument("--limit", type=int, default=None, help="максимум строк за запуск")
    ap.add_argument("--dry-run", action="store_true", help="не записывать, только показать")
    args = ap.parse_args()
    run(args.limit, args.dry_run)


if __name__ == "__main__":
    main()
