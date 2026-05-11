from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.db.models import ProjectEnvironment, TestCase


@dataclass(slots=True)
class ExecutionContext:
    """执行器运行上下文，由编排层负责组装。"""

    run_id: int
    project_id: int
    run_name: str
    trigger_type: str
    cases: list[TestCase]
    branch: str | None = None
    commit_sha: str | None = None
    changed_files: list[str] = field(default_factory=list)
    environment: ProjectEnvironment | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    workspace_dir: Path | None = None
    artifacts_dir: Path | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CaseExecutionResult:
    case_id: int | None
    status: str
    duration_ms: int = 0
    message: str | None = None
    logs: str | None = None
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    status: str
    case_results: list[CaseExecutionResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    report: str | None = None
    logs: str | None = None
    artifacts: list[str] = field(default_factory=list)


class TestExecutor(Protocol):
    name: str
    supported_case_types: set[str]

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """执行测试并返回标准化结果。"""
