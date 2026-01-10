from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"))
    op.drop_column("users", "points")


def downgrade() -> None:
    op.add_column("users", sa.Column("points", sa.Integer(), nullable=False, server_default="0"))
    op.drop_column("users", "balance")
