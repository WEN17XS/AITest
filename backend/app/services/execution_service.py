from __future__ import annotations

from datetime import UTC, datetime
from random import randint

from sqlalchemy.orm import Session

from app.db.models import TestCase, TestRun, TestRunResult


class TestExecutionService:
    """测试执行服务。

    第一版先提供稳定的模拟执行器，后续可以根据 TestCase.type 分发到
    Playwright、pytest、Newman、JMeter 等真实执行器。
    """

    def run(self, db: Session, run_id: int, case_ids: list[int] | None = None) -> TestRun:
        run = db.get(TestRun, run_id)
        if run is None:
            raise ValueError(f"测试运行不存在: {run_id}")

        run.status = "running"
        run.started_at = datetime.now(UTC)
        db.commit()

        query = db.query(TestCase).filter(TestCase.project_id == run.project_id)
        if case_ids:
            query = query.filter(TestCase.id.in_(case_ids))
        else:
            query = query.filter(TestCase.status == "approved")
        cases = query.order_by(TestCase.priority.asc(), TestCase.id.asc()).all()

        passed = 0
        failed = 0
        skipped = 0

        if not cases:
            skipped = 1
            run.report = "没有找到可执行的已审核测试用例，请先审核或手动选择用例。"
        else:
            for case in cases:
                result_status = self._simulate_case_status(case)
                if result_status == "passed":
                    passed += 1
                else:
                    failed += 1

                db.add(
                    TestRunResult(
                        run_id=run.id,
                        case_id=case.id,
                        status=result_status,
                        duration_ms=randint(200, 2200),
                        message="模拟执行通过" if result_status == "passed" else "模拟执行失败，请接入真实执行器后查看详细日志。",
                        logs=f"执行用例：{case.title}\n类型：{case.type}\n优先级：{case.priority}",
                        artifacts=[],
                    )
                )

            run.report = self._build_report(run, passed, failed, skipped)

        run.status = "failed" if failed else "passed"
        if skipped and not cases:
            run.status = "skipped"
        run.summary = {"total": len(cases), "passed": passed, "failed": failed, "skipped": skipped}
        run.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
        return run

    def _simulate_case_status(self, case: TestCase) -> str:
        # 高优先级回归用例更适合作为质量门禁，模拟器默认让它们通过。
        if case.priority == "P1":
            return "passed"
        return "failed" if "异常" in case.title and case.status != "approved" else "passed"

    def _build_report(self, run: TestRun, passed: int, failed: int, skipped: int) -> str:
        return (
            f"# 测试报告：{run.name}\n\n"
            f"- 触发方式：{run.trigger_type}\n"
            f"- 分支：{run.branch or '未提供'}\n"
            f"- 提交：{run.commit_sha or '未提供'}\n"
            f"- 通过：{passed}\n"
            f"- 失败：{failed}\n"
            f"- 跳过：{skipped}\n\n"
            "当前使用内置模拟执行器。接入 Playwright 或 pytest 后，这里会展示真实日志、截图和失败归因。"
        )

