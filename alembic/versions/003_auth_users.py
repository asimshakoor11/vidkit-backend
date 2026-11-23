"""auth users index and constraints

Revision ID: 003_auth_users
Revises: 002_short_urls
Create Date: 2026-11-23 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_auth_users"
down_revision: Union[str, Sequence[str], None] = "002_short_urls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure index on email for quick lookup if not present
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes("users")]
    if "ix_users_email" not in indexes:
        try:
            op.create_index("ix_users_email", "users", ["email"], unique=True)
        except Exception:
            # Email may already have a unique constraint/index
            pass


def downgrade() -> None:
    try:
        op.drop_index("ix_users_email", table_name="users")
    except Exception:
        pass
