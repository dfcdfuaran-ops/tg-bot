"""Rename POINTS to MONEY in referral_reward_type enum.

Revision ID: 0020
Revises: 0019
Create Date: 2025-12-28

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename POINTS to MONEY in the referral_reward_type enum
    op.execute("ALTER TYPE referral_reward_type RENAME VALUE 'POINTS' TO 'MONEY'")
    
    # Update settings JSON to replace POINTS with MONEY
    op.execute(
        text("""
            UPDATE settings 
            SET referral = jsonb_set(
                referral::jsonb, 
                '{reward,type}', 
                '"MONEY"'
            )
            WHERE referral::jsonb #>> '{reward,type}' = 'POINTS'
        """)
    )


def downgrade() -> None:
    # Rename MONEY back to POINTS
    op.execute("ALTER TYPE referral_reward_type RENAME VALUE 'MONEY' TO 'POINTS'")
    
    # Update settings JSON to replace MONEY with POINTS
    op.execute(
        text("""
            UPDATE settings 
            SET referral = jsonb_set(
                referral::jsonb, 
                '{reward,type}', 
                '"POINTS"'
            )
            WHERE referral::jsonb #>> '{reward,type}' = 'MONEY'
        """)
    )
