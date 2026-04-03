"""Initial schema

Revision ID: 20260402_01
Revises:
Create Date: 2026-04-02 12:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260402_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "broadcaster_installations"):
        op.create_table(
            "broadcaster_installations",
            sa.Column("broadcaster_id", sa.String(), nullable=False),
            sa.Column("login", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("access_token", sa.String(), nullable=False),
            sa.Column("refresh_token", sa.String(), nullable=False),
            sa.Column("expires_at", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("broadcaster_id"),
        )
        op.create_index(
            op.f("ix_broadcaster_installations_login"),
            "broadcaster_installations",
            ["login"],
            unique=True,
        )

    if not _table_exists(inspector, "broadcaster_settings"):
        op.create_table(
            "broadcaster_settings",
            sa.Column("commands", sa.JSON(), nullable=False),
            sa.Column("minimum_votes", sa.Integer(), nullable=False),
            sa.Column("command_window", sa.Integer(), nullable=False),
            sa.Column("command_cooldown", sa.Integer(), nullable=False),
            sa.Column("vote_permissions", sa.String(), nullable=False),
            sa.Column("subscriber_months", sa.String(), nullable=False),
            sa.Column("override_permissions", sa.String(), nullable=False),
            sa.Column("discord_webhook_url", sa.String(), nullable=False, server_default=""),
            sa.Column("donotallowlist_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("donotallowlist_usernames", sa.JSON(), nullable=False),
            sa.Column("broadcaster_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(
                ["broadcaster_id"],
                ["broadcaster_installations.broadcaster_id"],
            ),
            sa.PrimaryKeyConstraint("broadcaster_id"),
        )
    else:
        columns = _column_names(inspector, "broadcaster_settings")
        if "commands_json" in columns and "commands" not in columns:
            with op.batch_alter_table("broadcaster_settings") as batch_op:
                batch_op.alter_column(
                    "commands_json",
                    new_column_name="commands",
                    existing_type=sa.Text(),
                )
        if "donotallowlist_usernames_json" in columns and "donotallowlist_usernames" not in columns:
            with op.batch_alter_table("broadcaster_settings") as batch_op:
                batch_op.alter_column(
                    "donotallowlist_usernames_json",
                    new_column_name="donotallowlist_usernames",
                    existing_type=sa.Text(),
                )

    if not _table_exists(inspector, "clip_statistics"):
        op.create_table(
            "clip_statistics",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("clip_id", sa.String(), nullable=False),
            sa.Column("clip_url", sa.String(), nullable=False),
            sa.Column("timestamp", sa.String(), nullable=False),
            sa.Column("voters", sa.String(), nullable=False, server_default=""),
            sa.Column("comments", sa.String(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(), nullable=False, server_default=""),
            sa.Column("time_to_generate", sa.Float(), nullable=True),
            sa.Column("time_into_broadcast", sa.String(), nullable=True),
            sa.Column("broadcaster_id", sa.String(), nullable=True),
            sa.Column("broadcaster_name", sa.String(), nullable=True),
            sa.Column("clip_title", sa.String(), nullable=True),
            sa.Column("directory", sa.String(), nullable=True),
            sa.Column("thumbnail_url", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_clip_statistics_clip_id"), "clip_statistics", ["clip_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "clip_statistics"):
        op.drop_index(op.f("ix_clip_statistics_clip_id"), table_name="clip_statistics")
        op.drop_table("clip_statistics")

    if _table_exists(inspector, "broadcaster_settings"):
        op.drop_table("broadcaster_settings")

    if _table_exists(inspector, "broadcaster_installations"):
        op.drop_index(op.f("ix_broadcaster_installations_login"), table_name="broadcaster_installations")
        op.drop_table("broadcaster_installations")
