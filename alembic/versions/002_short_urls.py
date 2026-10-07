"""short_urls table

Revision ID: 002_short_urls
Revises: 001_initial
Create Date: 2026-10-06 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_short_urls"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "short_urls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_short_urls_code", "short_urls", ["code"], unique=True)
    op.create_index("idx_short_urls_expires_at", "short_urls", ["expires_at"])
    op.create_index("idx_short_urls_client_id", "short_urls", ["client_id"])


def downgrade() -> None:
    op.drop_index("idx_short_urls_client_id", table_name="short_urls")
    op.drop_index("idx_short_urls_expires_at", table_name="short_urls")
    op.drop_index("idx_short_urls_code", table_name="short_urls")
    op.drop_table("short_urls")
