from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiEndpointSpec:
    name: str
    path: str
    method: str = "GET"
    request_example: dict[str, Any] = field(default_factory=dict)
    success_example: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


class ApiDocParser:
    """从接口文档文本中提取轻量接口结构。

    解析目标是辅助测试用例生成，不追求完整 OpenAPI 能力；优先支持常见中文接口文档中的
    “请求URL / 请求方式 / 请求参数 / 正确时返回”片段。
    """

    endpoint_pattern = re.compile(r"(?m)^(api/[A-Za-z0-9_./-]+)\s*$")
    method_pattern = re.compile(r"请求[⽅方]式\s*(GET|POST|PUT|PATCH|DELETE)", re.IGNORECASE)
    json_block_pattern = re.compile(r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}", re.DOTALL)

    def parse(self, text: str) -> list[ApiEndpointSpec]:
        normalized = self._normalize_text(text)
        matches = list(self.endpoint_pattern.finditer(normalized))
        endpoints: list[ApiEndpointSpec] = []
        for match in matches:
            path = match.group(1).strip()
            start = normalized.rfind("\n请求URL", 0, match.start())
            start = start if start >= 0 else max(0, normalized.rfind("\n", 0, match.start() - 1))
            end = normalized.find("\n请求URL", match.end())
            end = end if end >= 0 else len(normalized)
            block = normalized[start:end].strip()
            endpoints.append(self._parse_endpoint(path, block))
        return endpoints

    def find(self, text: str, keywords: list[str]) -> ApiEndpointSpec | None:
        endpoints = self.parse(text)
        lowered_keywords = [keyword.lower() for keyword in keywords if keyword]
        for endpoint in endpoints:
            haystack = f"{endpoint.name}\n{endpoint.path}".lower()
            if all(keyword in haystack for keyword in lowered_keywords):
                return endpoint
        for endpoint in endpoints:
            haystack = f"{endpoint.name}\n{endpoint.path}".lower()
            if any(keyword in haystack for keyword in lowered_keywords):
                return endpoint
        for endpoint in endpoints:
            haystack = f"{endpoint.name}\n{endpoint.path}\n{endpoint.raw_text}".lower()
            if all(keyword in haystack for keyword in lowered_keywords):
                return endpoint
        for endpoint in endpoints:
            haystack = f"{endpoint.name}\n{endpoint.path}\n{endpoint.raw_text}".lower()
            if any(keyword in haystack for keyword in lowered_keywords):
                return endpoint
        return None

    def _parse_endpoint(self, path: str, block: str) -> ApiEndpointSpec:
        method_match = self.method_pattern.search(block)
        method = method_match.group(1).upper() if method_match else "POST"
        name = self._guess_name(path, block)
        json_blocks = [
            {"value": parsed, "start": match.start()}
            for match in self.json_block_pattern.finditer(block)
            if isinstance(parsed := self._parse_json_block(match.group(0)), dict)
        ]
        request_example = self._guess_request_example(block, json_blocks)
        parsed_blocks = [item["value"] for item in json_blocks]
        success_example = self._guess_success_example(json_blocks)
        return ApiEndpointSpec(
            name=name,
            path=path,
            method=method,
            request_example=request_example,
            success_example=success_example,
            raw_text=block[:3000],
        )

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\xa0", " ")
        normalized = normalized.replace("⼊", "入").replace("⻋", "车").replace("⽅", "方")
        normalized = normalized.replace("⾊", "色").replace("⼆", "二").replace("⼀", "一")
        return normalized

    def _guess_name(self, path: str, block: str) -> str:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line == path and index > 0:
                previous = lines[index - 1]
                if not previous.startswith("请求") and len(previous) <= 40:
                    return previous
        return path.rsplit("/", 1)[-1]

    def _parse_json_block(self, raw: str) -> dict[str, Any] | None:
        text = raw.replace("\xa0", " ")
        text = re.sub(r"//.*", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _guess_request_example(self, block: str, examples: list[dict[str, Any]]) -> dict[str, Any]:
        marker = block.find("请求参数")
        candidates = examples
        if marker >= 0:
            candidates = [item for item in examples if item["start"] > marker]
        for item in candidates:
            value = item["value"]
            if not ({"msg", "code", "data"} <= set(value.keys())):
                return value
        return candidates[0]["value"] if candidates else {}

    def _guess_success_example(self, examples: list[dict[str, Any]]) -> dict[str, Any]:
        for item in examples:
            example = item["value"]
            if "code" in example and str(example.get("code")) in {"0", "200"}:
                return example
        values = [item["value"] for item in examples]
        return values[-1] if len(values) > 1 else {}


def format_endpoint_context(endpoints: list[ApiEndpointSpec]) -> str:
    lines = []
    for endpoint in endpoints:
        lines.append(
            "\n".join(
                [
                    f"接口：{endpoint.name}",
                    f"路径：{endpoint.path}",
                    f"方法：{endpoint.method}",
                    f"请求示例：{json.dumps(endpoint.request_example, ensure_ascii=False)}",
                    f"成功示例：{json.dumps(endpoint.success_example, ensure_ascii=False)}",
                ]
            )
        )
    return "\n\n".join(lines)
