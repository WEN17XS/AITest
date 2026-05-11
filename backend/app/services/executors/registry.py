from __future__ import annotations

from app.db.models import TestCase
from app.services.executors.base import TestExecutor
from app.services.executors.mock_executor import MockExecutor
from app.services.executors.playwright_executor import PlaywrightExecutor


class ExecutorRegistry:
    """执行器注册表，集中管理执行器查找和默认分发规则。"""

    def __init__(self) -> None:
        self._executors: dict[str, TestExecutor] = {}
        self._case_type_defaults: dict[str, str] = {}

    def register(self, executor: TestExecutor, *, default_for: set[str] | None = None) -> None:
        self._executors[executor.name] = executor
        for case_type in default_for or set():
            self._case_type_defaults[case_type] = executor.name

    def get(self, executor_type: str) -> TestExecutor:
        executor = self._executors.get(executor_type)
        if executor is None:
            supported = "、".join(sorted(self._executors)) or "无"
            raise ValueError(f"不支持的测试执行器：{executor_type}。当前可用执行器：{supported}")
        return executor

    def resolve(self, cases: list[TestCase], executor_type: str | None = None) -> TestExecutor:
        if executor_type:
            return self.get(executor_type)

        case_types = {case.type for case in cases if case.type}
        for case_type in sorted(case_types):
            default_executor = self._case_type_defaults.get(case_type)
            if default_executor:
                return self.get(default_executor)

        return self.get("mock")


def create_default_registry() -> ExecutorRegistry:
    registry = ExecutorRegistry()
    mock_executor = MockExecutor()
    playwright_executor = PlaywrightExecutor()
    registry.register(
        mock_executor,
        default_for={"manual", "api", "integration"},
    )
    registry.register(playwright_executor, default_for={"web_ui"})
    return registry
