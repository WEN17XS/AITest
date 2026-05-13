from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunk, TestCase, TestRun, TestRunArtifact, TestRunResult
from app.services.llm_service import get_deepseek_chat_model


class FailureDiagnosisService:
    """失败归因服务。

    第一版采用 LLM 优先、规则兜底。归因结果直接写回 test_run_results.ai_diagnosis，
    后续可进入人工审核并沉淀到知识库。
    """

    def diagnose_result(self, db: Session, result_id: int) -> TestRunResult:
        result = db.get(TestRunResult, result_id)
        if result is None:
            raise ValueError("测试结果不存在")

        run = db.get(TestRun, result.run_id)
        test_case = db.get(TestCase, result.case_id) if result.case_id else None
        artifacts = db.query(TestRunArtifact).filter(TestRunArtifact.result_id == result.id).all()
        execution_evidence = self._load_execution_evidence(run, artifacts)

        diagnosis = self._diagnose_with_llm(run, result, test_case, artifacts, execution_evidence)
        if not diagnosis:
            diagnosis = self._diagnose_with_rules(run, result, test_case, artifacts, execution_evidence)
        elif not diagnosis.get("suggested_steps"):
            suggested_steps = self._suggest_steps_from_evidence(test_case, execution_evidence)
            if not suggested_steps:
                suggested_steps = self._suggest_steps_from_logs(test_case, "\n".join([result.message or "", result.logs or ""]))
            if suggested_steps:
                diagnosis["suggested_steps"] = suggested_steps

        result.ai_diagnosis = diagnosis
        db.commit()
        db.refresh(result)
        return result

    def save_diagnosis_knowledge(self, db: Session, result_id: int) -> KnowledgeChunk:
        result = db.get(TestRunResult, result_id)
        if result is None:
            raise ValueError("测试结果不存在")
        if not result.ai_diagnosis:
            result = self.diagnose_result(db, result_id)

        run = db.get(TestRun, result.run_id)
        test_case = db.get(TestCase, result.case_id) if result.case_id else None
        project_id = test_case.project_id if test_case else run.project_id if run else None
        if project_id is None:
            raise ValueError("无法确定知识所属项目")

        diagnosis = result.ai_diagnosis or {}
        source_type = str(diagnosis.get("knowledge_type") or "execution_failure")
        if source_type == "none":
            source_type = "execution_failure"
        source_id = f"run_result:{result.id}"
        existing = (
            db.query(KnowledgeChunk)
            .filter(
                KnowledgeChunk.project_id == project_id,
                KnowledgeChunk.source_type == source_type,
                KnowledgeChunk.source_id == source_id,
            )
            .first()
        )
        title = self._knowledge_title(result, test_case, diagnosis)
        content = self._knowledge_content(run, result, test_case, diagnosis)
        triggers = self._knowledge_triggers(run, result, test_case, diagnosis)
        metadata = {
            "run_id": result.run_id,
            "result_id": result.id,
            "case_id": result.case_id,
            "failure_type": diagnosis.get("failure_type"),
            "diagnosed_by": diagnosis.get("diagnosed_by"),
            "confidence": diagnosis.get("confidence"),
        }
        if existing:
            existing.title = title
            existing.content = content
            existing.status = "active"
            existing.skill_name = self._skill_name(source_type)
            existing.triggers = triggers
            existing.quality_score = self._knowledge_score(diagnosis)
            existing.metadata_ = metadata
            db.commit()
            db.refresh(existing)
            return existing

        chunk = KnowledgeChunk(
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            content=content,
            status="active",
            skill_name=self._skill_name(source_type),
            triggers=triggers,
            quality_score=self._knowledge_score(diagnosis),
            metadata_=metadata,
            embedding=None,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def _diagnose_with_llm(
        self,
        run: TestRun | None,
        result: TestRunResult,
        test_case: TestCase | None,
        artifacts: list[TestRunArtifact],
        execution_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        model = get_deepseek_chat_model(temperature=0, max_tokens=1200)
        if model is None:
            return {}

        payload = {
            "run": {
                "id": run.id if run else None,
                "executor_type": run.executor_type if run else None,
                "executor_config": run.executor_config if run else {},
                "status": run.status if run else None,
            },
            "result": {
                "id": result.id,
                "case_id": result.case_id,
                "status": result.status,
                "message": result.message,
                "logs": (result.logs or "")[-6000:],
                "artifacts": result.artifacts,
            },
            "test_case": {
                "title": test_case.title if test_case else None,
                "type": test_case.type if test_case else None,
                "steps": test_case.steps if test_case else [],
                "expected_result": test_case.expected_result if test_case else None,
            },
            "artifact_records": [
                {
                    "id": artifact.id,
                    "type": artifact.artifact_type,
                    "path": artifact.path,
                    "content_type": artifact.content_type,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in artifacts
            ],
            "execution_evidence": execution_evidence,
        }
        messages = [
            SystemMessage(
                content=(
                    "你是 AITestHub 的测试执行失败归因 Agent。"
                    "你只基于输入的运行结果、日志、测试步骤和附件元数据做诊断，不要编造未提供的业务事实。"
                    "必须返回 JSON，不能返回 Markdown。"
                    "failure_type 只能是 selector_not_visible、selector_not_found、navigation_timeout、assertion_mismatch、"
                    "anti_automation_blocked、environment_unreachable、test_case_design_error、execution_error、unknown 之一。"
                    "knowledge_type 只能是 selector_strategy、execution_failure、site_compatibility、anti_pattern、none 之一。"
                    "如果可以从 execution_evidence 和原步骤推断出更稳妥的步骤，请返回 suggested_steps 数组；"
                    "suggested_steps 必须是可人工审核的 Playwright 受控步骤 JSON，不要输出任意脚本。"
                    "JSON 格式：{\"failure_type\":\"\",\"root_cause\":\"\",\"evidence\":[\"\"],"
                    "\"fix_suggestions\":[\"\"],\"suggested_steps\":[{\"order\":1,\"action\":\"\"}],"
                    "\"knowledge_type\":\"\",\"should_save_knowledge\":true,"
                    "\"confidence\":0-100,\"diagnosed_by\":\"llm-diagnoser\"}"
                )
            ),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        try:
            response = model.invoke(messages)
            parsed = self._extract_json(str(response.content))
            return self._normalize_diagnosis(parsed, diagnosed_by="llm-diagnoser")
        except Exception:
            return {}

    def _diagnose_with_rules(
        self,
        run: TestRun | None,
        result: TestRunResult,
        test_case: TestCase | None,
        artifacts: list[TestRunArtifact],
        execution_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        text = "\n".join([result.message or "", result.logs or ""])
        lower_text = text.lower()
        failure_type = "unknown"
        root_cause = "暂未识别出明确根因，需要人工结合日志和附件继续分析。"
        suggestions = ["查看失败截图、运行日志和用例步骤，确认页面状态与预期是否一致。"]
        knowledge_type = "execution_failure"
        should_save = False
        suggested_steps = self._suggest_steps_from_evidence(test_case, execution_evidence)
        if not suggested_steps:
            suggested_steps = self._suggest_steps_from_logs(test_case, text)

        evidence_hints = self._evidence_hints(execution_evidence)

        if "wappass.baidu.com" in lower_text or "百度安全验证" in text or evidence_hints.get("anti_automation"):
            failure_type = "anti_automation_blocked"
            root_cause = "目标站点返回了安全验证页面，公开第三方站点存在反自动化拦截。"
            suggestions = ["改用可控测试站点验证平台能力。", "如必须验证该站点，考虑人工登录/验证后的持久化浏览器会话。"]
            knowledge_type = "site_compatibility"
            should_save = True
        elif "element is not visible" in lower_text or "not visible" in lower_text or evidence_hints.get("has_invisible_selector"):
            failure_type = "selector_not_visible"
            root_cause = "selector 命中了存在但不可见的元素，常见于页面 DOM 更新或隐藏旧表单。"
            suggestions = ["为步骤增加 selector_candidates。", "优先选择可见、可编辑、可点击的元素。", "结合截图和 DOM 摘要更新用例步骤。"]
            knowledge_type = "selector_strategy"
            should_save = True
        elif (
            ("waiting for locator" in lower_text and "timeout" in lower_text)
            or "没有找到可见且可操作的元素" in text
            or evidence_hints.get("has_missing_selector")
        ):
            failure_type = "selector_not_found"
            root_cause = "执行器在超时时间内没有找到可操作的目标元素，可能是 selector 失效或页面未进入预期状态。"
            suggestions = ["确认 selector 是否仍存在。", "增加等待条件或前置操作。", "检查环境 base_url 是否指向正确页面。"]
            knowledge_type = "selector_strategy"
            should_save = True
        elif "page.goto" in lower_text and "timeout" in lower_text:
            failure_type = "navigation_timeout"
            root_cause = "页面导航超时，可能是外部站点加载慢、资源长连接未结束或网络不可达。"
            suggestions = ["将 wait_until 调整为 domcontentloaded。", "适当提高 timeout。", "优先使用可控测试环境。"]
            knowledge_type = "execution_failure"
            should_save = True
        elif "未包含期望文本" in text or "expected" in lower_text and "not" in lower_text:
            failure_type = "assertion_mismatch"
            root_cause = "页面实际内容未满足断言，可能是等待不足、搜索未真正提交、结果页被拦截或预期文案不准确。"
            suggestions = ["确认断言前是否需要等待结果区域。", "检查截图中的当前页面状态。", "必要时调整预期结果或拆分提交与断言步骤。"]
            if "selector fallback" in lower_text:
                suggestions.insert(0, "将日志中已成功 fallback 的 selector 写回用例，并优先使用 press Enter 提交搜索。")
            knowledge_type = "execution_failure"
            should_save = True

        evidence = [
            *self._evidence_from_text(text, artifacts, test_case),
            *self._evidence_from_execution(execution_evidence),
        ][:8]
        return self._normalize_diagnosis(
            {
                "failure_type": failure_type,
                "root_cause": root_cause,
                "evidence": evidence,
                "fix_suggestions": suggestions,
                "suggested_steps": suggested_steps,
                "knowledge_type": knowledge_type,
                "should_save_knowledge": should_save,
                "confidence": 80 if failure_type != "unknown" else 35,
                "diagnosed_by": "rule-diagnoser",
            },
            diagnosed_by="rule-diagnoser",
        )

    def _extract_json(self, raw_content: str) -> dict[str, Any]:
        text = raw_content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    def _normalize_diagnosis(self, value: dict[str, Any], diagnosed_by: str) -> dict[str, Any]:
        failure_types = {
            "selector_not_visible",
            "selector_not_found",
            "navigation_timeout",
            "assertion_mismatch",
            "anti_automation_blocked",
            "environment_unreachable",
            "test_case_design_error",
            "execution_error",
            "unknown",
        }
        knowledge_types = {"selector_strategy", "execution_failure", "site_compatibility", "anti_pattern", "none"}
        confidence = value.get("confidence", 0)
        if not isinstance(confidence, int):
            confidence = 0
        return {
            "failure_type": value.get("failure_type") if value.get("failure_type") in failure_types else "unknown",
            "root_cause": str(value.get("root_cause") or "暂无明确归因。")[:1000],
            "evidence": self._string_list(value.get("evidence")),
            "fix_suggestions": self._string_list(value.get("fix_suggestions")),
            "suggested_steps": self._normalize_suggested_steps(value.get("suggested_steps")),
            "knowledge_type": value.get("knowledge_type") if value.get("knowledge_type") in knowledge_types else "none",
            "should_save_knowledge": bool(value.get("should_save_knowledge", False)),
            "confidence": max(0, min(100, confidence)),
            "diagnosed_by": str(value.get("diagnosed_by") or diagnosed_by)[:80],
        }

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item)[:300] for item in value if str(item).strip()][:8]
        if isinstance(value, str) and value.strip():
            return [value.strip()[:300]]
        return []

    def _evidence_from_text(
        self,
        text: str,
        artifacts: list[TestRunArtifact],
        test_case: TestCase | None,
    ) -> list[str]:
        evidence = []
        for line in text.splitlines():
            if any(keyword in line for keyword in ["失败原因", "Timeout", "not visible", "wappass", "未包含期望文本", "没有找到可见且可操作", "selector"]):
                evidence.append(line.strip())
        if test_case:
            evidence.append(f"用例：{test_case.title}")
        if artifacts:
            evidence.append("附件：" + "、".join(artifact.path for artifact in artifacts[:3]))
        return evidence[:8]

    def _evidence_from_execution(self, execution_evidence: dict[str, Any]) -> list[str]:
        if not execution_evidence:
            return []
        evidence = []
        if execution_evidence.get("url"):
            evidence.append(f"失败时页面 URL：{execution_evidence['url']}")
        if execution_evidence.get("title"):
            evidence.append(f"失败时页面标题：{execution_evidence['title']}")
        for diagnostic in execution_evidence.get("step_selectors", []) if isinstance(execution_evidence.get("step_selectors"), list) else []:
            if not isinstance(diagnostic, dict):
                continue
            candidates = diagnostic.get("candidates") if isinstance(diagnostic.get("candidates"), list) else []
            summary = []
            for candidate in candidates[:4]:
                if not isinstance(candidate, dict):
                    continue
                if "error" in candidate:
                    summary.append(f"{candidate.get('selector')} error")
                else:
                    summary.append(
                        f"{candidate.get('selector')} count={candidate.get('count')} visible={candidate.get('visible')} editable={candidate.get('editable')}"
                    )
            if summary:
                evidence.append(f"步骤 {diagnostic.get('order')} selector 诊断：" + "；".join(summary))
        visible = execution_evidence.get("visible_elements") if isinstance(execution_evidence.get("visible_elements"), dict) else {}
        inputs = visible.get("inputs") if isinstance(visible, dict) else []
        buttons = visible.get("buttons") if isinstance(visible, dict) else []
        if inputs:
            evidence.append("失败时可见输入元素：" + "；".join(self._element_identity(item) for item in inputs[:4] if isinstance(item, dict)))
        if buttons:
            evidence.append("失败时可见按钮元素：" + "；".join(self._element_identity(item) for item in buttons[:4] if isinstance(item, dict)))
        return [item for item in evidence if item][:8]

    def _evidence_hints(self, execution_evidence: dict[str, Any]) -> dict[str, bool]:
        text = "\n".join(
            [
                str(execution_evidence.get("url") or ""),
                str(execution_evidence.get("title") or ""),
                str(execution_evidence.get("body_text_excerpt") or ""),
            ]
        )
        has_invisible_selector = False
        has_missing_selector = False
        for diagnostic in execution_evidence.get("step_selectors", []) if isinstance(execution_evidence.get("step_selectors"), list) else []:
            if not isinstance(diagnostic, dict):
                continue
            candidates = diagnostic.get("candidates") if isinstance(diagnostic.get("candidates"), list) else []
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("count", 0) and candidate.get("visible") is False:
                    has_invisible_selector = True
                if isinstance(candidate, dict) and candidate.get("count", 0) == 0:
                    has_missing_selector = True
        return {
            "anti_automation": "wappass.baidu.com" in text or "百度安全验证" in text,
            "has_invisible_selector": has_invisible_selector,
            "has_missing_selector": has_missing_selector,
        }

    def _element_identity(self, item: dict[str, Any]) -> str:
        identity = item.get("id") or item.get("name") or item.get("placeholder") or item.get("aria_label") or item.get("text") or item.get("tag")
        return str(identity)[:100]

    def _load_execution_evidence(self, run: TestRun | None, artifacts: list[TestRunArtifact]) -> dict[str, Any]:
        if run is None:
            return {}
        for artifact in artifacts:
            if not artifact.path.endswith("failure-evidence.json"):
                continue
            evidence_path = self._run_artifacts_dir(run.id) / artifact.path
            try:
                resolved = evidence_path.resolve()
                resolved.relative_to(self._run_artifacts_dir(run.id))
                return json.loads(resolved.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _run_artifacts_dir(self, run_id: int) -> Path:
        return Path(__file__).resolve().parents[2] / "storage" / "runs" / str(run_id)

    def _suggest_steps_from_evidence(
        self,
        test_case: TestCase | None,
        execution_evidence: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if test_case is None or not execution_evidence:
            return []
        suggested_steps = [dict(step) for step in test_case.steps or [] if isinstance(step, dict)]
        replacements = self._selector_replacements(execution_evidence)
        if not replacements:
            return []
        changed = False
        for step in suggested_steps:
            selector = str(step.get("selector") or "").strip()
            replacement = replacements.get(selector)
            if not selector or not replacement:
                continue
            candidates = [str(item).strip() for item in step.get("selector_candidates", []) if str(item).strip()] if isinstance(step.get("selector_candidates"), list) else []
            step["selector_candidates"] = list(dict.fromkeys([replacement, *candidates, selector]))
            if selector in {"#kw", "#su"}:
                step["selector"] = replacement
            changed = True
        return self._normalize_suggested_steps(suggested_steps) if changed else []

    def _suggest_steps_from_logs(self, test_case: TestCase | None, text: str) -> list[dict[str, Any]]:
        if test_case is None or not text:
            return []
        replacements = self._selector_replacements_from_logs(text)
        if not replacements:
            return []

        suggested_steps = [dict(step) for step in test_case.steps or [] if isinstance(step, dict)]
        changed = False
        fill_selector = ""
        insert_press_after_order: int | None = None
        for step in suggested_steps:
            action = str(step.get("action") or "").strip()
            selector = str(step.get("selector") or "").strip()
            replacement = replacements.get(selector)
            if selector and replacement:
                candidates = [str(item).strip() for item in step.get("selector_candidates", []) if str(item).strip()] if isinstance(step.get("selector_candidates"), list) else []
                step["selector"] = replacement
                step["selector_candidates"] = list(dict.fromkeys([replacement, *candidates, selector]))
                changed = True
                if action == "fill":
                    fill_selector = replacement
                    insert_press_after_order = int(step.get("order") or 0)
            if action == "click" and selector in replacements:
                step["_prefer_remove_for_submit"] = True

        if fill_selector and not any(str(step.get("action") or "") == "press" for step in suggested_steps):
            press_step = {
                "order": (insert_press_after_order or 2) + 1,
                "action": "press",
                "selector": fill_selector,
                "selector_candidates": [fill_selector, "#kw"],
                "key": "Enter",
            }
            rebuilt_steps: list[dict[str, Any]] = []
            inserted = False
            for step in suggested_steps:
                if step.pop("_prefer_remove_for_submit", False):
                    changed = True
                    continue
                rebuilt_steps.append(step)
                if not inserted and int(step.get("order") or 0) == insert_press_after_order:
                    rebuilt_steps.append(press_step)
                    inserted = True
                    changed = True
            suggested_steps = rebuilt_steps

        for index, step in enumerate(suggested_steps, start=1):
            step["order"] = index
        return self._normalize_suggested_steps(suggested_steps) if changed else []

    def _selector_replacements_from_logs(self, text: str) -> dict[str, str]:
        replacements: dict[str, str] = {}
        for original, replacement in re.findall(r"selector fallback\s+([^\s]+)\s+->\s+([^\s\[]+)(?:\[\d+\])?", text):
            original_selector = original.strip()
            replacement_selector = replacement.strip()
            if original_selector and replacement_selector:
                replacements[original_selector] = replacement_selector
        return replacements

    def _selector_replacements(self, execution_evidence: dict[str, Any]) -> dict[str, str]:
        visible = execution_evidence.get("visible_elements") if isinstance(execution_evidence.get("visible_elements"), dict) else {}
        replacements: dict[str, str] = {}
        inputs = visible.get("inputs") if isinstance(visible, dict) else []
        buttons = visible.get("buttons") if isinstance(visible, dict) else []
        input_selector = self._best_selector(inputs if isinstance(inputs, list) else [], prefer_editable=True)
        button_selector = self._best_selector(buttons if isinstance(buttons, list) else [], prefer_editable=False)
        if input_selector:
            replacements["#kw"] = input_selector
        if button_selector:
            replacements["#su"] = button_selector
        return replacements

    def _best_selector(self, elements: list[Any], prefer_editable: bool) -> str | None:
        for item in elements:
            if not isinstance(item, dict):
                continue
            element_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            placeholder = str(item.get("placeholder") or "").strip()
            aria_label = str(item.get("aria_label") or "").strip()
            text = str(item.get("text") or "").strip()
            if element_id:
                return f"#{element_id}"
            if name:
                tag = "textarea" if prefer_editable and str(item.get("tag")) == "textarea" else "input"
                return f"{tag}[name='{name}']"
            if placeholder:
                tag = "textarea" if prefer_editable and str(item.get("tag")) == "textarea" else "input"
                return f"{tag}[placeholder='{placeholder}']"
            if aria_label:
                return f"[aria-label='{aria_label}']"
            if text and not prefer_editable:
                return f"button:has-text('{text[:40]}')"
        return None

    def _normalize_suggested_steps(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        allowed_actions = {"goto", "click", "fill", "press", "expect_text", "expect_url"}
        normalized: list[dict[str, Any]] = []
        for index, step in enumerate(value[:20], start=1):
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").strip()
            if action not in allowed_actions:
                continue
            item: dict[str, Any] = {"order": int(step.get("order") or index), "action": action}
            for key in ("url", "selector", "value", "key", "text", "contains"):
                if step.get(key) is not None and str(step.get(key)).strip():
                    item[key] = str(step.get(key)).strip()[:500]
            if isinstance(step.get("selector_candidates"), list):
                candidates = [str(candidate).strip() for candidate in step["selector_candidates"] if str(candidate).strip()]
                if candidates:
                    item["selector_candidates"] = list(dict.fromkeys(candidates))[:8]
            normalized.append(item)
        return normalized

    def _knowledge_title(
        self,
        result: TestRunResult,
        test_case: TestCase | None,
        diagnosis: dict[str, Any],
    ) -> str:
        failure_type = diagnosis.get("failure_type") or "unknown"
        case_title = test_case.title if test_case else f"Result #{result.id}"
        return f"失败归因经验：{failure_type} · {case_title}"[:240]

    def _knowledge_content(
        self,
        run: TestRun | None,
        result: TestRunResult,
        test_case: TestCase | None,
        diagnosis: dict[str, Any],
    ) -> str:
        steps = ""
        if test_case:
            steps = "\n".join(
                f"{step.get('order', index + 1)}. {step}"
                for index, step in enumerate(test_case.steps or [])
            )
        evidence = "\n".join(f"- {item}" for item in self._string_list(diagnosis.get("evidence")))
        suggestions = "\n".join(f"- {item}" for item in self._string_list(diagnosis.get("fix_suggestions")))
        suggested_steps = json.dumps(diagnosis.get("suggested_steps") or [], ensure_ascii=False, indent=2)
        return (
            f"失败类型：{diagnosis.get('failure_type') or 'unknown'}\n"
            f"归因来源：{diagnosis.get('diagnosed_by') or 'unknown'}；置信度：{diagnosis.get('confidence') or 0}\n"
            f"根因：{diagnosis.get('root_cause') or '暂无'}\n\n"
            f"证据：\n{evidence or '- 暂无'}\n\n"
            f"修复建议：\n{suggestions or '- 暂无'}\n\n"
            f"建议修复步骤 JSON：\n{suggested_steps}\n\n"
            f"运行：Run #{result.run_id}；执行器：{run.executor_type if run else 'unknown'}\n"
            f"用例：{test_case.title if test_case else '未知'}\n"
            f"用例步骤：\n{steps or '暂无'}\n\n"
            f"原始错误：{result.message or '暂无'}"
        )

    def _knowledge_triggers(
        self,
        run: TestRun | None,
        result: TestRunResult,
        test_case: TestCase | None,
        diagnosis: dict[str, Any],
    ) -> list[str]:
        values = [
            diagnosis.get("failure_type"),
            diagnosis.get("knowledge_type"),
            run.executor_type if run else None,
            test_case.type if test_case else None,
            *(test_case.tags if test_case else []),
        ]
        if result.message:
            values.extend(re.findall(r"[#A-Za-z0-9_-]{2,40}", result.message)[:6])
        return [str(value) for value in values if value][:12]

    def _skill_name(self, source_type: str) -> str:
        return {
            "selector_strategy": "UI selector 定位策略",
            "execution_failure": "测试执行失败经验",
            "site_compatibility": "站点兼容性经验",
            "anti_pattern": "AI 用例反例",
        }.get(source_type, "测试执行失败经验")

    def _knowledge_score(self, diagnosis: dict[str, Any]) -> int:
        confidence = diagnosis.get("confidence")
        if isinstance(confidence, int) and confidence >= 80:
            return 4
        return 3
