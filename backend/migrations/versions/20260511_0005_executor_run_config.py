"""新增测试运行执行器配置字段

Revision ID: 20260511_0005
Revises: 20260511_0004
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260511_0005"
down_revision: Union[str, None] = "20260511_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("environment_id", sa.Integer(), nullable=True))
    op.add_column("test_runs", sa.Column("executor_type", sa.String(length=40), nullable=False, server_default="mock"))
    op.add_column("test_runs", sa.Column("executor_config", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("test_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_test_runs_environment_id_project_environments",
        "test_runs",
        "project_environments",
        ["environment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_test_runs_environment_id_project_environments", "test_runs", type_="foreignkey")
    op.drop_column("test_runs", "error_message")
    op.drop_column("test_runs", "executor_config")
    op.drop_column("test_runs", "executor_type")
    op.drop_column("test_runs", "environment_id")
