from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunk
from app.schemas import KnowledgeCreate
from app.services.knowledge_service import KnowledgeService


class KnowledgeImportService:
    """解析上传文件并批量写入知识库。

    第一版支持 txt、md、csv、json。PDF/Word 后续接入专门解析器。
    """

    allowed_suffixes = {".txt", ".md", ".csv", ".json"}

    def import_file(
        self,
        db: Session,
        project_id: int,
        filename: str,
        content: bytes,
        default_source_type: str = "requirement",
        default_status: str = "active",
        default_skill_name: str | None = None,
        default_quality_score: int = 3,
    ) -> tuple[list[KnowledgeChunk], int]:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.allowed_suffixes:
            raise ValueError("仅支持 txt、md、csv、json 文件")
        text = self._decode_text(content)
        records = self._parse_records(filename, suffix, text, default_source_type)

        imported: list[KnowledgeChunk] = []
        skipped = 0
        service = KnowledgeService()
        for index, record in enumerate(records, start=1):
            title = str(record.get("title") or f"{Path(filename).stem}-{index}").strip()
            body = str(record.get("content") or "").strip()
            if not title or len(body) < 6:
                skipped += 1
                continue
            source_type = str(record.get("source_type") or default_source_type).strip() or default_source_type
            triggers = self._normalize_triggers(record.get("triggers") or record.get("keywords") or title)
            payload = KnowledgeCreate(
                project_id=project_id,
                source_type=source_type,
                source_id=str(record.get("source_id") or f"{filename}:{index}"),
                title=title[:240],
                content=body,
                status=str(record.get("status") or default_status),
                skill_name=str(record.get("skill_name") or default_skill_name or self._skill_name_for_source(source_type)),
                triggers=triggers,
                quality_score=self._normalize_quality(record.get("quality_score"), default_quality_score),
                metadata_={
                    "imported_from": filename,
                    "row_index": index,
                    "parser": suffix.lstrip("."),
                },
            )
            imported.append(service.create_chunk(db, payload))
        return imported, skipped

    def _decode_text(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文件编码无法识别，请使用 UTF-8 或 GB18030 文本")

    def _parse_records(self, filename: str, suffix: str, text: str, default_source_type: str) -> list[dict[str, Any]]:
        if suffix == ".json":
            return self._parse_json(text)
        if suffix == ".csv":
            return self._parse_csv(text)
        return self._parse_text(filename, text, default_source_type)

    def _parse_json(self, text: str) -> list[dict[str, Any]]:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data = data["items"]
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("JSON 必须是对象、对象数组，或包含 items 数组")
        return [item for item in data if isinstance(item, dict)]

    def _parse_csv(self, text: str) -> list[dict[str, Any]]:
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            if not row:
                continue
            normalized = {str(key).strip(): value for key, value in row.items() if key}
            rows.append(normalized)
        return rows

    def _parse_text(self, filename: str, text: str, default_source_type: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            return []

        blocks = self._split_markdown_blocks(normalized)
        if len(blocks) <= 1:
            blocks = self._split_plain_blocks(normalized)

        records = []
        for index, block in enumerate(blocks, start=1):
            title = self._guess_title(filename, block, index)
            records.append({"title": title, "content": block.strip(), "source_type": default_source_type})
        return records

    def _split_markdown_blocks(self, text: str) -> list[str]:
        matches = list(re.finditer(r"(?m)^#{1,4}\s+.+$", text))
        if not matches:
            return [text]
        blocks = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end].strip()
            if block:
                blocks.append(block)
        return blocks

    def _split_plain_blocks(self, text: str) -> list[str]:
        raw_blocks = [item.strip() for item in re.split(r"\n\s*\n+", text) if item.strip()]
        blocks: list[str] = []
        buffer = ""
        for block in raw_blocks:
            if len(block) > 1200:
                blocks.extend(self._chunk_long_text(block))
                continue
            if len(buffer) + len(block) < 1200:
                buffer = f"{buffer}\n\n{block}".strip()
            else:
                if buffer:
                    blocks.append(buffer)
                buffer = block
        if buffer:
            blocks.append(buffer)
        return blocks or [text]

    def _chunk_long_text(self, text: str, size: int = 1000) -> list[str]:
        sentences = re.split(r"(?<=[。！？.!?])", text)
        chunks = []
        buffer = ""
        for sentence in sentences:
            if len(buffer) + len(sentence) <= size:
                buffer += sentence
            else:
                if buffer.strip():
                    chunks.append(buffer.strip())
                buffer = sentence
        if buffer.strip():
            chunks.append(buffer.strip())
        return chunks or [text[:size]]

    def _guess_title(self, filename: str, block: str, index: int) -> str:
        first_line = block.strip().splitlines()[0].strip()
        first_line = re.sub(r"^#{1,6}\s*", "", first_line)
        if 4 <= len(first_line) <= 80:
            return first_line
        return f"{Path(filename).stem}-{index}"

    def _normalize_triggers(self, value: Any) -> list[str]:
        if isinstance(value, list):
            raw = value
        else:
            raw = re.split(r"[\s,，、;；|/]+", str(value))
        return [str(item).strip()[:40] for item in raw if str(item).strip()][:10]

    def _normalize_quality(self, value: Any, default: int) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            score = default
        return max(1, min(5, score))

    def _skill_name_for_source(self, source_type: str) -> str:
        mapping = {
            "requirement": "需求分析 skill",
            "historical_defect": "历史缺陷测试 skill",
            "business_rule": "业务规则测试 skill",
            "test_strategy": "测试策略 skill",
        }
        return mapping.get(source_type, "批量导入测试 skill")
