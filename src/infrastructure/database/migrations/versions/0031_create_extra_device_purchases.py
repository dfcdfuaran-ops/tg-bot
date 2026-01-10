"""create_extra_device_purchases

Revision ID: 0031
Revises: 0030
Create Date: 2026-01-03

"""
from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extra_device_purchases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("device_count", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),  # Стоимость за месяц
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default="true"),  # Автопродление
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_telegram_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extra_device_purchases_subscription_id", "extra_device_purchases", ["subscription_id"])
    op.create_index("ix_extra_device_purchases_user_telegram_id", "extra_device_purchases", ["user_telegram_id"])
    op.create_index("ix_extra_device_purchases_expires_at", "extra_device_purchases", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_extra_device_purchases_expires_at")
    op.drop_index("ix_extra_device_purchases_user_telegram_id")
    op.drop_index("ix_extra_device_purchases_subscription_id")
    op.drop_table("extra_device_purchases")
