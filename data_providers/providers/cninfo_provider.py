from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Optional, Set, Tuple

import pandas as pd

from ..errors import DataNotFoundError, MissingDependencyError, ProviderError
from ..schemas import (
    AnnouncementPDFRequest,
    DataMeta,
    DataResult,
    DatasetType,
)
from .base import BaseProvider


def _require_requests():
    try:
        import requests  # type: ignore

        return requests
    except Exception as e:  # pragma: no cover
        raise MissingDependencyError(
            "未安装 requests，无法使用 CninfoProvider。请先安装依赖：`uv pip install requests`"
        ) from e


def _cninfo_exchange_from_cn_code(code: str) -> str:
    """CNInfo 的交易所标识：sse/szse。"""

    code = (code or "").strip()
    if len(code) == 6 and code.isdigit() and code.startswith("6"):
        return "sse"
    return "szse"


def _default_date_range() -> Tuple[str, str]:
    # 默认取近两年，减少结果量
    now = datetime.now()
    start = f"{now.year - 2}-01-01"
    end = f"{now.year}-12-31"
    return start, end


def _sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    return name[:180] if len(name) > 180 else name


class CninfoProvider(BaseProvider):
    """巨潮资讯网（CNInfo）公告查询与 PDF 下载（当前仅 CN）。

    说明：
    - 查询接口：`/new/hisAnnouncement/query`（POST）
    - PDF 下载：`https://static.cninfo.com.cn/{adjunctUrl}`
    """

    name = "cninfo"

    @property
    def capabilities(self) -> Set[DatasetType]:
        return {
            DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_RAW,
        }

    def _query_announcements(self, req: AnnouncementPDFRequest) -> dict:
        requests = _require_requests()

        start = req.start_date
        end = req.end_date
        if not start or not end:
            start, end = _default_date_range()

        if not req.symbol or not req.symbol.isdigit() or len(req.symbol) != 6:
            raise ProviderError(f"CNInfo 查询仅支持 A 股 6 位代码：{req.symbol}")

        exch = _cninfo_exchange_from_cn_code(req.symbol)

        url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.cninfo.com.cn/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }
        # 重要：CNInfo 的 stock 精确过滤在部分环境下会返回 0。
        # 这里使用 searchkey 查询（更稳定），再在本地按 secCode/title 二次过滤。
        searchkey = req.symbol
        if req.keyword:
            searchkey = f"{req.symbol} {req.keyword}"

        data = {
            "pageNum": 1,
            "pageSize": int(req.page_size or 30),
            "tabName": "fulltext",
            "column": exch,
            # 用代码做 searchkey 可以把结果集限制在该标的附近
            "searchkey": searchkey,
            "seDate": f"{start}~{end}",
            # 预留：category/plate 等条件可通过 req.extra 覆盖
        }
        data.update(req.extra.get("cninfo_query", {}) if isinstance(req.extra, dict) else {})

        try:
            resp = requests.post(url, headers=headers, data=data, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise ProviderError(f"CNInfo 查询失败：{e}") from e

    def _pick_announcement(self, payload: dict, req: AnnouncementPDFRequest) -> dict:
        anns = payload.get("announcements") or payload.get("data") or []
        if not isinstance(anns, list) or not anns:
            raise DataNotFoundError(
                f"CNInfo 未找到公告：symbol={req.symbol} keyword={req.keyword}"
            )
        # 先按代码过滤
        code_hits = [a for a in anns if str(a.get("secCode") or a.get("sec_code") or "") == req.symbol]
        if not code_hits:
            code_hits = anns

        # 再按标题关键字过滤（例如 年报/年度报告）
        kw = (req.keyword or "").strip()
        if kw:
            title_hits = [
                a
                for a in code_hits
                if kw in str(a.get("announcementTitle") or a.get("title") or "")
            ]
            if title_hits:
                return title_hits[0]

        return code_hits[0]

    def _download_pdf(self, adjunct_url: str) -> bytes:
        requests = _require_requests()
        base = "https://static.cninfo.com.cn/"
        url = base + adjunct_url.lstrip("/")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.cninfo.com.cn/",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            content = resp.content
            if not content or len(content) < 200:
                raise DataNotFoundError("PDF 内容为空")
            return content
        except Exception as e:
            raise ProviderError(f"CNInfo PDF 下载失败：{e}") from e

    def get_announcement_pdf_raw(self, req: AnnouncementPDFRequest) -> DataResult:
        market = (req.market or "CN").upper()
        if market != "CN":
            raise ProviderError(f"CninfoProvider 暂不支持 market={market}")

        if req.announcement_id:
            # 若未来需要：可按 announcement_id 直接构造下载链接（CNInfo 现有公开数据多用 adjunctUrl）
            raise ProviderError("当前版本不支持仅凭 announcement_id 直接下载，请使用 keyword+date 查询")

        payload = self._query_announcements(req)
        ann = self._pick_announcement(payload, req)

        adjunct_url = ann.get("adjunctUrl") or ann.get("adjunct_url")
        if not adjunct_url:
            raise DataNotFoundError("公告缺少 adjunctUrl")

        pdf_bytes = self._download_pdf(adjunct_url)

        title = ann.get("announcementTitle") or ann.get("title") or "announcement"
        published_ms = ann.get("announcementTime")
        published_at = None
        if isinstance(published_ms, (int, float)):
            try:
                published_at = datetime.fromtimestamp(published_ms / 1000.0).isoformat()
            except Exception:
                published_at = None

        # raw 返回：一行元数据 + pdf_bytes（由 DataHub 落盘/缓存）
        df = pd.DataFrame(
            [
                {
                    "symbol": req.symbol,
                    "market": market,
                    "keyword": req.keyword,
                    "title": title,
                    "published_at": published_at,
                    "adjunct_url": adjunct_url,
                    "pdf_bytes": pdf_bytes,
                    "filename_hint": _sanitize_filename(title) + ".pdf",
                }
            ]
        )
        return DataResult(
            df=df,
            meta=DataMeta(
                dataset=DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_RAW,
                source=self.name,
                fetched_at=datetime.utcnow(),
                cached=False,
                params={"request": asdict(req)},
            ),
        )
