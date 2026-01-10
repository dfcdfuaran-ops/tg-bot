"""Make referral_id nullable in referral_rewards table.

Revision ID: 0021
Revises: 0020
Create Date: 2024-12-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "referral_rewards",
        "referral_id",
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "referral_rewards",
        "referral_id",
        nullable=False,
    )
