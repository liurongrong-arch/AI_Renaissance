from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Dict, Set

import pandas as pd

from ..errors import DataNotFoundError, MissingDependencyError, ProviderError
from ..schemas import (
    DataMeta,
    DataResult,
    DatasetType,
    FinancialStatementsRequest,
    StatementType,
)
from .base import BaseProvider


def _require_requests():
    try:
        import requests  # type: ignore

        return requests
    except Exception as e:  # pragma: no cover
        raise MissingDependencyError(
            "未安装 requests，无法使用 EastMoneyProvider。请先安装依赖：`uv pip install requests`"
        ) from e


def _to_eastmoney_code(cn_code: str) -> str:
    """A 股 6 位代码 -> 东方财富 code（SHxxxxxx/SZxxxxxx）。"""

    code = (cn_code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return ""
    if code.startswith("6"):
        return f"SH{code}"
    if code.startswith(("0", "3")):
        return f"SZ{code}"
    return ""


def _default_latest_report_date(now: datetime | None = None) -> str:
    """按披露节奏推断“最近可取到”的报告期。

    Q1(03-31)→4/30  Q2(06-30)→8/31  Q3(09-30)→10/31  Q4(12-31)→次年4/30
    """

    now = now or datetime.now()
    y = now.year
    if now >= datetime(y + 1, 4, 30):
        return f"{y}-12-31"
    if now >= datetime(y, 10, 31):
        return f"{y}-09-30"
    if now >= datetime(y, 8, 31):
        return f"{y}-06-30"
    if now >= datetime(y, 4, 30):
        return f"{y}-03-31"
    return f"{y - 1}-12-31"


class EastMoneyProvider(BaseProvider):
    """东方财富 NewFinanceAnalysis（三表）Provider（当前仅 CN）。"""

    name = "eastmoney"

    @property
    def capabilities(self) -> Set[DatasetType]:
        return {
            DatasetType.FUNDAMENTALS_FIN_STMT_RAW,
        }

    def get_financial_statements_raw(self, req: FinancialStatementsRequest) -> DataResult:
        market = (req.market or "CN").upper()
        if market != "CN":
            raise ProviderError(f"EastMoneyProvider 暂不支持 market={market}")

        requests = _require_requests()

        em_code = _to_eastmoney_code(req.symbol)
        if not em_code:
            raise ProviderError(f"无法转换为东方财富 code：{req.symbol}")

        report_date = req.report_date or _default_latest_report_date()
        base_url = "https://emweb.eastmoney.com/NewFinanceAnalysis"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://emweb.eastmoney.com/",
        }

        # 说明：这些参数与现有 Agent 实现保持一致（companyType/reportType 等）
        urls: Dict[StatementType, str] = {
            StatementType.BALANCE: f"{base_url}/zcfzbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={em_code}",
            StatementType.INCOME: f"{base_url}/lrbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={em_code}",
            StatementType.CASHFLOW: f"{base_url}/xjllbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={em_code}",
        }

        frames = []
        for stype, url in urls.items():
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                payload = resp.json() or {}
                rows = payload.get("data") or []
                if not isinstance(rows, list):
                    rows = [rows]
                df = pd.DataFrame(rows)
                if df.empty:
                    continue
                df.insert(0, "statement", stype.value)
                # 常见字段：REPORT_DATE / SECURITY_CODE / SECURITY_NAME_ABBR 等，尽量留原样
                frames.append(df)
            except Exception as e:
                raise ProviderError(f"EastMoneyProvider 拉取 {stype.value} 失败：{e}") from e

        if not frames:
            raise DataNotFoundError(f"东方财富返回空数据：{em_code} {report_date}")

        out = pd.concat(frames, ignore_index=True)
        return DataResult(
            df=out,
            meta=DataMeta(
                dataset=DatasetType.FUNDAMENTALS_FIN_STMT_RAW,
                source=self.name,
                fetched_at=datetime.utcnow(),
                cached=False,
                params={
                    "symbol": req.symbol,
                    "market": req.market,
                    "em_code": em_code,
                    "report_date": report_date,
                    "request": asdict(req),
                },
            ),
        )
