"""Этап 2 (часть 3): индексы под аналитику и поиск (pg_trgm + btree).

Revision ID: 0004_analytics
Revises: 0003_risk
Create Date: 2026-07-10
"""
from alembic import op

revision = "0004_analytics"
down_revision = "0003_risk"
branch_labels = None
depends_on = None

_GIN = [
    ("ix_line_items_name_trgm", "line_items", "name"),
    ("ix_line_items_canon_trgm", "line_items", "canonical_name"),
    ("ix_contracts_number_trgm", "contracts", "number"),
    ("ix_suppliers_name_trgm", "suppliers", "name"),
]
_BTREE = [
    ("ix_contracts_supplier_id", "contracts", "supplier_id"),
    ("ix_contracts_risk_level", "contracts", "risk_level"),
    ("ix_contracts_date", "contracts", "date"),
    ("ix_contracts_status", "contracts", "status"),
    ("ix_line_items_contract_id", "line_items", "contract_id"),
]


def upgrade() -> None:
    # Триграммный поиск (full-text/fuzzy) по наименованиям и номерам.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, col in _GIN:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({col} gin_trgm_ops)")
    for name, table, col in _BTREE:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})")


def downgrade() -> None:
    for name, _t, _c in _GIN + _BTREE:
        op.execute(f"DROP INDEX IF EXISTS {name}")
