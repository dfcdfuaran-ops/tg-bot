"""Add EXTRA_DEVICES to purchasetype enum

Revision ID: 0037
Revises: 0036
Create Date: 2026-01-08

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add EXTRA_DEVICES value to purchasetype enum
    op.execute("ALTER TYPE purchasetype ADD VALUE IF NOT EXISTS 'EXTRA_DEVICES'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type
    pass
