"""OCR: источник извлечения позиции (line_items.source_type: xlsx|pdf_text|ocr).

Revision ID: 0005_source
Revises: 0004_analytics
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_source"
down_revision = "0004_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_items", sa.Column("source_type", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("line_items", "source_type")
