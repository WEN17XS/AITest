from __future__ import annotations

from time import perf_counter
from typing import Any
from urllib.parse import urljoin

from app.services.executors.base import CaseExecutionResult, ExecutionContext, ExecutionResult


class PlaywrightExecutor:
    """Playwright Web UI 最小执行器。

    第一版只解释受控步骤，避免执行任意脚本。
    """

    name = "playwright"
    supported_case_types = {"web_ui"}
    supported_actions = {"goto", "click", "fill", "expect_text", "expect_url"}

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        if not context.cases:
            return ExecutionResult(
                status="skipped",
                summary={"total": 0, "passed": 0, "failed": 0, "skipped": 1, "error": 0},
                report="没有找到可执行的 Web UI 测试用例。",
            )

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            return self._dependency_error_result(context, exc)

        headless = bool(context.config.get("headless", True))
        browser_name = str(context.config.get("browser", "chromium"))
        timeout_ms = int(context.config.get("timeout_ms", 10000))
        screenshot_on_failure = bool(context.config.get("screenshot_on_failure", True))

        results: list[CaseExecutionResult] = []
        run_logs: list[str] = []

        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_name, None)
            if browser_type is None:
                return self._configuration_error_result(context, f"不支持的浏览器类型：{browser_name}")

            browser = browser_type.launch(headless=headless)
            try:
                for case in context.cases:
                    started = perf_counter()
                    case_dir = context.artifacts_dir / "cases" / str(case.id) if context.artifacts_dir else None
                    if case_dir:
                        case_dir.mkdir(parents=True, exist_ok=True)

                    page = browser.new_page()
                    page.set_default_timeout(timeout_ms)
                    logs: list[str] = [f"执行用例：{case.title}", f"浏览器：{browser_name}", f"超时：{timeout_ms}ms"]
                    artifacts: list[str] = []
                    status = "passed"
                    message = "Playwright 执行通过"

                    try:
                        for step in case.steps:
                            self._execute_step(page, context, step, logs)
                    except (AssertionError, PlaywrightTimeoutError, PlaywrightError, ValueError) as exc:
                        status = "failed"
                        message = str(exc)
                        logs.append(f"失败原因：{exc}")
                        if screenshot_on_failure and case_dir:
                            screenshot_path = case_dir / "failure.png"
                            page.screenshot(path=str(screenshot_path), full_page=True)
                            artifacts.append(self._relative_artifact_path(context, screenshot_path))
                            logs.append(f"失败截图：{artifacts[-1]}")
                    finally:
                        page.close()

                    duration_ms = int((perf_counter() - started) * 1000)
                    run_logs.extend(logs)
                    results.append(
                        CaseExecutionResult(
                            case_id=case.id,
                            status=status,
                            duration_ms=duration_ms,
                            message=message,
                            logs="\n".join(logs),
                            artifacts=artifacts,
                            metadata={"executor": self.name, "browser": browser_name},
                        )
                    )
            finally:
                browser.close()

        summary = self._build_summary(results)
        status = self._build_run_status(summary)
        return ExecutionResult(
            status=status,
            case_results=results,
            summary=summary,
            report=self._build_report(context, summary),
            logs="\n".join(run_logs),
        )

    def _execute_step(self, page: Any, context: ExecutionContext, step: dict[str, Any], logs: list[str]) -> None:
        action = str(step.get("action") or "").strip()
        if action not in self.supported_actions:
            raise ValueError(f"不支持的 Playwright 步骤动作：{action or '空动作'}")

        if action == "goto":
            target_url = self._resolve_url(context, step)
            logs.append(f"goto {target_url}")
            page.goto(target_url)
            return

        if action == "click":
            selector = self._required_text(step, "selector")
            logs.append(f"click {selector}")
            page.locator(selector).click()
            return

        if action == "fill":
            selector = self._required_text(step, "selector")
            value = str(step.get("value") or "")
            logs.append(f"fill {selector}")
            page.locator(selector).fill(value)
            return

        if action == "expect_text":
            selector = str(step.get("selector") or "body")
            expected_text = self._required_text(step, "text")
            logs.append(f"expect_text {selector}")
            actual_text = page.locator(selector).inner_text()
            if expected_text not in actual_text:
                raise AssertionError(f"元素 {selector} 未包含期望文本：{expected_text}")
            return

        if action == "expect_url":
            expected_contains = self._required_text(step, "contains")
            logs.append(f"expect_url contains {expected_contains}")
            if expected_contains not in page.url:
                raise AssertionError(f"当前 URL 未包含期望片段：{expected_contains}，实际：{page.url}")

    def _resolve_url(self, context: ExecutionContext, step: dict[str, Any]) -> str:
        raw_url = self._required_text(step, "url")
        if raw_url.startswith(("http://", "https://", "data:", "about:")):
            return raw_url

        base_url = str(context.variables.get("BASE_URL") or "").strip()
        if not base_url:
            raise ValueError("Playwright 执行需要项目环境 base_url 或步骤中提供完整 URL")
        return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))

    def _required_text(self, step: dict[str, Any], key: str) -> str:
        value = str(step.get(key) or "").strip()
        if not value:
            raise ValueError(f"Playwright 步骤缺少必填字段：{key}")
        return value

    def _relative_artifact_path(self, context: ExecutionContext, path: Any) -> str:
        if context.artifacts_dir is None:
            return str(path)
        return path.relative_to(context.artifacts_dir).as_posix()

    def _build_summary(self, results: list[CaseExecutionResult]) -> dict[str, int]:
        passed = sum(1 for result in results if result.status == "passed")
        failed = sum(1 for result in results if result.status == "failed")
        skipped = sum(1 for result in results if result.status == "skipped")
        error = sum(1 for result in results if result.status == "error")
        return {"total": len(results), "passed": passed, "failed": failed, "skipped": skipped, "error": error}

    def _build_run_status(self, summary: dict[str, int]) -> str:
        if summary.get("error", 0):
            return "error"
        if summary.get("failed", 0):
            return "failed"
        if summary.get("total", 0) == 0 or summary.get("skipped", 0) == summary.get("total", 0):
            return "skipped"
        return "passed"

    def _build_report(self, context: ExecutionContext, summary: dict[str, int]) -> str:
        environment_name = context.environment.name if context.environment else "未指定"
        base_url = context.variables.get("BASE_URL") or "未提供"
        return (
            f"# Playwright 测试报告：{context.run_name}\n\n"
            f"- 触发方式：{context.trigger_type}\n"
            f"- 环境：{environment_name}\n"
            f"- Base URL：{base_url}\n"
            f"- 分支：{context.branch or '未提供'}\n"
            f"- 提交：{context.commit_sha or '未提供'}\n"
            f"- 总数：{summary['total']}\n"
            f"- 通过：{summary['passed']}\n"
            f"- 失败：{summary['failed']}\n"
            f"- 跳过：{summary['skipped']}\n"
            f"- 错误：{summary['error']}\n\n"
            "当前使用 Playwright 最小执行器，支持 goto、click、fill、expect_text、expect_url。"
        )

    def _dependency_error_result(self, context: ExecutionContext, exc: ImportError) -> ExecutionResult:
        message = f"Playwright 依赖未安装或不可用：{exc}"
        return ExecutionResult(
            status="error",
            summary={"total": len(context.cases), "passed": 0, "failed": 0, "skipped": 0, "error": 1},
            report=f"# Playwright 执行器不可用：{context.run_name}\n\n{message}",
            logs=message,
        )

    def _configuration_error_result(self, context: ExecutionContext, message: str) -> ExecutionResult:
        return ExecutionResult(
            status="error",
            summary={"total": len(context.cases), "passed": 0, "failed": 0, "skipped": 0, "error": 1},
            report=f"# Playwright 配置错误：{context.run_name}\n\n{message}",
            logs=message,
        )
