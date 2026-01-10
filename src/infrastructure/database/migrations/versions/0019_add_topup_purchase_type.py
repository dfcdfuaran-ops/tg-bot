"""Add TOPUP to purchasetype enum

Revision ID: 0019
Revises: 0018
Create Date: 2024-12-28

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add TOPUP value to purchasetype enum
    op.execute("ALTER TYPE purchasetype ADD VALUE IF NOT EXISTS 'TOPUP'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type
    pass
