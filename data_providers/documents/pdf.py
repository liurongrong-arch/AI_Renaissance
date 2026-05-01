from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from ..errors import MissingDependencyError, ProviderError


def _require_pypdf():
    try:
        from pypdf import PdfReader  # type: ignore

        return PdfReader
    except Exception as e:  # pragma: no cover
        raise MissingDependencyError(
            "未安装 pypdf，无法解析 PDF。请先安装依赖：`uv pip install pypdf`"
        ) from e


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_pdf_to_pages(pdf_bytes: bytes) -> pd.DataFrame:
    """把 PDF 原文解析为逐页文本表。

    返回列：page/text/char_count
    """

    PdfReader = _require_pypdf()
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        rows = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            rows.append({"page": i, "text": text, "char_count": len(text)})
        return pd.DataFrame(rows)
    except Exception as e:
        raise ProviderError(f"PDF 解析失败：{e}") from e
