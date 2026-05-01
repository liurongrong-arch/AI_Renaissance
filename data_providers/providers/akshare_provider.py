from __future__ import annotations

from datetime import datetime
import time
from typing import Set

import pandas as pd

from ..errors import DataNotFoundError, MissingDependencyError, ProviderError
from ..schemas import (
    DataMeta,
    DataResult,
    DatasetType,
    PriceOHLCVRequest,
    Symbol,
    SpotQuoteRequest,
)
from .base import BaseProvider


def _require_akshare():
    try:
        import akshare as ak  # type: ignore

        return ak
    except Exception as e:  # pragma: no cover
        raise MissingDependencyError(
            "未安装 akshare，无法使用 AkShareProvider。请先安装依赖：`uv pip install akshare`"
        ) from e


def _normalize_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # AkShare A股历史行情常见列：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
    col_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "换手率": "turnover",
    }
    out = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}).copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out


def _normalize_spot_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    col_map = {
        "代码": "symbol",
        "名称": "name",
        "最新价": "last",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "成交量": "volume",
        "成交额": "amount",
        "最高": "high",
        "最低": "low",
        "今开": "open",
        "昨收": "prev_close",
        "换手率": "turnover",
    }
    out = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}).copy()
    return out


def _call_with_retries(fn, retries: int = 2, backoff_seconds: float = 0.6):
    """对第三方数据源做轻量重试，降低偶发网络抖动的失败率。"""

    last_exc = None
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # pragma: no cover
            last_exc = e
            if i >= retries:
                break
            time.sleep(backoff_seconds * (2**i))
    raise last_exc


