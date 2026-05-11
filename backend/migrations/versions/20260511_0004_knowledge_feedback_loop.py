"""新增知识反馈闭环字段

Revision ID: 20260511_0004
Revises: 20260511_0003
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260511_0004"
down_revision: Union[str, None] = "20260511_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("ai_review", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("knowledge_chunks", sa.Column("status", sa.String(length=30), nullable=False, server_default="active"))
    op.add_column("knowledge_chunks", sa.Column("skill_name", sa.String(length=120), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("triggers", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("knowledge_chunks", sa.Column("quality_score", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "quality_score")
    op.drop_column("knowledge_chunks", "triggers")
    op.drop_column("knowledge_chunks", "skill_name")
    op.drop_column("knowledge_chunks", "status")
    op.drop_column("test_cases", "ai_review")
