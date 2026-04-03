"""Add app session storage

Revision ID: 20260402_02
Revises: 20260402_01
Create Date: 2026-04-02 15:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260402_02"
down_revision: Union[str, Sequence[str], None] = "20260402_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "app_sessions" in inspector.get_table_names():
        return

    op.create_table(
        "app_sessions",
        sa.Column("session_id_hash", sa.String(), nullable=False),
        sa.Column("broadcaster_id", sa.String(), nullable=False),
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("csrf_token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["broadcaster_id"],
            ["broadcaster_installations.broadcaster_id"],
        ),
        sa.PrimaryKeyConstraint("session_id_hash"),
    )
    op.create_index(
        op.f("ix_app_sessions_broadcaster_id"),
        "app_sessions",
        ["broadcaster_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "app_sessions" not in inspector.get_table_names():
        return

    op.drop_index(op.f("ix_app_sessions_broadcaster_id"), table_name="app_sessions")
    op.drop_table("app_sessions")
