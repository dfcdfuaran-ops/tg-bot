"""Add name field to promocodes table.

Revision ID: 0023
Revises: 0022
Create Date: 2026-01-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promocodes", sa.Column("name", sa.String(), nullable=False, server_default=""))
    op.alter_column("promocodes", "name", server_default=None)


def downgrade() -> None:
    op.drop_column("promocodes", "name")
