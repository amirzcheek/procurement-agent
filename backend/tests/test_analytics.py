"""Тесты чистых агрегаторов аналитики (без БД/LLM)."""
from datetime import datetime

import analytics


# ── over_range_flags ─────────────────────────────────────────────────────────
def test_over_range_flag_true():
    # поставщик 1 стабильно даёт максимум по 4 товарам, есть с чем сравнить → флаг
    rows = []
    for i in range(4):
        rows.append({"supplier_id": 1, "canonical_key": f"k{i}", "unit_price": 200})
        rows.append({"supplier_id": 2, "canonical_key": f"k{i}", "unit_price": 100})
    flags = analytics.over_range_flags(rows, min_items=3, threshold=0.3)
    assert flags[1]["flag"] is True
    assert flags[1]["share"] == 1.0
    assert flags[2]["flag"] is False


def test_over_range_min_items_guard():
    rows = [
        {"supplier_id": 1, "canonical_key": "k0", "unit_price": 200},
        {"supplier_id": 2, "canonical_key": "k0", "unit_price": 100},
    ]
    flags = analytics.over_range_flags(rows, min_items=3, threshold=0.3)
    assert flags[1]["flag"] is False  # всего 1 позиция < min_items


def test_over_range_single_price_not_flagged():
    # нет с чем сравнивать (одна цена по товару) → не «выше диапазона»
    rows = [{"supplier_id": 1, "canonical_key": f"k{i}", "unit_price": 100} for i in range(5)]
    flags = analytics.over_range_flags(rows)
    assert flags[1]["above"] == 0


# ── aggregate_deviations ─────────────────────────────────────────────────────
def test_aggregate_deviations_counts_sorted():
    lists = [
        [{"factor": "завышение цены"}, {"factor": "изменение количества"}],
        [{"factor": "завышение цены"}],
        [{"factor": "отсутствие обязательных условий"}],
    ]
    dev = analytics.aggregate_deviations(lists)
    assert dev[0] == {"factor": "завышение цены", "count": 2}
    assert {"factor": "изменение количества", "count": 1} in dev


# ── employee_stats ───────────────────────────────────────────────────────────
def test_employee_stats_counts_and_duration():
    rows = [
        {"user_email": "a@x", "action": "save_contract", "entity_id": "10",
         "created_at": datetime(2026, 1, 1, 10, 0)},
        {"user_email": "a@x", "action": "run_checks", "entity_id": "10",
         "created_at": datetime(2026, 1, 1, 12, 0)},
        {"user_email": "a@x", "action": "confirm_contract", "entity_id": "10",
         "created_at": datetime(2026, 1, 1, 14, 0)},
        {"user_email": "b@x", "action": "save_contract", "entity_id": "11",
         "created_at": datetime(2026, 1, 1, 9, 0)},
    ]
    stats = analytics.employee_stats(rows)
    a = next(s for s in stats if s["email"] == "a@x")
    assert a["uploads"] == 1 and a["checks"] == 1 and a["confirms"] == 1
    assert a["avg_hours_to_confirm"] == 4.0  # 10:00 → 14:00


def test_employee_stats_self_only():
    rows = [
        {"user_email": "a@x", "action": "save_contract", "entity_id": "1", "created_at": datetime(2026, 1, 1)},
        {"user_email": "b@x", "action": "save_contract", "entity_id": "2", "created_at": datetime(2026, 1, 1)},
    ]
    stats = analytics.employee_stats(rows, only_email="a@x")
    assert len(stats) == 1 and stats[0]["email"] == "a@x"
