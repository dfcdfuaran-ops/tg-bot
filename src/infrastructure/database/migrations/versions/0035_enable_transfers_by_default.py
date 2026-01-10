"""enable_transfers_by_default

Revision ID: 0035
Revises: 0034
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обновляем существующие записи в таблице settings
    # Устанавливаем transfers.enabled = true по умолчанию
    op.execute("""
        UPDATE settings
        SET features = jsonb_set(
            COALESCE(features::jsonb, '{}'::jsonb),
            '{transfers,enabled}',
            'true'::jsonb,
            true
        )
        WHERE features IS NOT NULL
    """)


def downgrade() -> None:
    # Устанавливаем transfers.enabled = false
    op.execute("""
        UPDATE settings
        SET features = jsonb_set(
            features::jsonb,
            '{transfers,enabled}',
            'false'::jsonb,
            true
        )
        WHERE features IS NOT NULL
    """)
