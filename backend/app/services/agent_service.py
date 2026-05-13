from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.schemas import TestCaseCreate
from app.services.api_doc_parser import ApiDocParser, ApiEndpointSpec
from app.services.llm_service import get_deepseek_chat_model


class TestCaseAgent:
    """测试用例生成 Agent。

    当前 Agent 使用 langchain-deepseek 的 ChatDeepSeek 生成结构化测试用例。
    如果大模型不可用、返回格式不正确或没有配置密钥，会自动回退到规则生成。
    """

    def generate_cases(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None = None,
        skill_context: str = "暂无可用测试 skill 知识。",
    ) -> list[TestCaseCreate]:
        llm_cases = self._generate_with_deepseek_agent(project_id, content, requirement_id, skill_context)
        if llm_cases:
            llm_cases = self._ensure_required_rule_cases(project_id, content, requirement_id, llm_cases)
            return self.review_cases(content, llm_cases, skill_context)
        rule_cases = self._generate_with_rules(project_id, content, requirement_id, skill_context)
        return self._review_cases_with_rules(content, rule_cases)

    def _ensure_required_rule_cases(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None,
        cases: list[TestCaseCreate],
    ) -> list[TestCaseCreate]:
        if self._looks_like_shopxo_cart_requirement(content) and not self._has_executable_api_case(cases):
            return [self._shopxo_login_cart_case(project_id, requirement_id, content), *cases]
        if self._looks_like_api_requirement(content) and not self._has_executable_api_case(cases):
            return [
                *self._generate_api_cases(project_id, content, requirement_id, self._extract_features(content), ""),
                *cases,
            ]
        return cases

    def _has_executable_api_case(self, cases: list[TestCaseCreate]) -> bool:
        for case in cases:
            if case.type != "api":
                continue
            actions = {str(step.get("action", "")).strip() for step in case.steps if isinstance(step, dict)}
            if "request" in actions and (actions & {"expect_status", "expect_json_contains", "expect_text_contains"}):
                return True
        return False

    def _generate_with_deepseek_agent(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None,
        skill_context: str,
    ) -> list[TestCaseCreate]:
        model = get_deepseek_chat_model(temperature=0.2)
        if model is None:
            return []

        messages = [
            SystemMessage(
                content=(
                    "你是 AITestHub 平台中的测试用例生成 Agent。"
                    "你负责把需求文档、自然语言描述或功能说明拆解成可人工审核的测试用例。"
                    "你必须优先参考输入中的测试 skill 知识，但不得编造需求未出现的功能。"
                    "如果测试 skill 知识中包含 selector_strategy、execution_failure、site_compatibility 或 anti_pattern，"
                    "这些内容必须作为生成约束：已知不可见、失效或不稳定的 selector 不要作为唯一选择器；"
                    "必须为 Web UI 步骤补充 selector_candidates，并优先选择可见、可编辑、可点击的元素。"
                    "如果知识提示公开第三方站点存在安全验证、反自动化或 DOM 变更风险，"
                    "需要在前置条件、预期结果或 tags 中标记该风险，不要承诺结果页一定稳定出现。"
                    "如果知识是 anti_pattern，除非需求明确要求，否则应避免重复生成类似问题。"
                    "当需求描述页面点击、输入框、搜索框、按钮、页面跳转、文案校验等浏览器操作时，"
                    "必须生成 type=web_ui 的用例，并使用 Playwright 受控步骤："
                    "goto、click、fill、press、expect_text、expect_url。"
                    "web_ui 步骤字段示例："
                    "{\"order\":1,\"action\":\"goto\",\"url\":\"/\"},"
                    "{\"order\":2,\"action\":\"fill\",\"selector\":\"#kw\","
                    "\"selector_candidates\":[\"#chat-textarea\",\"textarea.chat-input-textarea\"],"
                    "\"value\":\"井冈山大学\"},"
                    "{\"order\":3,\"action\":\"click\",\"selector\":\"#su\","
                    "\"selector_candidates\":[\"#chat-submit-button\",\"button:has-text('百度一下')\"]},"
                    "{\"order\":4,\"action\":\"press\",\"selector\":\"#kw\","
                    "\"selector_candidates\":[\"#chat-textarea\",\"textarea.chat-input-textarea\"],"
                    "\"key\":\"Enter\"},"
                    "{\"order\":5,\"action\":\"expect_text\",\"selector\":\"body\",\"text\":\"井冈山大学\"}。"
                    "当需求描述接口、HTTP、请求、响应、状态码时，生成 type=api。"
                    "api 步骤必须使用受控动作：request、extract_json、expect_status、expect_json_contains、expect_text_contains。"
                    "需要登录态串联时，用 extract_json 从响应提取 token，再在后续请求中用 ${token} 引用。"
                    "必须只返回 JSON，不要返回 Markdown，不要解释。"
                    "JSON 格式为："
                    "{\"cases\":[{\"title\":\"\",\"type\":\"functional|api|web_ui|regression|security\","
                    "\"priority\":\"P0|P1|P2|P3\",\"preconditions\":\"\","
                    "\"steps\":[{\"order\":1,\"action\":\"\"}],"
                    "\"expected_result\":\"\",\"tags\":[\"\"]}]}"
                )
            ),
            HumanMessage(
                content=(
                    "请基于以下需求生成测试用例。要求覆盖：正常流程、异常流程、边界条件、权限/安全、"
                    "数据一致性、回归风险。每条用例步骤要具体，预期结果必须可验证。\n\n"
                    f"可用测试 skill 知识：\n{skill_context}\n\n"
                    f"需求：\n{content}"
                )
            ),
        ]

        try:
            response = model.invoke(messages)
            parsed = self._extract_json(str(response.content))
            return self._parse_llm_cases(project_id, requirement_id, parsed)
        except Exception:
            return []

    def _extract_json(self, raw_content: str) -> dict[str, Any]:
        text = raw_content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    def _parse_llm_cases(
        self,
        project_id: int,
        requirement_id: int | None,
        parsed: dict[str, Any],
    ) -> list[TestCaseCreate]:
        raw_cases = parsed.get("cases")
        if not isinstance(raw_cases, list):
            return []

        cases: list[TestCaseCreate] = []
        for item in raw_cases[:12]:
            case_type = self._normalize_case_type(str(item.get("type") or "functional"), item.get("steps"))
            steps = self._normalize_steps(item.get("steps"), case_type)
            if not steps:
                continue

            cases.append(
                TestCaseCreate(
                    project_id=project_id,
                    requirement_id=requirement_id,
                    title=str(item.get("title") or "未命名测试用例")[:240],
                    type=case_type,
                    priority=self._normalize_priority(str(item.get("priority") or "P2")),
                    status="draft",
                    preconditions=str(item.get("preconditions") or "测试环境和测试数据已准备完成。"),
                    steps=steps,
                    expected_result=str(item.get("expected_result") or "实际结果符合需求预期。"),
                    tags=self._normalize_tags(item.get("tags")),
                    generated_by="deepseek-agent",
                    ai_review={},
                )
            )
        return cases

    def _normalize_steps(self, value: Any, case_type: str = "functional") -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        steps = []
        for index, step in enumerate(value, start=1):
            if isinstance(step, dict):
                if case_type == "web_ui":
                    normalized_step = self._normalize_web_ui_step(step, index)
                    if normalized_step:
                        steps.append(normalized_step)
                    continue
                if case_type == "api":
                    normalized_step = self._normalize_api_step(step, index)
                    if normalized_step:
                        steps.append(normalized_step)
                    continue
                action = str(step.get("action", "")).strip()
            else:
                action = str(step).strip()
            if action:
                steps.append({"order": index, "action": action})
        return steps

    def _normalize_web_ui_step(self, step: dict[str, Any], index: int) -> dict[str, Any] | None:
        action = str(step.get("action", "")).strip()
        if action not in {"goto", "click", "fill", "press", "expect_text", "expect_url"}:
            return None

        result: dict[str, Any] = {"order": int(step.get("order") or index), "action": action}
        for key in ("url", "selector", "value", "key", "text", "contains"):
            if step.get(key) is not None and str(step.get(key)).strip():
                result[key] = str(step.get(key)).strip()
        if isinstance(step.get("selector_candidates"), list):
            candidates = [str(item).strip() for item in step["selector_candidates"] if str(item).strip()]
            if candidates:
                result["selector_candidates"] = candidates[:8]
        return result

    def _normalize_api_step(self, step: dict[str, Any], index: int) -> dict[str, Any] | None:
        action = str(step.get("action", "")).strip()
        if action not in {"request", "extract_json", "expect_status", "expect_json_contains", "expect_text_contains"}:
            return None

        result: dict[str, Any] = {"order": int(step.get("order") or index), "action": action}
        if action == "request":
            result["method"] = str(step.get("method") or "GET").upper()
            if step.get("url") is None or not str(step.get("url")).strip():
                return None
            result["url"] = str(step.get("url")).strip()
            for key in ("headers", "params", "query", "json", "body", "data", "form"):
                if key in step:
                    result[key] = step[key]
            return result
        if action == "extract_json":
            if step.get("path") is None or step.get("as") is None:
                return None
            result["path"] = str(step.get("path")).strip()
            result["as"] = str(step.get("as")).strip()
            return result
        if action == "expect_status":
            result["status"] = int(step.get("status") or step.get("value") or 200)
            return result
        if action == "expect_json_contains":
            result["path"] = str(step.get("path") or "").strip()
            result["value"] = step.get("value")
            return result
        if action == "expect_text_contains":
            text = str(step.get("text") or step.get("value") or "").strip()
            if not text:
                return None
            result["text"] = text
            return result
        return None

    def _normalize_case_type(self, value: str, steps: Any = None) -> str:
        normalized = value.strip().lower().replace("-", "_")
        aliases = {"ui": "web_ui", "web": "web_ui", "webui": "web_ui", "interface": "api"}
        normalized = aliases.get(normalized, normalized)

        if normalized not in {"functional", "api", "web_ui", "regression", "security", "manual"}:
            normalized = "functional"

        if isinstance(steps, list):
            actions = {str(step.get("action", "")).strip() for step in steps if isinstance(step, dict)}
            if actions & {"goto", "click", "fill", "press", "expect_text", "expect_url"}:
                return "web_ui"
            if actions & {"request", "extract_json", "expect_status", "expect_json_contains", "expect_text_contains"}:
                return "api"

        return normalized

    def _normalize_priority(self, priority: str) -> str:
        return priority if priority in {"P0", "P1", "P2", "P3"} else "P2"

    def _normalize_tags(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item)[:40] for item in value if str(item).strip()][:8]
        if isinstance(value, str) and value.strip():
            return [value.strip()[:40]]
        return ["agent-generated"]

    def _generate_with_rules(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None = None,
        skill_context: str = "",
    ) -> list[TestCaseCreate]:
        features = self._extract_features(content)
        if self._looks_like_web_ui_requirement(content):
            return self._generate_web_ui_cases(project_id, content, requirement_id, features)
        if self._looks_like_api_requirement(content):
            return self._generate_api_cases(project_id, content, requirement_id, features, skill_context)

        cases: list[TestCaseCreate] = []

        for index, feature in enumerate(features, start=1):
            cases.append(
                TestCaseCreate(
                    project_id=project_id,
                    requirement_id=requirement_id,
                    title=f"验证{feature}的正常流程",
                    type="functional",
                    priority="P1" if index == 1 else "P2",
                    status="draft",
                    preconditions="测试环境可访问，测试账号和基础数据已准备完成。",
                    steps=[
                        {"order": 1, "action": f"进入与“{feature}”相关的功能页面或接口。"},
                        {"order": 2, "action": "输入一组合法数据并提交。"},
                        {"order": 3, "action": "检查页面反馈、接口响应和数据落库结果。"},
                    ],
                    expected_result=f"{feature}可以按需求完成，响应状态、页面提示和数据状态均正确。",
                    tags=["agent-generated", "happy-path"],
                    generated_by="agent",
                    ai_review={},
                )
            )
            cases.append(
                TestCaseCreate(
                    project_id=project_id,
                    requirement_id=requirement_id,
                    title=f"验证{feature}的异常输入处理",
                    type="functional",
                    priority="P2",
                    status="draft",
                    preconditions="测试环境可访问，准备空值、超长值、非法格式等异常数据。",
                    steps=[
                        {"order": 1, "action": f"进入与“{feature}”相关的功能入口。"},
                        {"order": 2, "action": "分别提交空值、非法格式、重复数据或越权数据。"},
                        {"order": 3, "action": "观察错误提示、接口状态码和数据是否被错误写入。"},
                    ],
                    expected_result="系统给出明确错误提示，拒绝非法数据，不产生脏数据或越权结果。",
                    tags=["agent-generated", "negative"],
                    generated_by="agent",
                    ai_review={},
                )
            )

        cases.append(self._regression_case(project_id, requirement_id))
        return cases

    def _generate_web_ui_cases(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None,
        features: list[str],
    ) -> list[TestCaseCreate]:
        query = self._extract_quoted_text(content) or "测试关键词"
        feature = features[0] if features else content[:40]
        return [
            TestCaseCreate(
                project_id=project_id,
                requirement_id=requirement_id,
                title=f"验证页面搜索“{query}”",
                type="web_ui",
                priority="P1",
                status="draft",
                preconditions="已配置被测站点环境，搜索页面可访问。",
                steps=[
                    {"order": 1, "action": "goto", "url": "/"},
                    {
                        "order": 2,
                        "action": "fill",
                        "selector": "#kw",
                        "selector_candidates": ["#chat-textarea", "textarea.chat-input-textarea"],
                        "value": query,
                    },
                    {
                        "order": 3,
                        "action": "click",
                        "selector": "#su",
                        "selector_candidates": ["#chat-submit-button", "button:has-text('百度一下')"],
                    },
                    {
                        "order": 4,
                        "action": "press",
                        "selector": "#kw",
                        "selector_candidates": ["#chat-textarea", "textarea.chat-input-textarea"],
                        "key": "Enter",
                    },
                    {"order": 5, "action": "expect_text", "selector": "body", "text": query},
                ],
                expected_result=f"页面展示与“{query}”相关的搜索结果或反馈信息。",
                tags=["agent-generated", "web-ui", "playwright"],
                generated_by="agent",
                ai_review={},
            ),
            TestCaseCreate(
                project_id=project_id,
                requirement_id=requirement_id,
                title=f"验证{feature}页面基础可访问",
                type="web_ui",
                priority="P2",
                status="draft",
                preconditions="已配置被测站点环境。",
                steps=[
                    {"order": 1, "action": "goto", "url": "/"},
                    {"order": 2, "action": "expect_text", "selector": "body", "text": query},
                ],
                expected_result="页面可正常加载，关键文案或搜索关键词可被验证。",
                tags=["agent-generated", "web-ui"],
                generated_by="agent",
                ai_review={},
            ),
        ]

    def _generate_api_cases(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None,
        features: list[str],
        skill_context: str = "",
    ) -> list[TestCaseCreate]:
        feature = features[0] if features else "接口能力"
        parsed_case = self._generate_api_case_from_doc(project_id, content, requirement_id, skill_context)
        if parsed_case is not None:
            return [parsed_case]
        if self._looks_like_shopxo_cart_requirement(content):
            return [self._shopxo_login_cart_case(project_id, requirement_id, content)]
        return [
            TestCaseCreate(
                project_id=project_id,
                requirement_id=requirement_id,
                title=f"验证{feature}接口正常响应",
                type="api",
                priority="P1",
                status="draft",
                preconditions="接口服务可访问，鉴权和测试数据已准备完成。",
                steps=[
                    {"order": 1, "action": "request", "method": "GET", "url": "/"},
                    {"order": 2, "action": "expect_status", "status": 200},
                ],
                expected_result="接口返回成功状态，响应结构和业务数据符合需求。",
                tags=["agent-generated", "api"],
                generated_by="agent",
                ai_review={},
            )
        ]

    def _generate_api_case_from_doc(
        self,
        project_id: int,
        content: str,
        requirement_id: int | None,
        skill_context: str,
    ) -> TestCaseCreate | None:
        doc_text = f"{content}\n\n{skill_context}"
        parser = ApiDocParser()
        login_endpoint = parser.find(doc_text, ["login"]) or parser.find(doc_text, ["登录"])
        target_endpoint = self._find_target_endpoint(parser, doc_text, content)
        register_endpoint = self._find_register_endpoint(parser, doc_text, content)
        if register_endpoint is not None and login_endpoint is not None:
            return self._registration_then_login_case(project_id, requirement_id, register_endpoint, login_endpoint)
        if target_endpoint is None:
            return None

        steps: list[dict[str, Any]] = []
        if login_endpoint is not None and login_endpoint.path != target_endpoint.path:
            steps.extend(self._endpoint_request_steps(login_endpoint, order_start=1, auth=False))
            steps.append({"order": len(steps) + 1, "action": "expect_status", "status": 200})
            steps.append({"order": len(steps) + 1, "action": "expect_json_contains", "path": "code", "value": 0})
            steps.append({"order": len(steps) + 1, "action": "extract_json", "path": "data.token", "as": "token"})

        steps.extend(self._endpoint_request_steps(target_endpoint, order_start=len(steps) + 1, auth=login_endpoint is not None))
        steps.append({"order": len(steps) + 1, "action": "expect_status", "status": 200})
        steps.append({"order": len(steps) + 1, "action": "expect_json_contains", "path": "code", "value": 0})

        title = f"验证{target_endpoint.name}接口正常响应"
        if login_endpoint is not None and login_endpoint.path != target_endpoint.path:
            title = f"验证登录后{target_endpoint.name}接口正常响应"
        return TestCaseCreate(
            project_id=project_id,
            requirement_id=requirement_id,
            title=title,
            type="api",
            priority="P1",
            status="draft",
            preconditions="已配置接口测试环境，账号密码等敏感数据通过环境变量提供。",
            steps=steps,
            expected_result="接口返回 HTTP 200 且业务 code=0，响应结构符合接口文档。",
            tags=["agent-generated", "api", "api-doc"],
            generated_by="agent",
            ai_review={},
        )

    def _find_target_endpoint(self, parser: ApiDocParser, doc_text: str, content: str) -> ApiEndpointSpec | None:
        if any(keyword in content for keyword in ["购物车", "加购", "加入购物车", "cart"]):
            cart_save = self._find_endpoint_by_path(parser, doc_text, "api/cart/save")
            return cart_save or parser.find(doc_text, ["cart", "save"]) or parser.find(doc_text, ["购物车"])
        features = self._extract_features(content)
        for feature in features:
            endpoint = parser.find(doc_text, [feature[:12]])
            if endpoint is not None and "login" not in endpoint.path.lower():
                return endpoint
        endpoints = [endpoint for endpoint in parser.parse(doc_text) if "login" not in endpoint.path.lower()]
        return endpoints[0] if endpoints else None

    def _find_register_endpoint(self, parser: ApiDocParser, doc_text: str, content: str) -> ApiEndpointSpec | None:
        if not any(keyword in content for keyword in ["注册", "register", "reg"]):
            return None
        exact = self._find_endpoint_by_path(parser, doc_text, "api/user/reg")
        if exact is not None:
            return exact
        for endpoint in parser.parse(doc_text):
            normalized_path = endpoint.path.lower()
            if "user" in normalized_path and ("reg" in normalized_path or "register" in normalized_path):
                return endpoint
        return ApiEndpointSpec(name="reg", path="api/user/reg", method="POST", request_example={})

    def _registration_then_login_case(
        self,
        project_id: int,
        requirement_id: int | None,
        register_endpoint: ApiEndpointSpec,
        login_endpoint: ApiEndpointSpec,
    ) -> TestCaseCreate:
        register_step = self._endpoint_request_steps(register_endpoint, order_start=1, auth=False)[0]
        register_step["json"] = {
            "accounts": "${SHOPXO_USERNAME}_${SHORT_TS}",
            "pwd": "${SHOPXO_PASSWORD}",
            "type": "username",
        }
        login_step = self._endpoint_request_steps(login_endpoint, order_start=4, auth=False)[0]
        login_step["json"] = {
            "accounts": "${SHOPXO_USERNAME}_${SHORT_TS}",
            "pwd": "${SHOPXO_PASSWORD}",
            "type": "username",
        }
        return TestCaseCreate(
            project_id=project_id,
            requirement_id=requirement_id,
            title="验证注册成功后可以正常登录",
            type="api",
            priority="P1",
            status="draft",
            preconditions="已配置接口测试环境，账号前缀和密码通过环境变量提供；执行时会追加短时间戳避免重复注册。",
            steps=[
                register_step,
                {"order": 2, "action": "expect_status", "status": 200},
                {"order": 3, "action": "expect_json_contains", "path": "code", "value": 0},
                login_step,
                {"order": 5, "action": "expect_status", "status": 200},
                {"order": 6, "action": "expect_json_contains", "path": "code", "value": 0},
                {"order": 7, "action": "extract_json", "path": "data.token", "as": "token"},
            ],
            expected_result="注册接口返回 code=0，随后使用同一账号密码登录成功并返回 token。",
            tags=["agent-generated", "api", "api-doc", "registration"],
            generated_by="agent",
            ai_review={},
        )

    def _find_endpoint_by_path(self, parser: ApiDocParser, doc_text: str, path: str) -> ApiEndpointSpec | None:
        normalized_path = path.lower().strip("/")
        for endpoint in parser.parse(doc_text):
            if endpoint.path.lower().strip("/") == normalized_path:
                return endpoint
        return None

    def _endpoint_request_steps(self, endpoint: ApiEndpointSpec, order_start: int, auth: bool) -> list[dict[str, Any]]:
        params = self._default_api_params(endpoint.path)
        if auth:
            params["token"] = "${token}"
        body = self._prepared_request_body(endpoint)
        step: dict[str, Any] = {
            "order": order_start,
            "action": "request",
            "method": endpoint.method,
            "url": "/",
            "params": params,
        }
        if body:
            step["json"] = body
        return [step]

    def _default_api_params(self, path: str) -> dict[str, Any]:
        return {
            "application": "app",
            "application_client_type": "weixin",
            "ajax": "ajax",
            "s": path,
        }

    def _prepared_request_body(self, endpoint: ApiEndpointSpec) -> dict[str, Any]:
        body = dict(endpoint.request_example)
        if "accounts" in body:
            body["accounts"] = "${SHOPXO_USERNAME}"
        if "username" in body:
            body["username"] = "${SHOPXO_USERNAME}"
        if "pwd" in body:
            body["pwd"] = "${SHOPXO_PASSWORD}"
        if "password" in body:
            body["password"] = "${SHOPXO_PASSWORD}"
        body.pop("verify", None)
        return body

    def _looks_like_shopxo_cart_requirement(self, content: str) -> bool:
        return all(keyword in content for keyword in ["登录", "购物车"]) or all(
            keyword in content for keyword in ["login", "cart"]
        )

    def _shopxo_login_cart_case(
        self,
        project_id: int,
        requirement_id: int | None,
        content: str = "",
    ) -> TestCaseCreate:
        common_params = {
            "application": "app",
            "application_client_type": "weixin",
            "ajax": "ajax",
        }
        return TestCaseCreate(
            project_id=project_id,
            requirement_id=requirement_id,
            title="验证华测商城登录后加入购物车",
            type="api",
            priority="P1",
            status="draft",
            preconditions="华测商城接口服务可访问，测试账号和商品规格数据已准备完成。",
            steps=[
                {
                    "order": 1,
                    "action": "request",
                    "method": "POST",
                    "url": "/",
                    "params": {**common_params, "s": "api/user/login"},
                    "json": {"accounts": "${SHOPXO_USERNAME}", "pwd": "${SHOPXO_PASSWORD}", "type": "username"},
                },
                {"order": 2, "action": "expect_status", "status": 200},
                {"order": 3, "action": "expect_json_contains", "path": "code", "value": 0},
                {"order": 4, "action": "extract_json", "path": "data.token", "as": "token"},
                {
                    "order": 5,
                    "action": "request",
                    "method": "POST",
                    "url": "/",
                    "params": {**common_params, "s": "api/cart/save", "token": "${token}"},
                    "json": {
                        "goods_id": "2",
                        "spec": [
                            {"type": "套餐", "value": "套餐二"},
                            {"type": "颜色", "value": "银色"},
                            {"type": "容量", "value": "64G"},
                        ],
                        "stock": 1,
                    },
                },
                {"order": 6, "action": "expect_status", "status": 200},
                {"order": 7, "action": "expect_json_contains", "path": "code", "value": 0},
            ],
            expected_result="登录接口返回 token，加入购物车接口返回 code=0。",
            tags=["agent-generated", "api", "shopxo", "cart"],
            generated_by="agent",
            ai_review={},
        )

    def _looks_like_web_ui_requirement(self, content: str) -> bool:
        return any(keyword in content for keyword in ["点击", "搜索框", "输入框", "按钮", "页面", "跳转", "填入", "搜索"])

    def _looks_like_api_requirement(self, content: str) -> bool:
        lowered = content.lower()
        return any(keyword in lowered for keyword in ["api", "http", "接口", "请求", "响应", "状态码", "endpoint", "登录", "购物车", "加购"])

    def _extract_credentials(self, content: str) -> tuple[str, str]:
        username = self._match_first(content, [r"账号[:：\s]*([A-Za-z0-9_@.-]{3,64})", r"用户名[:：\s]*([A-Za-z0-9_@.-]{3,64})"])
        password = self._match_first(content, [r"密码[:：\s]*([^\s，。；;,]{3,64})"])
        return username or "huace_xm", password or "123456"

    def _match_first(self, content: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, content, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_quoted_text(self, content: str) -> str | None:
        patterns = [
            r'"([^"]+)"',
            r"“([^”]+)”",
            r"'([^']+)'",
            r"搜索\s*([^\s，。,.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip()
        return None

    def _extract_features(self, content: str) -> list[str]:
        text = content.strip()
        if not text:
            return ["核心功能"]

        candidates = re.split(r"[。；;\n\r]+", text)
        features = []
        for item in candidates:
            cleaned = re.sub(r"^\s*[-*0-9.、]+\s*", "", item).strip()
            if 4 <= len(cleaned) <= 60:
                features.append(cleaned)

        if not features:
            features = [text[:40]]
        return features[:5]

    def _regression_case(self, project_id: int, requirement_id: int | None) -> TestCaseCreate:
        return TestCaseCreate(
            project_id=project_id,
            requirement_id=requirement_id,
            title="验证本次需求变更不破坏核心回归流程",
            type="regression",
            priority="P1",
            status="draft",
            preconditions="已准备历史核心流程用例和本次需求相关测试数据。",
            steps=[
                {"order": 1, "action": "根据需求影响范围选择核心回归用例。"},
                {"order": 2, "action": "执行登录、权限、主流程和数据查询等关键路径。"},
                {"order": 3, "action": "对比历史预期结果和本次执行结果。"},
            ],
            expected_result="核心流程保持稳定，没有出现与本次需求无关的功能回退。",
            tags=["agent-generated", "regression"],
            generated_by="agent",
            ai_review={},
        )

    def review_cases(self, requirement: str, cases: list[TestCaseCreate], skill_context: str) -> list[TestCaseCreate]:
        llm_review = self._review_with_deepseek(requirement, cases, skill_context)
        reviewed_cases = []
        for index, case in enumerate(cases):
            review = llm_review.get(index) or self._rule_review_case(requirement, case, cases)
            reviewed_cases.append(case.model_copy(update={"ai_review": review}))
        return reviewed_cases

    def _review_cases_with_rules(self, requirement: str, cases: list[TestCaseCreate]) -> list[TestCaseCreate]:
        return [
            case.model_copy(update={"ai_review": self._rule_review_case(requirement, case, cases)})
            for case in cases
        ]

    def _review_with_deepseek(
        self,
        requirement: str,
        cases: list[TestCaseCreate],
        skill_context: str,
    ) -> dict[int, dict[str, Any]]:
        model = get_deepseek_chat_model(temperature=0)
        if model is None or not cases:
            return {}

        case_payload = [
            {
                "index": index,
                "title": case.title,
                "type": case.type,
                "priority": case.priority,
                "preconditions": case.preconditions,
                "steps": case.steps,
                "expected_result": case.expected_result,
                "tags": case.tags,
            }
            for index, case in enumerate(cases)
        ]
        messages = [
            SystemMessage(
                content=(
                    "你是 AITestHub 平台中的测试用例自评审 Agent。"
                    "你只检查生成用例质量，不新增业务事实。"
                    "必须只返回 JSON，不要 Markdown，不要解释。"
                    "JSON 格式：{\"reviews\":[{\"index\":0,\"risk_level\":\"low|medium|high\","
                    "\"score\":0-100,\"missing\":[\"\"],\"contradictions\":[\"\"],"
                    "\"out_of_scope\":[\"\"],\"duplicates\":[\"\"],\"suggestions\":[\"\"],"
                    "\"verdict\":\"pass|needs_human_review\"}]}"
                )
            ),
            HumanMessage(
                content=(
                    f"需求：\n{requirement}\n\n"
                    f"可用测试 skill 知识：\n{skill_context}\n\n"
                    f"待评审用例 JSON：\n{json.dumps(case_payload, ensure_ascii=False)}"
                )
            ),
        ]
        try:
            response = model.invoke(messages)
            parsed = self._extract_json(str(response.content))
            reviews = parsed.get("reviews", [])
            result = {}
            if isinstance(reviews, list):
                for item in reviews:
                    index = item.get("index")
                    if isinstance(index, int):
                        result[index] = self._normalize_ai_review(item)
            return result
        except Exception:
            return {}

    def _rule_review_case(
        self,
        requirement: str,
        test_case: TestCaseCreate,
        all_cases: list[TestCaseCreate],
    ) -> dict[str, Any]:
        missing = []
        contradictions = []
        out_of_scope = []
        suggestions = []

        if len(test_case.steps) < 2:
            missing.append("步骤数量偏少，可能缺少操作过程或验证动作。")
        if not test_case.expected_result.strip():
            missing.append("缺少可验证的预期结果。")
        if test_case.type not in {"functional", "api", "web_ui", "ui", "regression", "security", "manual"}:
            out_of_scope.append("用例类型不在平台推荐范围内。")
        if "成功" in test_case.title and any(word in test_case.expected_result for word in ["失败", "错误", "拒绝"]):
            contradictions.append("标题描述成功场景，但预期结果包含失败语义。")
        duplicate_titles = [item.title for item in all_cases if item is not test_case and item.title == test_case.title]
        duplicates = list(dict.fromkeys(duplicate_titles))

        requirement_keywords = set(self._extract_features(requirement))
        if requirement_keywords and not any(keyword[:8] in test_case.title or keyword[:8] in test_case.expected_result for keyword in requirement_keywords):
            suggestions.append("建议人工确认该用例是否与当前需求强相关。")

        score = 100 - len(missing) * 15 - len(contradictions) * 20 - len(out_of_scope) * 20 - len(duplicates) * 10
        score = max(0, min(100, score))
        risk_level = "low" if score >= 80 else "medium" if score >= 60 else "high"
        return {
            "risk_level": risk_level,
            "score": score,
            "missing": missing,
            "contradictions": contradictions,
            "out_of_scope": out_of_scope,
            "duplicates": duplicates,
            "suggestions": suggestions,
            "verdict": "pass" if score >= 80 else "needs_human_review",
            "reviewed_by": "rule-reviewer",
        }

    def _normalize_ai_review(self, item: dict[str, Any]) -> dict[str, Any]:
        score = item.get("score", 0)
        if not isinstance(score, int):
            score = 0
        return {
            "risk_level": item.get("risk_level") if item.get("risk_level") in {"low", "medium", "high"} else "medium",
            "score": max(0, min(100, score)),
            "missing": self._normalize_string_list(item.get("missing")),
            "contradictions": self._normalize_string_list(item.get("contradictions")),
            "out_of_scope": self._normalize_string_list(item.get("out_of_scope")),
            "duplicates": self._normalize_string_list(item.get("duplicates")),
            "suggestions": self._normalize_string_list(item.get("suggestions")),
            "verdict": item.get("verdict") if item.get("verdict") in {"pass", "needs_human_review"} else "needs_human_review",
            "reviewed_by": "deepseek-reviewer",
        }

    def _normalize_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item)[:240] for item in value if str(item).strip()][:8]
        if isinstance(value, str) and value.strip():
            return [value.strip()[:240]]
        return []


def serialize_steps(steps: list[dict[str, Any]]) -> str:
    return "\n".join(f"{step.get('order', index + 1)}. {step.get('action', '')}" for index, step in enumerate(steps))
