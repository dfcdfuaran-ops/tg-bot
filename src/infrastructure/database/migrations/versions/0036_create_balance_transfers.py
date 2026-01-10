"""create_balance_transfers

Revision ID: 0036
Revises: 0035
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "balance_transfers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sender_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("commission", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sender_telegram_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_telegram_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_balance_transfers_sender_telegram_id", "balance_transfers", ["sender_telegram_id"])
    op.create_index("ix_balance_transfers_recipient_telegram_id", "balance_transfers", ["recipient_telegram_id"])
    op.create_index("ix_balance_transfers_created_at", "balance_transfers", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_balance_transfers_created_at")
    op.drop_index("ix_balance_transfers_recipient_telegram_id")
    op.drop_index("ix_balance_transfers_sender_telegram_id")
    op.drop_table("balance_transfers")
