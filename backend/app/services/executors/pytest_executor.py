from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.executors.base import CaseExecutionResult, ExecutionContext, ExecutionResult


class PytestExecutor:
    """pytest 执行器。

    第一版只允许通过参数数组调用 pytest，不经过 shell。
    用例步骤可提供 action=pytest、target 和 args，也可由运行级配置提供 args。
    """

    name = "pytest"
    supported_case_types = {"pytest", "integration", "regression"}

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        if not context.cases:
            return ExecutionResult(
                status="skipped",
                summary={"total": 0, "passed": 0, "failed": 0, "skipped": 1, "error": 0},
                report="没有找到可执行的 pytest 测试用例。",
            )

        workspace = self._workspace(context)
        timeout_seconds = int(context.config.get("timeout_seconds") or 120)
        results: list[CaseExecutionResult] = []
        run_logs: list[str] = []

        for case in context.cases:
            command = self._command_for_case(case.steps or [], context)
            logs = [f"执行用例：{case.title}", f"工作目录：{workspace}", "命令：" + " ".join(command)]
            try:
                completed = subprocess.run(
                    command,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False,
                    check=False,
                )
                output = self._trim_output("\n".join([completed.stdout, completed.stderr]).strip())
                logs.append(output or "pytest 未输出内容")
                status = "passed" if completed.returncode == 0 else "failed"
                message = "pytest 执行通过" if status == "passed" else f"pytest 退出码：{completed.returncode}"
            except subprocess.TimeoutExpired as exc:
                status = "failed"
                message = f"pytest 执行超时：{timeout_seconds}s"
                logs.append(self._trim_output((exc.stdout or "") + "\n" + (exc.stderr or "")))
            except OSError as exc:
                status = "error"
                message = f"pytest 执行器启动失败：{exc}"
                logs.append(message)

            run_logs.extend(logs)
            results.append(
                CaseExecutionResult(
                    case_id=case.id,
                    status=status,
                    message=message,
                    logs="\n".join(logs),
                    artifacts=[],
                    metadata={"executor": self.name, "command": command},
                )
            )

        summary = self._build_summary(results)
        return ExecutionResult(
            status=self._run_status(summary),
            case_results=results,
            summary=summary,
            report=self._build_report(context, summary),
            logs="\n".join(run_logs),
        )

    def _workspace(self, context: ExecutionContext) -> Path:
        raw_workspace = context.config.get("workspace_dir") or context.workspace_dir
        workspace = Path(raw_workspace).resolve() if raw_workspace else Path.cwd()
        if not workspace.exists() or not workspace.is_dir():
            raise ValueError(f"pytest 工作目录不存在：{workspace}")
        return workspace

    def _command_for_case(self, steps: list[dict], context: ExecutionContext) -> list[str]:
        base_command = list(context.config.get("command") or ["python", "-m", "pytest"])
        args = list(context.config.get("args") or [])
        for step in steps:
            if not isinstance(step, dict) or step.get("action") != "pytest":
                continue
            if isinstance(step.get("args"), list):
                args.extend(str(item) for item in step["args"])
            if step.get("target"):
                args.append(str(step["target"]))
        return [str(item) for item in [*base_command, *args]]

    def _trim_output(self, output: str, limit: int = 12000) -> str:
        text = output.strip()
        if len(text) <= limit:
            return text
        return text[-limit:]

    def _build_summary(self, results: list[CaseExecutionResult]) -> dict[str, int]:
        passed = sum(1 for result in results if result.status == "passed")
        failed = sum(1 for result in results if result.status == "failed")
        error = sum(1 for result in results if result.status == "error")
        return {"total": len(results), "passed": passed, "failed": failed, "skipped": 0, "error": error}

    def _run_status(self, summary: dict[str, int]) -> str:
        if summary["error"]:
            return "error"
        if summary["failed"]:
            return "failed"
        return "passed"

    def _build_report(self, context: ExecutionContext, summary: dict[str, int]) -> str:
        return (
            f"# pytest 测试报告：{context.run_name}\n\n"
            f"- 总数：{summary['total']}\n"
            f"- 通过：{summary['passed']}\n"
            f"- 失败：{summary['failed']}\n"
            f"- 错误：{summary['error']}\n\n"
            "当前使用 pytest 执行器，通过非 shell subprocess 调用 pytest。"
        )
