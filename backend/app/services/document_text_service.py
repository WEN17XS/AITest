from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


class DocumentTextService:
    """把用户上传的需求/接口文档转换成文本上下文。"""

    allowed_suffixes = {".txt", ".md", ".csv", ".json", ".pdf"}

    def extract_text(self, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.allowed_suffixes:
            raise ValueError("仅支持 txt、md、csv、json、pdf 文档")
        if suffix == ".pdf":
            return self._extract_pdf_text(content)
        text = self._decode_text(content)
        if suffix == ".json":
            return self._json_to_text(text)
        if suffix == ".csv":
            return self._csv_to_text(text)
        return text

    def _decode_text(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文件编码无法识别，请使用 UTF-8 或 GB18030 文本")

    def _extract_pdf_text(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("当前环境未安装 pypdf，暂时无法直接解析 PDF；请上传已提取的 txt 文档") from exc

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"===== PAGE {index} =====\n{text.strip()}")
        if not pages:
            raise ValueError("PDF 未提取到可用文本")
        return "\n\n".join(pages)

    def _json_to_text(self, text: str) -> str:
        data: Any = json.loads(text)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _csv_to_text(self, text: str) -> str:
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            return text
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
