"""Тесты чистой логики проверок договора (conditions/quantity) — без БД/LLM."""
import checks


# ── conditions ───────────────────────────────────────────────────────────────
def test_conditions_all_present():
    r = checks.check_conditions({
        "warranty": "12 мес", "delivery_term": "30 дней", "payment_terms": "по факту",
        "conditions": {"penalties": True, "appendices": True, "tech_spec": True},
    })
    assert r["risk_level"] == "low"
    assert r["findings"]["missing_critical"] == []


def test_conditions_missing_critical_high():
    r = checks.check_conditions({
        "warranty": "", "delivery_term": "30 дней", "payment_terms": "по факту",
        "conditions": {"penalties": True, "appendices": True, "tech_spec": True},
    })
    assert r["risk_level"] == "high"
    assert "гарантия" in r["findings"]["missing_critical"]


def test_conditions_missing_extra_medium():
    r = checks.check_conditions({
        "warranty": "12 мес", "delivery_term": "30 дней", "payment_terms": "по факту",
        "conditions": {"penalties": False, "appendices": False, "tech_spec": True},
    })
    assert r["risk_level"] == "medium"
    assert "штрафные санкции" in r["findings"]["missing_extra"]


def test_conditions_none_conditions_obj():
    r = checks.check_conditions({"warranty": "12 мес", "delivery_term": "30 дн", "payment_terms": "аванс"})
    # critical есть, extra отсутствуют (conditions=None) → medium
    assert r["risk_level"] == "medium"


# ── quantity ─────────────────────────────────────────────────────────────────
def test_quantity_single_source():
    r = checks.check_quantity([{"label": "договор", "items": {"a": 10, "b": 5}}])
    assert r["risk_level"] == "low"
    assert r["result"]["sources"] == 1
    assert "note" in r["result"]


def test_quantity_match():
    groups = [
        {"label": "договор", "items": {"a": 10, "b": 5}},
        {"label": "КП", "items": {"a": 10, "b": 5}},
    ]
    r = checks.check_quantity(groups)
    assert r["risk_level"] == "low"
    assert r["findings"]["mismatches"] == []


def test_quantity_mismatch():
    groups = [
        {"label": "договор", "items": {"a": 10, "b": 5}},
        {"label": "КП", "items": {"a": 12, "b": 5}},
    ]
    r = checks.check_quantity(groups)
    assert r["risk_level"] == "medium"
    ms = r["findings"]["mismatches"]
    assert len(ms) == 1 and ms[0]["item"] == "a"
    assert ms[0]["per_source"] == {"договор": 10, "КП": 12}


# ── aggregate_risk ───────────────────────────────────────────────────────────
def _chk(type, risk, result=None, findings=None):
    return {"type": type, "risk_level": risk, "result": result or {}, "findings": findings or {}}


def test_aggregate_all_low():
    agg = checks.aggregate_risk([_chk("price", "low"), _chk("conditions", "low")])
    assert agg["risk_level"] == "low"
    assert agg["factors"] == []


def test_aggregate_high_wins():
    agg = checks.aggregate_risk([_chk("conditions", "medium"), _chk("price", "high")])
    assert agg["risk_level"] == "high"


def test_aggregate_medium():
    agg = checks.aggregate_risk([_chk("conditions", "medium"), _chk("price", "low")])
    assert agg["risk_level"] == "medium"


def test_factor_overprice():
    price = _chk("price", "high", result={"items": [
        {"item": "Бумага", "kp_unit_price": 3000, "combined_min": 1000, "combined_max": 2000, "risk_level": "high"},
    ]})
    agg = checks.aggregate_risk([price])
    facs = [f["factor"] for f in agg["factors"]]
    assert "завышение цены" in facs


def test_factor_underprice():
    price = _chk("price", "high", result={"items": [
        {"item": "X", "kp_unit_price": 500, "combined_min": 1000, "combined_max": 2000, "risk_level": "high"},
    ]})
    agg = checks.aggregate_risk([price])
    assert "занижение цены" in [f["factor"] for f in agg["factors"]]


def test_factor_conditions_and_quantity():
    cond = _chk("conditions", "high", findings={"missing_critical": ["гарантия"],
                                                "missing_extra": ["приложения"]})
    qty = _chk("quantity", "medium", findings={"mismatches": [{"item": "a", "per_source": {"д": 1, "кп": 2}}]})
    agg = checks.aggregate_risk([cond, qty])
    facs = [f["factor"] for f in agg["factors"]]
    assert "отсутствие обязательных условий" in facs
    assert "отсутствие обязательных документов" in facs
    assert "изменение количества" in facs
