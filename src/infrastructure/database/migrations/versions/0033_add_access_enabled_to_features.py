"""add_access_enabled_to_features

Revision ID: 0033
Revises: 0032
Create Date: 2026-01-05

"""
from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обновляем существующие записи в таблице settings
    # Добавляем access_enabled = true в features JSON
    op.execute("""
        UPDATE settings
        SET features = jsonb_set(
            features::jsonb,
            '{access_enabled}',
            'true'::jsonb,
            true
        )
        WHERE features IS NOT NULL
    """)


def downgrade() -> None:
    # Удаляем access_enabled из features JSON
    op.execute("""
        UPDATE settings
        SET features = features::jsonb - 'access_enabled'
        WHERE features IS NOT NULL
    """)
