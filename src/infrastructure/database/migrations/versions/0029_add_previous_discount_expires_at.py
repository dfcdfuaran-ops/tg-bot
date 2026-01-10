"""add_previous_discount_expires_at_to_promocode_activations

Revision ID: 0029
Revises: 0028
Create Date: 2026-01-02

"""
from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promocode_activations",
        sa.Column("previous_discount_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("promocode_activations", "previous_discount_expires_at")
