from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Set

from ..schemas import (
    AnnouncementPDFRequest,
    DatasetType,
    FinancialStatementsRequest,
    PriceOHLCVRequest,
    SpotQuoteRequest,
)


class BaseProvider(ABC):
    """数据源 Provider 抽象。

    约定：
    - Provider 只负责“取数 + 最小归一化”，不做业务判断。
    - 统一抛出明确异常（在 DataHub 层做降级/兜底）。
    """

    name: str

    @property
    @abstractmethod
    def capabilities(self) -> Set[DatasetType]:
        raise NotImplementedError

    def supports(self, dataset: DatasetType) -> bool:
        return dataset in self.capabilities

    def get_price_ohlcv_daily(self, req: PriceOHLCVRequest):
        raise NotImplementedError

    def get_spot_quote(self, req: SpotQuoteRequest):
        raise NotImplementedError

    def get_financial_statements_raw(self, req: FinancialStatementsRequest):
        raise NotImplementedError

    def get_announcement_pdf_raw(self, req: AnnouncementPDFRequest):
        raise NotImplementedError

    def resolve_symbol(self, raw: str, market: str = "CN"):
        """可选：把“名称/代码”等输入解析成统一代码。

        返回：`schemas.Symbol`
        """

        raise NotImplementedError
