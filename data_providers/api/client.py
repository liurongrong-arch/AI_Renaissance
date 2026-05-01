from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..hub import DataHub
from ..schemas import (
    AnnouncementPDFRequest,
    DataResult,
    FinancialStatementsRequest,
    PriceOHLCVRequest,
    SpotQuoteRequest,
)


@dataclass
class DataAPI:
    """对外 Data API（面向 Agent）。

    说明：
    - 这是 `DataHub` 的轻量封装层：提供更直观的函数签名。
    - 若你希望统一注入 providers/cache 策略，可在初始化 DataAPI 时传入自定义 hub。
    """

    hub: DataHub = DataHub()

    # ----------- 量价（当前仅日线） -----------
    def price_daily(
        self,
        symbol: str,
        market: str = "CN",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "",
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        return self.hub.get_price_ohlcv_daily(
            PriceOHLCVRequest(
                symbol=symbol,
                market=market,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            ),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )

    def spot_quote(
        self,
        symbol: Optional[str] = None,
        market: str = "CN",
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = False,
    ) -> DataResult:
        return self.hub.get_spot_quote(
            SpotQuoteRequest(symbol=symbol, market=market),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )

    # ----------- 财报（三表） -----------
    def financial_statements_raw(
        self,
        symbol: str,
        market: str = "CN",
        report_date: Optional[str] = None,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        return self.hub.get_financial_statements_raw(
            FinancialStatementsRequest(symbol=symbol, market=market, report_date=report_date),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )

    def financial_statements_normalized(
        self,
        symbol: str,
        market: str = "CN",
        report_date: Optional[str] = None,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        return self.hub.get_financial_statements_normalized(
            FinancialStatementsRequest(symbol=symbol, market=market, report_date=report_date),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )

    # ----------- 公告 PDF（巨潮） -----------
    def announcement_pdf_raw(
        self,
        symbol: str,
        market: str = "CN",
        keyword: str = "年报",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        return self.hub.get_announcement_pdf_raw(
            AnnouncementPDFRequest(
                symbol=symbol,
                market=market,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            ),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )

    def announcement_pdf_parsed(
        self,
        symbol: str,
        market: str = "CN",
        keyword: str = "年报",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        return self.hub.get_announcement_pdf_parsed(
            AnnouncementPDFRequest(
                symbol=symbol,
                market=market,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            ),
            prefer_sources=prefer_sources,
            use_cache=use_cache,
        )
