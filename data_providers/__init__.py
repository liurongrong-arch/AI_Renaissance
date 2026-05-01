"""统一数据访问层（DataHub）。

目标：让 Agent 只关心“要什么数据、怎么分析”，不关心“数据从哪来、怎么拿、怎么缓存/限频”。
"""

from .hub import DataHub
from .schemas import (
    AnnouncementPDFRequest,
    DatasetType,
    DataMeta,
    DataResult,
    FinancialStatementsRequest,
    PriceOHLCVRequest,
    Symbol,
    SpotQuoteRequest,
)
from .symbols import SymbolResolver

__all__ = [
    "DataHub",
    "AnnouncementPDFRequest",
    "DatasetType",
    "DataMeta",
    "DataResult",
    "FinancialStatementsRequest",
    "PriceOHLCVRequest",
    "Symbol",
    "SymbolResolver",
    "SpotQuoteRequest",
]
