from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunk, TestCase
from app.schemas import KnowledgeCreate


class KnowledgeService:
    """向量知识库服务。

    第一版先写入知识文本和元数据。embedding 字段预留给真实向量模型，
    这样数据库结构可以提前稳定下来。
    """

    def create_chunk(self, db: Session, payload: KnowledgeCreate) -> KnowledgeChunk:
        chunk = KnowledgeChunk(
            project_id=payload.project_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            title=payload.title,
            content=payload.content,
            status=payload.status,
            skill_name=payload.skill_name,
            triggers=payload.triggers,
            quality_score=payload.quality_score,
            metadata_=payload.metadata,
            embedding=None,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def get_skill_context(self, db: Session, project_id: int, query: str, limit: int = 6) -> list[KnowledgeChunk]:
        """按关键词召回当前项目的有效 skill 知识。

        第一阶段先使用关键词召回，后续接入 embedding 后可以替换为向量召回。
        """
        keywords = self._extract_keywords(query)
        db_query = db.query(KnowledgeChunk).filter(
            KnowledgeChunk.project_id == project_id,
            KnowledgeChunk.status.in_(["active", "verified"]),
        )
        if keywords:
            conditions = []
            for keyword in keywords[:8]:
                pattern = f"%{keyword}%"
                conditions.append(KnowledgeChunk.title.ilike(pattern))
                conditions.append(KnowledgeChunk.content.ilike(pattern))
            from sqlalchemy import or_

            db_query = db_query.filter(or_(*conditions))
        return db_query.order_by(KnowledgeChunk.quality_score.desc(), KnowledgeChunk.id.desc()).limit(limit).all()

    def format_skill_context(self, chunks: list[KnowledgeChunk]) -> str:
        if not chunks:
            return "暂无可用测试 skill 知识。"
        lines = []
        for index, chunk in enumerate(chunks, start=1):
            triggers = "、".join(chunk.triggers or [])
            lines.append(
                f"{index}. [{chunk.source_type}] {chunk.title}\n"
                f"   skill：{chunk.skill_name or '通用测试经验'}；触发词：{triggers or '未配置'}；质量分：{chunk.quality_score}\n"
                f"   内容：{chunk.content[:800]}"
            )
        return "\n".join(lines)

    def create_from_test_case(
        self,
        db: Session,
        test_case: TestCase,
        source_type: str,
        status: str = "verified",
    ) -> KnowledgeChunk:
        title = f"测试用例经验：{test_case.title}"
        content = self._format_case_content(test_case)
        existing = (
            db.query(KnowledgeChunk)
            .filter(
                KnowledgeChunk.project_id == test_case.project_id,
                KnowledgeChunk.source_type == source_type,
                KnowledgeChunk.source_id == str(test_case.id),
            )
            .first()
        )
        if existing:
            existing.title = title
            existing.content = content
            existing.status = status
            existing.skill_name = self._skill_name_from_case(test_case)
            existing.triggers = self._case_triggers(test_case)
            existing.quality_score = 4 if test_case.status == "approved" else 2
            existing.metadata_ = self._case_metadata(test_case)
            db.commit()
            db.refresh(existing)
            return existing

        chunk = KnowledgeChunk(
            project_id=test_case.project_id,
            source_type=source_type,
            source_id=str(test_case.id),
            title=title,
            content=content,
            status=status,
            skill_name=self._skill_name_from_case(test_case),
            triggers=self._case_triggers(test_case),
            quality_score=4 if test_case.status == "approved" else 2,
            metadata_=self._case_metadata(test_case),
            embedding=None,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def create_rejection_pattern(self, db: Session, test_case: TestCase, review_comment: str | None) -> KnowledgeChunk:
        content = (
            f"被人工驳回的 AI/人工用例：{test_case.title}\n"
            f"驳回原因：{review_comment or '未填写'}\n"
            f"用例内容：\n{self._format_case_content(test_case)}\n"
            "后续生成时应避免同类问题，除非需求明确要求。"
        )
        chunk = KnowledgeChunk(
            project_id=test_case.project_id,
            source_type="anti_pattern",
            source_id=str(test_case.id),
            title=f"反例经验：{test_case.title}",
            content=content,
            status="active",
            skill_name="AI 用例反例",
            triggers=self._case_triggers(test_case),
            quality_score=2,
            metadata_={"case_id": test_case.id, "review_comment": review_comment, "case_status": test_case.status},
            embedding=None,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def _format_case_content(self, test_case: TestCase) -> str:
        steps = "\n".join(f"{step.get('order', index + 1)}. {step.get('action', '')}" for index, step in enumerate(test_case.steps or []))
        return (
            f"标题：{test_case.title}\n"
            f"类型：{test_case.type}\n"
            f"优先级：{test_case.priority}\n"
            f"前置条件：{test_case.preconditions or '无'}\n"
            f"步骤：\n{steps}\n"
            f"预期结果：{test_case.expected_result}\n"
            f"标签：{', '.join(test_case.tags or [])}\n"
            f"AI自评审：{test_case.ai_review or {}}"
        )

    def _case_metadata(self, test_case: TestCase) -> dict:
        return {
            "case_id": test_case.id,
            "requirement_id": test_case.requirement_id,
            "case_status": test_case.status,
            "generated_by": test_case.generated_by,
            "review_comment": test_case.review_comment,
        }

    def _skill_name_from_case(self, test_case: TestCase) -> str:
        if test_case.type in {"security"}:
            return "安全测试经验"
        if test_case.type in {"api"}:
            return "接口测试经验"
        if test_case.type in {"ui"}:
            return "UI 测试经验"
        if test_case.type in {"regression"}:
            return "回归测试经验"
        return "功能测试经验"

    def _case_triggers(self, test_case: TestCase) -> list[str]:
        values = [test_case.type, test_case.priority, *(test_case.tags or [])]
        title_words = self._extract_keywords(test_case.title)
        return [item for item in [*values, *title_words] if item][:12]

    def _extract_keywords(self, text: str) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        parts = [item for item in re_split_keywords(cleaned) if 2 <= len(item) <= 32]
        return list(dict.fromkeys(parts))[:12]


def re_split_keywords(text: str) -> list[str]:
    import re

    return [item.strip() for item in re.split(r"[\s,，。；;、:：/\\|()\[\]{}<>《》\"']+", text) if item.strip()]
