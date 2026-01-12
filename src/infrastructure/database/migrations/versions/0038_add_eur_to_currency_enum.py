from typing import Sequence, Union

from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add EUR to currency enum
    op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'EUR'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    # So we can't easily downgrade this migration
    pass
