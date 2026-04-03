"""Add worker error state to broadcaster installations

Revision ID: 20260403_01
Revises: 20260402_02
Create Date: 2026-04-03 02:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260403_01"
down_revision: Union[str, Sequence[str], None] = "20260402_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("broadcaster_installations")}
    if "worker_error" in columns:
        return

    with op.batch_alter_table("broadcaster_installations") as batch_op:
        batch_op.add_column(sa.Column("worker_error", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("broadcaster_installations")}
    if "worker_error" not in columns:
        return

    with op.batch_alter_table("broadcaster_installations") as batch_op:
        batch_op.drop_column("worker_error")
