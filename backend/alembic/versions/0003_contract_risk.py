"""Этап 2 (часть 2): агрегированный риск договора (contracts.risk_level, risk_factors).

Revision ID: 0003_risk
Revises: 0002_conditions
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_risk"
down_revision = "0002_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("risk_level", sa.String(length=10), nullable=True))
    op.add_column("contracts", sa.Column("risk_factors", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "risk_factors")
    op.drop_column("contracts", "risk_level")
