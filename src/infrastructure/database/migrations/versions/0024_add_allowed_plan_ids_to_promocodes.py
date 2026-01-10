"""Add allowed_plan_ids field to promocodes table.

Revision ID: 0024
Revises: 0023
Create Date: 2026-01-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promocodes", sa.Column("allowed_plan_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("promocodes", "allowed_plan_ids")
