from __future__ import annotations

import re
from typing import Iterable, List, Optional

import pandas as pd

from .errors import DataNotFoundError, ProviderError
from .schemas import Symbol


_A_SHARE_CODE_RE = re.compile(r"^\d{6}$")
_HK_CODE_RE = re.compile(r"^\d{4,5}$")
_US_EM_CODE_RE = re.compile(r"^\d+\.[A-Za-z]+$")  # 例如 105.MSFT（东财美股代码）


def _normalize_input(s: str) -> str:
    return (s or "").strip()


def is_a_share_code(s: str) -> bool:
    return bool(_A_SHARE_CODE_RE.match(_normalize_input(s)))


def is_hk_code(s: str) -> bool:
    return bool(_HK_CODE_RE.match(_normalize_input(s)))


def normalize_hk_code(s: str) -> str:
    """港股代码统一为 5 位数字（前导 0 补齐）。"""

    s = _normalize_input(s)
    if not is_hk_code(s):
        return s
    return s.zfill(5)


def is_us_em_code(s: str) -> bool:
    return bool(_US_EM_CODE_RE.match(_normalize_input(s)))


def _pick_one(df: pd.DataFrame, code_col: str, name_col: str) -> Symbol:
    if df is None or df.empty:
        raise DataNotFoundError("未找到匹配标的")
    if len(df) > 1:
        # 先做一次“完全匹配名称/代码”优先，否则视为歧义
        return Symbol(code=str(df.iloc[0][code_col]), name=str(df.iloc[0][name_col]))
    row = df.iloc[0]
    return Symbol(code=str(row[code_col]), name=str(row[name_col]))


class SymbolResolver:
    """把“股票名称/股票代码”解析成统一的 Symbol(code,name)。

    说明：
    - 当前先聚焦 A 股：代码为 6 位数字。
    - 若输入为名称：通过 provider 提供的映射表解析。
    """

    def __init__(self, providers: Iterable[object]):
        self.providers = list(providers)

    def resolve(self, raw: str, market: str = "CN", prefer_sources: Optional[List[str]] = None) -> Symbol:
        raw = _normalize_input(raw)
        if not raw:
            raise DataNotFoundError("symbol 为空")

        market = (market or "CN").upper()

        # CN: A 股 6 位代码
        if market == "CN":
            if is_a_share_code(raw):
                return Symbol(code=raw, name=None, market=market)

        # HK: 4/5 位数字，统一补齐为 5 位
        if market == "HK":
            if is_hk_code(raw):
                return Symbol(code=normalize_hk_code(raw), name=None, market=market)

        # US: 东财美股代码通常是 "105.MSFT" 形态；若输入不是该形态，交给 provider 映射
        if market == "US":
            if is_us_em_code(raw):
                return Symbol(code=raw.upper(), name=None, market=market)

        # 按 prefer_sources 顺序尝试 provider 的 symbol mapping
        providers = self.providers
        if prefer_sources:
            order = {name: i for i, name in enumerate(prefer_sources)}
            providers = sorted(providers, key=lambda p: order.get(getattr(p, "name", ""), 9999))

        errors: List[str] = []
        for p in providers:
            fn = getattr(p, "resolve_symbol", None)
            if not callable(fn):
                continue
            try:
                return fn(raw, market=market)
            except Exception as e:
                errors.append(f"{getattr(p, 'name', type(p).__name__)}: {type(e).__name__}: {e}")
                continue

        raise DataNotFoundError("标的解析失败：" + " | ".join(errors))
