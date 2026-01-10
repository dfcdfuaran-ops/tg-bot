"""Migration to alter external_squad column from UUID to UUID array."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert external_squad column from UUID to UUID[] array."""
    # Step 1: Create a new column with correct type
    op.add_column(
        "subscriptions",
        sa.Column("external_squad_new", postgresql.UUID(as_uuid=True), nullable=True),
    )
    
    # Step 2: Migrate data - convert single UUID to array
    op.execute("""
        UPDATE subscriptions
        SET external_squad_new = external_squad
    """)
    
    # Step 3: Drop old column
    op.drop_column("subscriptions", "external_squad")
    
    # Step 4: Create the array column
    op.add_column(
        "subscriptions",
        sa.Column(
            "external_squad",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
    )
    
    # Step 5: Migrate data from temporary to array column
    op.execute("""
        UPDATE subscriptions
        SET external_squad = 
            CASE 
                WHEN external_squad_new IS NOT NULL THEN ARRAY[external_squad_new]
                ELSE NULL
            END
    """)
    
    # Step 6: Drop temporary column
    op.drop_column("subscriptions", "external_squad_new")


def downgrade() -> None:
    """Revert external_squad from UUID[] array back to UUID."""
    # Create temporary UUID column
    op.add_column(
        "subscriptions",
        sa.Column("external_squad_old", postgresql.UUID(as_uuid=True), nullable=True),
    )
    
    # Take first element from array if exists
    op.execute("""
        UPDATE subscriptions
        SET external_squad_old = 
            CASE 
                WHEN external_squad IS NOT NULL AND array_length(external_squad, 1) > 0 
                    THEN external_squad[1]
                ELSE NULL
            END
    """)
    
    # Drop array column
    op.drop_column("subscriptions", "external_squad")
    
    # Rename old back to original name
    op.alter_column("subscriptions", "external_squad_old", new_column_name="external_squad")
