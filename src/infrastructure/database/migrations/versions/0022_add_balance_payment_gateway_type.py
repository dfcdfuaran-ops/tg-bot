"""Add BALANCE to payment_gateway_type enum.

Revision ID: 0022
Revises: 0021
Create Date: 2024-12-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_gateway_type ADD VALUE IF NOT EXISTS 'BALANCE'")


def downgrade() -> None:
    # Cannot remove enum values in PostgreSQL
    pass
