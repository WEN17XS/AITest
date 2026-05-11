"""新增测试运行附件表

Revision ID: 20260511_0006
Revises: 20260511_0005
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260511_0006"
down_revision: Union[str, None] = "20260511_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_run_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["test_run_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_run_artifacts_run_id", "test_run_artifacts", ["run_id"])
    op.create_index("ix_test_run_artifacts_result_id", "test_run_artifacts", ["result_id"])


def downgrade() -> None:
    op.drop_index("ix_test_run_artifacts_result_id", table_name="test_run_artifacts")
    op.drop_index("ix_test_run_artifacts_run_id", table_name="test_run_artifacts")
    op.drop_table("test_run_artifacts")
