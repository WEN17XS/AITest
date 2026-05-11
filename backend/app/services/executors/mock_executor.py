from __future__ import annotations

from random import randint

from app.db.models import TestCase
from app.services.executors.base import CaseExecutionResult, ExecutionContext, ExecutionResult


class MockExecutor:
    """内置模拟执行器，作为平台闭环的稳定兜底能力。"""

    name = "mock"
    supported_case_types = {"manual", "web_ui", "api", "integration"}

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        passed = 0
        failed = 0
        skipped = 0
        case_results: list[CaseExecutionResult] = []

        if not context.cases:
            skipped = 1
            return ExecutionResult(
                status="skipped",
                case_results=[],
                summary={"total": 0, "passed": 0, "failed": 0, "skipped": skipped},
                report="没有找到可执行的已审核测试用例，请先审核或手动选择用例。",
            )

        for case in context.cases:
            result_status = self._simulate_case_status(case)
            if result_status == "passed":
                passed += 1
            else:
                failed += 1

            case_results.append(
                CaseExecutionResult(
                    case_id=case.id,
                    status=result_status,
                    duration_ms=randint(200, 2200),
                    message="模拟执行通过" if result_status == "passed" else "模拟执行失败，请接入真实执行器后查看详细日志。",
                    logs=f"执行用例：{case.title}\n类型：{case.type}\n优先级：{case.priority}",
                    artifacts=[],
                    metadata={"executor": self.name},
                )
            )

        status = "failed" if failed else "passed"
        summary = {"total": len(context.cases), "passed": passed, "failed": failed, "skipped": skipped}
        return ExecutionResult(
            status=status,
            case_results=case_results,
            summary=summary,
            report=self._build_report(context, passed, failed, skipped),
            logs=None,
            artifacts=[],
        )

    def _simulate_case_status(self, case: TestCase) -> str:
        # 高优先级回归用例更适合作为质量门禁，模拟器默认让它们通过。
        if case.priority == "P1":
            return "passed"
        return "failed" if "异常" in case.title and case.status != "approved" else "passed"

    def _build_report(self, context: ExecutionContext, passed: int, failed: int, skipped: int) -> str:
        return (
            f"# 测试报告：{context.run_name}\n\n"
            f"- 触发方式：{context.trigger_type}\n"
            f"- 分支：{context.branch or '未提供'}\n"
            f"- 提交：{context.commit_sha or '未提供'}\n"
            f"- 通过：{passed}\n"
            f"- 失败：{failed}\n"
            f"- 跳过：{skipped}\n\n"
            "当前使用内置模拟执行器。接入 Playwright 或 pytest 后，这里会展示真实日志、截图和失败归因。"
        )
