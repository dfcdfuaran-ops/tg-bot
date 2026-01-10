from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create as UUID array from the start (correct implementation)
    op.add_column(
        "subscriptions",
        sa.Column(
            "external_squad",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
