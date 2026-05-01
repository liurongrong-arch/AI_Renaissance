from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import pandas as pd


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("，", "").strip()
        if s in ("", "-", "--", "N/A", "null"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _pick(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in row:
            v = _safe_float(row.get(k))
            if v is not None:
                return v
    return None


def _infer_report_date(row: Dict[str, Any]) -> Optional[str]:
    for k in ("REPORT_DATE", "REPORTDATE", "report_date", "reportDate", "date"):
        v = row.get(k)
        if isinstance(v, str) and v:
            # 统一成 YYYY-MM-DD
            if len(v) >= 10:
                return v[:10]
            return v
    return None


def normalize_financial_statements(raw_df: pd.DataFrame) -> pd.DataFrame:
    """把三表 raw 数据归一化为“七步验证链常用指标集”。

    输入：`EastMoneyProvider` 的 raw DataFrame（包含 `statement` 列）。
    输出：按 report_date 的宽表，一行一个报告期。
    """

    if raw_df is None or raw_df.empty:
        return pd.DataFrame()
    if "statement" not in raw_df.columns:
        return pd.DataFrame()

    # 取每个 statement 的第一行（当前接口默认只取一个 dates，因此通常只有 1 行）
    by_stmt: Dict[str, Dict[str, Any]] = {}
    for stype in ("balance", "income", "cashflow"):
        sub = raw_df[raw_df["statement"] == stype]
        if sub.empty:
            continue
        by_stmt[stype] = sub.iloc[0].to_dict()

    income = by_stmt.get("income", {})
    cashflow = by_stmt.get("cashflow", {})
    balance = by_stmt.get("balance", {})

    report_date = _infer_report_date(income) or _infer_report_date(cashflow) or _infer_report_date(balance)

    out = {
        "report_date": report_date,
        # 利润表
        "revenue": _pick(income, "TOTAL_OPERATE_INCOME", "totalOperateIncome", "revenue", "营业收入"),
        "net_profit": _pick(income, "PARENT_NETPROFIT", "parentNetProfit", "net_profit", "归母净利润"),
        "operating_profit": _pick(income, "OPERATE_PROFIT", "operateProfit", "operating_profit", "营业利润"),
        "financial_expense": _pick(income, "FINANCE_EXPENSE", "financialExpense", "financial_expense", "财务费用"),
        # 现金流量表
        "operating_cf": _pick(cashflow, "NETCASH_OPERATE", "netCashFromOperatingActivities", "operating_cf", "经营活动现金流净额"),
        "sales_cash": _pick(cashflow, "SALES_SERVICES", "salesServicesReceivedCash", "sales_cash", "销售收现"),
        "capex": _pick(cashflow, "CONSTRUCT_LONG_ASSET", "cashPaidForFixedAssets", "capex", "购建固定资产支付的现金"),
        # 资产负债表
        "accounts_receivable": _pick(balance, "ACCOUNTS_RECE", "accountsReceivable", "accounts_receivable", "应收账款"),
        "inventory": _pick(balance, "INVENTORY", "inventory", "存货"),
        "contract_liability": _pick(balance, "CONTRACT_LIAB", "contractLiability", "contract_liability", "合同负债", "预收款项"),
        "construction_in_progress": _pick(balance, "CIP", "constructionInProgress", "construction_in_progress", "在建工程"),
        "fixed_assets": _pick(balance, "FIXED_ASSET", "fixedAssets", "fixed_assets", "固定资产"),
        "cash": _pick(balance, "MONETARYFUNDS", "cash", "货币资金"),
        "short_borrowing": _pick(balance, "SHORT_LOAN", "shortLoan", "short_borrowing", "短期借款"),
        "long_borrowing": _pick(balance, "LONG_LOAN", "longLoan", "long_borrowing", "长期借款"),
        "equity": _pick(balance, "TOTAL_PARENT_EQUITY", "totalParentEquity", "equity", "归母所有者权益"),
    }

    return pd.DataFrame([out])
