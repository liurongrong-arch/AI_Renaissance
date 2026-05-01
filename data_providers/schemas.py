from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import pandas as pd


class DatasetType(str, Enum):
    """统一的数据集标识（用于路由/缓存/观测）。"""

    PRICE_OHLCV_DAILY = "price.ohlcv.daily"
    PRICE_SPOT_QUOTE = "price.spot.quote"

    FUNDAMENTALS_FIN_STMT_RAW = "fundamentals.financial_statements.raw"
    FUNDAMENTALS_FIN_STMT_NORMALIZED = "fundamentals.financial_statements.normalized"

    DOCUMENTS_ANNOUNCEMENTS_PDF_RAW = "documents.announcements.pdf.raw"
    DOCUMENTS_ANNOUNCEMENTS_PDF_PARSED = "documents.announcements.pdf.parsed"


class StatementType(str, Enum):
    BALANCE = "balance"
    INCOME = "income"
    CASHFLOW = "cashflow"


@dataclass(frozen=True)
class Symbol:
    """统一标的标识。

    约定：
    - Agent 可输入“股票名称/股票代码”，由 DataHub 负责解析。
    - provider 侧通常使用 `code`（例如 A 股 6 位代码）。
    """

    code: str
    name: Optional[str] = None
    market: str = "CN"
    exchange: Optional[str] = None  # 预留：SSE/SZSE...


@dataclass(frozen=True)
class DataMeta:
    dataset: DatasetType
    source: str
    fetched_at: datetime
    cached: bool = False
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataResult:
    """统一返回格式：数据 + 元信息。

    约定：
    - 所有时间序列数据必须包含 `date` 列（datetime64[ns]），并按 date 升序。
    - 价格类 OHLCV 统一列：date/open/high/low/close/volume/amount（可缺省部分）。
    """

    df: pd.DataFrame
    meta: DataMeta

    def is_empty(self) -> bool:
        return self.df is None or self.df.empty


@dataclass(frozen=True)
class PriceOHLCVRequest:
    symbol: str
    # 口径确认：量价数据当前阶段仅支持“日线”（daily）
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD
    adjust: str = ""  # "" | "qfq" | "hfq"（由 Provider 自行解释）
    market: str = "CN"  # 预留：CN/US/HK...
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpotQuoteRequest:
    symbol: Optional[str] = None  # None 表示全量
    market: str = "CN"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialStatementsRequest:
    """财报（三表）请求。

    说明：
    - 当前先支持 CN（东方财富 NewFinanceAnalysis）；HK/US 后续接入。
    - report_date: 期末日期（YYYY-MM-DD）。为空时由 Provider 决定（默认取“最近可披露期”）。
    """

    symbol: str
    market: str = "CN"
    report_date: Optional[str] = None  # YYYY-MM-DD
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnnouncementPDFRequest:
    """公告 PDF 请求（巨潮/交易所公告等）。

    设计目标：
    - `raw`：下载 PDF 原文并落盘，返回可追溯元数据与本地路径
    - `parsed`：逐页解析文本，返回 page 级结果，便于引用（page->text）
    """

    symbol: str
    market: str = "CN"
    # 查询范围（CNInfo 支持 seDate: start~end）
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD
    keyword: str = "年报"  # 默认取年报
    announcement_id: Optional[str] = None  # 若已知可直接下载
    page_size: int = 30
    extra: Dict[str, Any] = field(default_factory=dict)
