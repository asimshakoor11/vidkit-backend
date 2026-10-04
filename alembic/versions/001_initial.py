"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-29 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("plan", sa.String(length=20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_expires_at", "jobs", ["expires_at"])
    op.create_index("idx_jobs_client_id", "jobs", ["client_id"])

    op.create_table(
        "job_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("part_index", sa.Integer(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("codec_video", sa.String(length=30), nullable=True),
        sa.Column("codec_audio", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_job_files_job_id", "job_files", ["job_id"])


def downgrade() -> None:
    op.drop_index("idx_job_files_job_id", table_name="job_files")
    op.drop_table("job_files")
    op.drop_index("idx_jobs_client_id", table_name="jobs")
    op.drop_index("idx_jobs_expires_at", table_name="jobs")
    op.drop_index("idx_jobs_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("users")
