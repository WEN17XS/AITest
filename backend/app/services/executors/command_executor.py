from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.services.executors.base import CaseExecutionResult, ExecutionContext, ExecutionResult


class CommandExecutor:
    """通用命令执行器。

    仅允许运行配置或步骤中声明的参数数组，不经过 shell；默认命令白名单很窄，
    可通过运行级 executor_config.allowed_commands 扩展。
    """

    name = "command"
    supported_case_types = {"command", "integration", "regression"}
    default_allowed_commands = {"python", "pytest", "npm", "pnpm", "node"}

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        if not context.cases:
            return ExecutionResult(
                status="skipped",
                summary={"total": 0, "passed": 0, "failed": 0, "skipped": 1, "error": 0},
                report="没有找到可执行的命令测试用例。",
            )

        workspace = self._workspace(context)
        timeout_seconds = int(context.config.get("timeout_seconds") or 120)
        allowed_commands = set(context.config.get("allowed_commands") or self.default_allowed_commands)
        results: list[CaseExecutionResult] = []
        run_logs: list[str] = []

        for case in context.cases:
            command = self._command_for_case(case.steps or [], context)
            logs = [f"执行用例：{case.title}", f"工作目录：{workspace}", "命令：" + " ".join(command)]
            try:
                self._validate_command(command, allowed_commands)
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
                logs.append(output or "命令未输出内容")
                status = "passed" if completed.returncode == 0 else "failed"
                message = "命令执行通过" if status == "passed" else f"命令退出码：{completed.returncode}"
            except subprocess.TimeoutExpired as exc:
                status = "failed"
                message = f"命令执行超时：{timeout_seconds}s"
                logs.append(self._trim_output((exc.stdout or "") + "\n" + (exc.stderr or "")))
            except (OSError, ValueError) as exc:
                status = "error"
                message = f"命令执行器失败：{exc}"
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
            raise ValueError(f"命令工作目录不存在：{workspace}")
        return workspace

    def _command_for_case(self, steps: list[dict[str, Any]], context: ExecutionContext) -> list[str]:
        command = context.config.get("command")
        for step in steps:
            if isinstance(step, dict) and step.get("action") == "command" and isinstance(step.get("command"), list):
                command = step["command"]
                break
        if not isinstance(command, list) or not command:
            raise ValueError("命令执行器需要 executor_config.command 或 action=command 的 command 数组")
        return [str(item) for item in command]

    def _validate_command(self, command: list[str], allowed_commands: set[str]) -> None:
        executable = Path(command[0]).name.lower()
        executable = executable[:-4] if executable.endswith(".exe") else executable
        if executable not in allowed_commands:
            supported = "、".join(sorted(allowed_commands))
            raise ValueError(f"命令 {command[0]} 不在白名单中，当前允许：{supported}")

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
            f"# 命令测试报告：{context.run_name}\n\n"
            f"- 总数：{summary['total']}\n"
            f"- 通过：{summary['passed']}\n"
            f"- 失败：{summary['failed']}\n"
            f"- 错误：{summary['error']}\n\n"
            "当前使用通用命令执行器，命令以参数数组形式运行且不经过 shell。"
        )