class AkShareProvider(BaseProvider):
    name = "akshare"

    @property
    def capabilities(self) -> Set[DatasetType]:
        return {
            DatasetType.PRICE_OHLCV_DAILY,
            DatasetType.PRICE_SPOT_QUOTE,
        }

    def get_price_ohlcv_daily(self, req: PriceOHLCVRequest) -> DataResult:
        ak = _require_akshare()
        try:
            start = req.start_date.replace("-", "") if req.start_date else ""
            end = req.end_date.replace("-", "") if req.end_date else ""

            market = (req.market or "CN").upper()
            if market == "CN":
                raw = _call_with_retries(
                    lambda: ak.stock_zh_a_hist(
                        symbol=req.symbol,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust=req.adjust,
                    )
                )
            elif market == "HK":
                raw = _call_with_retries(
                    lambda: ak.stock_hk_hist(
                        symbol=req.symbol,
                        period="daily",
                        start_date=start or "19700101",
                        end_date=end or "22220101",
                        adjust=req.adjust,
                    )
                )
            elif market == "US":
                raw = _call_with_retries(
                    lambda: ak.stock_us_hist(
                        symbol=req.symbol,
                        period="daily",
                        start_date=start or "19700101",
                        end_date=end or "22220101",
                        adjust=req.adjust,
                    )
                )
            else:
                raise ProviderError(f"AkShareProvider 暂不支持 market={market}")

            df = _normalize_ohlcv_df(raw)
            if df.empty:
                raise DataNotFoundError(f"AkShare 返回空数据：{req.symbol}")
            return DataResult(
                df=df,
                meta=DataMeta(
                    dataset=DatasetType.PRICE_OHLCV_DAILY,
                    source=self.name,
                    fetched_at=datetime.utcnow(),
                    cached=False,
                    params={
                        "symbol": req.symbol,
                        "start_date": req.start_date,
                        "end_date": req.end_date,
                        "adjust": req.adjust,
                        "market": req.market,
                    },
                ),
            )
        except (DataNotFoundError, MissingDependencyError):
            raise
        except Exception as e:
            raise ProviderError(f"AkShareProvider.get_price_ohlcv_daily 失败：{e}") from e

    def get_spot_quote(self, req: SpotQuoteRequest) -> DataResult:
        ak = _require_akshare()
        try:
            market = (req.market or "CN").upper()
            if market == "CN":
                raw = _call_with_retries(lambda: ak.stock_zh_a_spot_em())
            elif market == "HK":
                raw = _call_with_retries(lambda: ak.stock_hk_spot_em())
            elif market == "US":
                raw = _call_with_retries(lambda: ak.stock_us_spot_em())
            else:
                raise ProviderError(f"AkShareProvider 暂不支持 market={market}")

            if raw is None or raw.empty:
                raise DataNotFoundError("AkShare spot 返回空数据")
            df = _normalize_spot_df(raw)
            if req.symbol:
                # 部分 market 的 symbol 可能不是字符串
                if "symbol" in df.columns:
                    df = df[df["symbol"].astype(str) == str(req.symbol)]
            return DataResult(
                df=df.reset_index(drop=True),
                meta=DataMeta(
                    dataset=DatasetType.PRICE_SPOT_QUOTE,
                    source=self.name,
                    fetched_at=datetime.utcnow(),
                    cached=False,
                    params={"symbol": req.symbol, "market": req.market},
                ),
            )
        except (DataNotFoundError, MissingDependencyError):
            raise
        except Exception as e:
            raise ProviderError(f"AkShareProvider.get_spot_quote 失败：{e}") from e

    def resolve_symbol(self, raw: str, market: str = "CN") -> Symbol:
        """支持用“股票名称/代码”解析到各市场可用的 code。

        - CN：返回 A 股 6 位代码
        - HK：返回 5 位代码（前导 0 补齐）
        - US：返回东财美股代码（例如 105.MSFT），用于 `stock_us_hist`
        """

        ak = _require_akshare()
        q = (raw or "").strip()
        if not q:
            raise DataNotFoundError("symbol 为空")

        market = (market or "CN").upper()

        # 代码直通（不依赖联网）
        if market == "CN" and q.isdigit() and len(q) == 6:
            return Symbol(code=q, name=None, market=market)
        if market == "HK" and q.isdigit() and len(q) in (4, 5):
            return Symbol(code=q.zfill(5), name=None, market=market)
        if market == "US" and "." in q:
            return Symbol(code=q.upper(), name=None, market=market)

        try:
            # CN 优先：ak.stock_info_a_code_name()
            if market == "CN" and hasattr(ak, "stock_info_a_code_name"):
                df = ak.stock_info_a_code_name()
                if df is not None and not df.empty and "name" in df.columns and "code" in df.columns:
                    hit = df[df["name"] == q]
                    if hit.empty:
                        hit = df[df["name"].astype(str).str.contains(q, na=False)]
                    if not hit.empty:
                        row = hit.iloc[0]
                        return Symbol(code=str(row["code"]), name=str(row["name"]), market=market)

            # fallback：用对应市场的 spot 列表做映射
            if market == "CN":
                spot = _call_with_retries(lambda: ak.stock_zh_a_spot_em())
            elif market == "HK":
                spot = _call_with_retries(lambda: ak.stock_hk_spot_em())
            elif market == "US":
                spot = _call_with_retries(lambda: ak.stock_us_spot_em())
            else:
                raise DataNotFoundError(f"不支持 market={market}")

            if spot is None or spot.empty:
                raise DataNotFoundError("spot 返回空")
            if "名称" not in spot.columns or "代码" not in spot.columns:
                raise DataNotFoundError("spot 缺少 代码/名称 列")

            # 对 US：用户可能输入 ticker（如 MSFT/AAPL），代码列通常包含 ticker
            hit = spot[spot["名称"].astype(str) == q]
            if hit.empty:
                hit = spot[spot["名称"].astype(str).str.contains(q, na=False)]
            if hit.empty and market == "US":
                hit = spot[spot["代码"].astype(str).str.contains(q.upper(), na=False)]

            if hit.empty:
                raise DataNotFoundError(f"未找到名称匹配：{q}")
            row = hit.iloc[0]
            code = str(row["代码"])
            if market == "HK" and code.isdigit():
                code = code.zfill(5)
            return Symbol(code=code, name=str(row["名称"]), market=market)
        except Exception as e:
            raise ProviderError(f"AkShareProvider.resolve_symbol 失败：{e}") from e
