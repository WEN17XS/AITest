"""新增测试结果 AI 失败归因字段

Revision ID: 20260512_0007
Revises: 20260511_0006
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260512_0007"
down_revision: Union[str, None] = "20260511_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_run_results",
        sa.Column("ai_diagnosis", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("test_run_results", "ai_diagnosis")
