from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.services.executors.base import CaseExecutionResult, ExecutionContext, ExecutionResult


class ApiExecutor:
    """最小 API 执行器。

    解释受控步骤，不执行任意代码。每个用例内维护最近一次 HTTP 响应，
    后续断言步骤基于该响应校验状态码、JSON 内容或文本内容。
    """

    name = "api"
    supported_case_types = {"api"}
    supported_actions = {"request", "expect_status", "expect_json_contains", "expect_text_contains", "extract_json"}
    variable_pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
    sensitive_keys = {"token", "access_token", "authorization", "password", "pwd", "secret", "api_key", "apikey"}

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        if not context.cases:
            return ExecutionResult(
                status="skipped",
                summary={"total": 0, "passed": 0, "failed": 0, "skipped": 1, "error": 0},
                report="没有找到可执行的 API 测试用例。",
            )

        timeout_seconds = max(1, int(context.config.get("timeout_ms", 30000)) / 1000)
        results: list[CaseExecutionResult] = []
        run_logs: list[str] = []

        with httpx.Client(timeout=timeout_seconds, follow_redirects=bool(context.config.get("follow_redirects", True))) as client:
            for case in context.cases:
                started = perf_counter()
                logs = [f"执行用例：{case.title}", f"类型：{case.type}", f"超时：{int(timeout_seconds * 1000)}ms"]
                status = "passed"
                message = "API 执行通过"
                last_response: httpx.Response | None = None
                variables = dict(context.variables)
                variables["RUN_ID"] = context.run_id
                variables["TIMESTAMP"] = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                variables["SHORT_TS"] = datetime.now(UTC).strftime("%H%M%S")

                try:
                    for step in case.steps or []:
                        last_response = self._execute_step(client, variables, step, last_response, logs)
                except (AssertionError, ValueError, httpx.HTTPError) as exc:
                    status = "failed"
                    message = str(exc)
                    logs.append(f"失败原因：{exc}")

                duration_ms = int((perf_counter() - started) * 1000)
                run_logs.extend(logs)
                results.append(
                    CaseExecutionResult(
                        case_id=case.id,
                        status=status,
                        duration_ms=duration_ms,
                        message=message,
                        logs="\n".join(logs),
                        artifacts=[],
                        metadata={"executor": self.name},
                    )
                )

        summary = self._build_summary(results)
        return ExecutionResult(
            status="failed" if summary["failed"] else "passed",
            case_results=results,
            summary=summary,
            report=self._build_report(context, summary),
            logs="\n".join(run_logs),
        )

    def _execute_step(
        self,
        client: httpx.Client,
        variables: dict[str, Any],
        step: dict[str, Any],
        last_response: httpx.Response | None,
        logs: list[str],
    ) -> httpx.Response | None:
        action = str(step.get("action") or "").strip()
        if action not in self.supported_actions:
            raise ValueError(f"不支持的 API 步骤动作：{action or '空动作'}")

        if action == "request":
            method = str(step.get("method") or "GET").upper()
            url = self._resolve_url(variables, step)
            headers = self._dict_value(self._render_variables(step.get("headers"), variables))
            params = self._dict_value(self._render_variables(step.get("params") or step.get("query"), variables))
            json_body = self._render_variables(step.get("json"), variables)
            data = self._render_variables(step.get("body") or step.get("data") or step.get("form"), variables)
            logs.append(f"request {method} {self._mask_url(url)}")
            response = client.request(method, url, headers=headers, params=params, json=json_body, data=data)
            logs.append(f"response {response.status_code} {response.elapsed.total_seconds() * 1000:.0f}ms")
            logs.append(f"response body: {self._response_excerpt(response)}")
            return response

        if last_response is None:
            raise ValueError(f"{action} 断言前缺少 request 响应")

        if action == "expect_status":
            expected_status = int(step.get("status") or step.get("value") or 200)
            logs.append(f"expect_status {expected_status}")
            if last_response.status_code != expected_status:
                raise AssertionError(f"期望状态码 {expected_status}，实际 {last_response.status_code}")
            return last_response

        if action == "expect_json_contains":
            path = str(step.get("path") or "").strip()
            expected = step.get("value")
            logs.append(f"expect_json_contains {path or '<root>'}={expected!r}")
            actual = self._json_path(last_response.json(), path)
            if not self._matches(actual, expected):
                raise AssertionError(f"JSON 路径 {path or '<root>'} 不符合预期，期望包含 {expected!r}，实际 {actual!r}")
            return last_response

        if action == "expect_text_contains":
            expected_text = str(step.get("text") or step.get("value") or "").strip()
            if not expected_text:
                raise ValueError("expect_text_contains 缺少 text 或 value")
            logs.append(f"expect_text_contains {expected_text}")
            if expected_text not in last_response.text:
                raise AssertionError(f"响应文本未包含期望内容：{expected_text}")
            return last_response

        if action == "extract_json":
            path = str(step.get("path") or "").strip()
            variable_name = str(step.get("as") or step.get("name") or "").strip()
            if not variable_name:
                raise ValueError("extract_json 缺少 as 或 name")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable_name):
                raise ValueError(f"变量名不合法：{variable_name}")
            actual = self._json_path(last_response.json(), path)
            variables[variable_name] = actual
            logs.append(f"extract_json {path or '<root>'} -> ${{{variable_name}}}={self._safe_value(actual)}")
            return last_response

        return last_response

    def _resolve_url(self, variables: dict[str, Any], step: dict[str, Any]) -> str:
        raw_url = str(self._render_variables(step.get("url") or "", variables)).strip()
        if not raw_url:
            raise ValueError("request 步骤缺少 url")
        if raw_url.startswith(("http://", "https://")):
            return raw_url
        base_url = str(variables.get("BASE_URL") or "").strip()
        if not base_url:
            raise ValueError("API 执行需要项目环境 base_url 或步骤中提供完整 URL")
        if raw_url == "/":
            return base_url
        if raw_url.startswith("?"):
            return f"{base_url}{raw_url}"
        return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))

    def _render_variables(self, value: Any, variables: dict[str, Any]) -> Any:
        if isinstance(value, str):
            full_match = self.variable_pattern.fullmatch(value)
            if full_match:
                name = full_match.group(1)
                if name not in variables:
                    raise ValueError(f"变量未定义：{name}")
                return variables[name]

            def replace(match: re.Match[str]) -> str:
                name = match.group(1)
                if name not in variables:
                    raise ValueError(f"变量未定义：{name}")
                return str(variables[name])

            return self.variable_pattern.sub(replace, value)
        if isinstance(value, list):
            return [self._render_variables(item, variables) for item in value]
        if isinstance(value, dict):
            return {key: self._render_variables(item, variables) for key, item in value.items()}
        return value

    def _dict_value(self, value: Any) -> dict[str, Any] | None:
        return value if isinstance(value, dict) else None

    def _response_excerpt(self, response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")
        text = response.text
        if "application/json" in content_type:
            try:
                text = self._mask_sensitive(response.json()).__repr__()
            except ValueError:
                pass
        return text[:1000]

    def _mask_sensitive(self, value: Any) -> Any:
        if isinstance(value, dict):
            masked = {}
            for key, item in value.items():
                if str(key).lower() in self.sensitive_keys:
                    masked[key] = self._safe_value(item)
                else:
                    masked[key] = self._mask_sensitive(item)
            return masked
        if isinstance(value, list):
            return [self._mask_sensitive(item) for item in value]
        return value

    def _safe_value(self, value: Any) -> str:
        text = str(value)
        if not text:
            return "<empty>"
        if len(text) <= 8:
            return "***"
        return f"{text[:4]}...{text[-4:]}"

    def _mask_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if not parsed.query:
            return url
        masked_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            masked_query.append((key, self._safe_value(value) if key.lower() in self.sensitive_keys else value))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(masked_query), parsed.fragment))

    def _json_path(self, data: Any, path: str) -> Any:
        current = data
        if not path:
            return current
        for part in path.split("."):
            if isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise AssertionError(f"JSON 路径不存在：{path}")
        return current

    def _matches(self, actual: Any, expected: Any) -> bool:
        if isinstance(actual, dict) and isinstance(expected, dict):
            return all(key in actual and self._matches(actual[key], value) for key, value in expected.items())
        if isinstance(actual, list):
            return expected in actual
        return actual == expected

    def _build_summary(self, results: list[CaseExecutionResult]) -> dict[str, int]:
        passed = sum(1 for result in results if result.status == "passed")
        failed = sum(1 for result in results if result.status == "failed")
        return {"total": len(results), "passed": passed, "failed": failed, "skipped": 0, "error": 0}

    def _build_report(self, context: ExecutionContext, summary: dict[str, int]) -> str:
        environment_name = context.environment.name if context.environment else "未指定"
        base_url = context.variables.get("BASE_URL") or "未提供"
        return (
            f"# API 测试报告：{context.run_name}\n\n"
            f"- 触发方式：{context.trigger_type}\n"
            f"- 环境：{environment_name}\n"
            f"- Base URL：{base_url}\n"
            f"- 总数：{summary['total']}\n"
            f"- 通过：{summary['passed']}\n"
            f"- 失败：{summary['failed']}\n\n"
            "当前使用最小 API 执行器，支持 request、extract_json、expect_status、expect_json_contains、expect_text_contains。"
        )
