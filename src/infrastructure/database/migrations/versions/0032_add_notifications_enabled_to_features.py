"""add_notifications_enabled_to_features

Revision ID: 0032
Revises: 0031
Create Date: 2026-01-05

"""
from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обновляем существующие записи в таблице settings
    # Добавляем notifications_enabled = true в features JSON
    op.execute("""
        UPDATE settings
        SET features = jsonb_set(
            features::jsonb,
            '{notifications_enabled}',
            'true'::jsonb,
            true
        )
        WHERE features IS NOT NULL
    """)


def downgrade() -> None:
    # Удаляем notifications_enabled из features JSON
    op.execute("""
        UPDATE settings
        SET features = features::jsonb - 'notifications_enabled'
        WHERE features IS NOT NULL
    """)
