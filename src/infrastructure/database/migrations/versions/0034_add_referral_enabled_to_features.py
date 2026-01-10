"""add_referral_enabled_to_features

Revision ID: 0034
Revises: 0033
Create Date: 2026-01-05

"""
from alembic import op
import sqlalchemy as sa


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обновляем существующие записи в таблице settings
    # Добавляем referral_enabled = true в features JSON
    op.execute("""
        UPDATE settings
        SET features = jsonb_set(
            features::jsonb,
            '{referral_enabled}',
            'true'::jsonb,
            true
        )
        WHERE features IS NOT NULL
    """)


def downgrade() -> None:
    # Удаляем referral_enabled из features JSON
    op.execute("""
        UPDATE settings
        SET features = features::jsonb - 'referral_enabled'
        WHERE features IS NOT NULL
    """)
