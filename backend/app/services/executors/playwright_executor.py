from __future__ import annotations

import json
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
    supported_actions = {"goto", "click", "fill", "press", "expect_text", "expect_url"}

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
        timeout_ms = int(context.config.get("timeout_ms", 30000))
        wait_until = str(context.config.get("wait_until", "domcontentloaded"))
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
                    page.set_default_navigation_timeout(timeout_ms)
                    logs: list[str] = [
                        f"执行用例：{case.title}",
                        f"浏览器：{browser_name}",
                        f"超时：{timeout_ms}ms",
                        f"导航等待：{wait_until}",
                    ]
                    artifacts: list[str] = []
                    status = "passed"
                    message = "Playwright 执行通过"

                    try:
                        for step in case.steps:
                            self._execute_step(page, context, step, logs, wait_until)
                            self._raise_if_known_blocked_page(page)
                    except (AssertionError, PlaywrightTimeoutError, PlaywrightError, ValueError) as exc:
                        status = "failed"
                        message = str(exc)
                        logs.append(f"失败原因：{exc}")
                        evidence = self._collect_failure_evidence(page, case.steps, str(exc))
                        logs.extend(self._format_evidence_logs(evidence))
                        if screenshot_on_failure and case_dir:
                            screenshot_path = case_dir / "failure.png"
                            page.screenshot(path=str(screenshot_path), full_page=True)
                            artifacts.append(self._relative_artifact_path(context, screenshot_path))
                            logs.append(f"失败截图：{artifacts[-1]}")
                        if case_dir:
                            evidence_path = case_dir / "failure-evidence.json"
                            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                            artifacts.append(self._relative_artifact_path(context, evidence_path))
                            logs.append(f"失败证据：{artifacts[-1]}")
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

    def _execute_step(
        self,
        page: Any,
        context: ExecutionContext,
        step: dict[str, Any],
        logs: list[str],
        wait_until: str,
    ) -> None:
        action = str(step.get("action") or "").strip()
        if action not in self.supported_actions:
            raise ValueError(f"不支持的 Playwright 步骤动作：{action or '空动作'}")

        if action == "goto":
            target_url = self._resolve_url(context, step)
            logs.append(f"goto {target_url}")
            page.goto(target_url, wait_until=wait_until)
            return

        if action == "click":
            locator, selector = self._resolve_action_locator(page, step, logs, editable=False)
            logs.append(f"click {selector}")
            locator.click()
            self._settle_after_interaction(page, logs)
            return

        if action == "fill":
            locator, selector = self._resolve_action_locator(page, step, logs, editable=True)
            value = str(step.get("value") or "")
            logs.append(f"fill {selector}")
            locator.fill(value)
            return

        if action == "press":
            locator, selector = self._resolve_action_locator(page, step, logs, editable=False)
            key = str(step.get("key") or "Enter").strip()
            logs.append(f"press {selector} {key}")
            locator.press(key)
            self._settle_after_interaction(page, logs)
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

    def _resolve_action_locator(
        self,
        page: Any,
        step: dict[str, Any],
        logs: list[str],
        editable: bool,
    ) -> tuple[Any, str]:
        selectors = self._selector_candidates(step)
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                count = 0
            if count <= 0:
                continue

            for index in range(count):
                candidate = locator.nth(index)
                try:
                    is_ready = candidate.is_visible(timeout=500) and candidate.is_enabled(timeout=500)
                    if editable:
                        is_ready = is_ready and candidate.is_editable(timeout=500)
                    if is_ready:
                        if selector != selectors[0] or index > 0:
                            logs.append(f"selector fallback {selectors[0]} -> {selector}[{index}]")
                        return candidate, selector
                except Exception:
                    continue

        raise ValueError(f"没有找到可见且可操作的元素，候选 selector：{', '.join(selectors)}")

    def _selector_candidates(self, step: dict[str, Any]) -> list[str]:
        primary = self._required_text(step, "selector")
        selectors = [primary]
        raw_candidates = step.get("selector_candidates")
        if isinstance(raw_candidates, list):
            selectors.extend(str(item).strip() for item in raw_candidates if str(item).strip())

        selectors.extend(self._built_in_selector_fallbacks(primary))
        return list(dict.fromkeys(selectors))

    def _built_in_selector_fallbacks(self, selector: str) -> list[str]:
        if selector == "#kw":
            return ["#chat-textarea", "textarea[name='wd']", "textarea.chat-input-textarea"]
        if selector == "#su":
            return ["#chat-submit-button", "button:has-text('百度一下')", "input[type='submit'][value='百度一下']"]
        return []

    def _settle_after_interaction(self, page: Any, logs: list[str]) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            logs.append("wait domcontentloaded after interaction")
        except Exception:
            page.wait_for_timeout(1000)
            logs.append("wait 1000ms after interaction")

    def _raise_if_known_blocked_page(self, page: Any) -> None:
        if "wappass.baidu.com/static/captcha" in page.url:
            raise AssertionError("百度返回了安全验证页面，公开站点存在反自动化拦截，建议改用可控测试站点或人工完成验证后复用浏览器会话。")
        try:
            body_text = page.locator("body").inner_text(timeout=1000)
        except Exception:
            return
        if "百度安全验证" in body_text and "请完成下方验证" in body_text:
            raise AssertionError("百度返回了安全验证页面，公开站点存在反自动化拦截，建议改用可控测试站点或人工完成验证后复用浏览器会话。")

    def _collect_failure_evidence(self, page: Any, steps: list[dict[str, Any]], error: str) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "error": error,
            "url": self._safe_page_value(lambda: page.url),
            "title": self._safe_page_value(page.title),
            "body_text_excerpt": self._safe_body_text(page),
            "visible_elements": self._visible_elements_snapshot(page),
            "step_selectors": self._step_selector_diagnostics(page, steps),
        }
        return evidence

    def _visible_elements_snapshot(self, page: Any) -> dict[str, list[dict[str, Any]]]:
        selectors = {
            "inputs": "input, textarea, [contenteditable='true']",
            "buttons": "button, input[type='button'], input[type='submit'], [role='button']",
            "links": "a[href]",
        }
        return {
            name: self._element_summaries(page, selector, limit=12)
            for name, selector in selectors.items()
        }

    def _element_summaries(self, page: Any, selector: str, limit: int) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        try:
            locator = page.locator(selector)
            count = min(locator.count(), limit)
        except Exception:
            return elements

        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible(timeout=200):
                    continue
                elements.append(
                    {
                        "tag": self._safe_locator_value(lambda: item.evaluate("el => el.tagName.toLowerCase()")),
                        "id": self._safe_locator_value(lambda: item.get_attribute("id")),
                        "name": self._safe_locator_value(lambda: item.get_attribute("name")),
                        "type": self._safe_locator_value(lambda: item.get_attribute("type")),
                        "role": self._safe_locator_value(lambda: item.get_attribute("role")),
                        "placeholder": self._safe_locator_value(lambda: item.get_attribute("placeholder")),
                        "aria_label": self._safe_locator_value(lambda: item.get_attribute("aria-label")),
                        "text": self._truncate(self._safe_locator_value(lambda: item.inner_text(timeout=200)), 120),
                    }
                )
            except Exception:
                continue
        return elements

    def _step_selector_diagnostics(self, page: Any, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        for step in steps:
            selector = str(step.get("selector") or "").strip()
            if not selector:
                continue
            selectors = self._selector_candidates(step)
            checks = []
            for candidate_selector in selectors[:8]:
                locator = page.locator(candidate_selector)
                try:
                    count = locator.count()
                    first = locator.first()
                    checks.append(
                        {
                            "selector": candidate_selector,
                            "count": count,
                            "visible": bool(count and first.is_visible(timeout=200)),
                            "enabled": bool(count and first.is_enabled(timeout=200)),
                            "editable": bool(count and first.is_editable(timeout=200)),
                        }
                    )
                except Exception as exc:
                    checks.append({"selector": candidate_selector, "error": str(exc)[:200]})
            diagnostics.append({"order": step.get("order"), "action": step.get("action"), "selector": selector, "candidates": checks})
        return diagnostics

    def _format_evidence_logs(self, evidence: dict[str, Any]) -> list[str]:
        lines = [
            f"页面 URL：{evidence.get('url') or '未知'}",
            f"页面标题：{evidence.get('title') or '未知'}",
        ]
        visible = evidence.get("visible_elements") if isinstance(evidence.get("visible_elements"), dict) else {}
        for group_name in ("inputs", "buttons"):
            items = visible.get(group_name) if isinstance(visible, dict) else []
            if items:
                labels = [
                    self._element_label(item)
                    for item in items[:5]
                    if isinstance(item, dict)
                ]
                lines.append(f"可见 {group_name}：{'；'.join(labels)}")
        return lines

    def _element_label(self, item: dict[str, Any]) -> str:
        identity = item.get("id") or item.get("name") or item.get("placeholder") or item.get("aria_label") or item.get("text") or item.get("tag")
        return str(identity)[:80]

    def _safe_page_value(self, getter: Any) -> str | None:
        try:
            value = getter()
            return self._truncate(str(value), 500)
        except Exception:
            return None

    def _safe_locator_value(self, getter: Any) -> str | None:
        try:
            value = getter()
            if value is None:
                return None
            return str(value)
        except Exception:
            return None

    def _safe_body_text(self, page: Any) -> str:
        try:
            return self._truncate(page.locator("body").inner_text(timeout=1000), 2000)
        except Exception:
            return ""

    def _truncate(self, value: str | None, limit: int) -> str:
        text = (value or "").strip()
        return text[:limit]

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
