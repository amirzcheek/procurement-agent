"""Этап 2: доп. обязательные условия договора (contracts.conditions JSONB).

Revision ID: 0002_conditions
Revises: 0001_init
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_conditions"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("conditions", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "conditions")
