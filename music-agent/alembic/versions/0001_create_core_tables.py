"""create core tables

Revision ID: 0001_create_core_tables
Revises:
Create Date: 2026-03-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_create_core_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "song_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requestor_id", sa.Integer(), nullable=False),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=False),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("song_title", sa.String(length=255), nullable=True),
        sa.Column("artist_name", sa.String(length=255), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("video_id", sa.String(length=100), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requestor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_song_requests_requestor_id", "song_requests", ["requestor_id"], unique=False)
    op.create_index("ix_song_requests_assigned_admin_id", "song_requests", ["assigned_admin_id"], unique=False)
    op.create_index(
        "ix_song_requests_assigned_admin_id_created_at",
        "song_requests",
        ["assigned_admin_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_song_requests_requestor_id_created_at",
        "song_requests",
        ["requestor_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "downloads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("saved_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["song_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_downloads_request_id", "downloads", ["request_id"], unique=False)
    op.create_index("ix_downloads_admin_id", "downloads", ["admin_id"], unique=False)
    op.create_index(
        "ix_downloads_request_id_created_at",
        "downloads",
        ["request_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_downloads_request_id_created_at", table_name="downloads")
    op.drop_index("ix_downloads_admin_id", table_name="downloads")
    op.drop_index("ix_downloads_request_id", table_name="downloads")
    op.drop_table("downloads")

    op.drop_index("ix_song_requests_requestor_id_created_at", table_name="song_requests")
    op.drop_index("ix_song_requests_assigned_admin_id_created_at", table_name="song_requests")
    op.drop_index("ix_song_requests_assigned_admin_id", table_name="song_requests")
    op.drop_index("ix_song_requests_requestor_id", table_name="song_requests")
    op.drop_table("song_requests")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

