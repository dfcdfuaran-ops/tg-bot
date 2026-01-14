"""add_features_to_settings

Revision ID: 0028
Revises: 0027
Create Date: 2026-01-02

"""
from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку features с дефолтным значением JSON
    op.add_column(
        "settings",
        sa.Column(
            "features",
            sa.JSON(),
            nullable=False,
            server_default='{"community_enabled": false, "tos_enabled": false, "balance_enabled": true}'
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "features")
