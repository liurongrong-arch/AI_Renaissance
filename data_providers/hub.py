from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from .cache import DiskCache
from .errors import DataNotFoundError, DatasetNotSupportedError, ProviderError
from .documents.pdf import parse_pdf_to_pages, sha256_bytes
from .normalizers import normalize_financial_statements
from .rate_limit import SimpleRateLimiter
from .schemas import (
    AnnouncementPDFRequest,
    DataMeta,
    DataResult,
    DatasetType,
    FinancialStatementsRequest,
    PriceOHLCVRequest,
    SpotQuoteRequest,
    Symbol,
)
from .providers import AkShareProvider, BaseProvider, CninfoProvider, EastMoneyProvider
from .symbols import SymbolResolver


def _default_cache_dir() -> Path:
    # 避免在仓库内生成缓存文件；默认落在用户目录。
    return Path.home() / ".cache" / "ai_renaissance" / "datahub"


def _default_docs_dir() -> Path:
    return _default_cache_dir() / "documents"


class DataHub:
    """统一数据入口：Provider 路由 + 缓存 + 限频 + 错误归一化。"""

    def __init__(
        self,
        providers: Optional[Iterable[BaseProvider]] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl_seconds: int = 3600,
        cache_ttls: Optional[dict] = None,
        min_interval_seconds: float = 0.2,
    ):
        self.providers: List[BaseProvider] = (
            list(providers)
            if providers
            else [AkShareProvider(), EastMoneyProvider(), CninfoProvider()]
        )
        self.cache = DiskCache(cache_dir or _default_cache_dir(), ttl_seconds=cache_ttl_seconds)
        self.ratelimiter = SimpleRateLimiter(min_interval_seconds=min_interval_seconds)
        self.symbols = SymbolResolver(self.providers)
        self.docs_dir = _default_docs_dir()
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        # 分级缓存策略（默认值可在初始化时覆盖）
        self.cache_ttls = {
            DatasetType.PRICE_OHLCV_DAILY: 24 * 3600,
            DatasetType.FUNDAMENTALS_FIN_STMT_RAW: 7 * 24 * 3600,
            DatasetType.FUNDAMENTALS_FIN_STMT_NORMALIZED: 7 * 24 * 3600,
            DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_RAW: 30 * 24 * 3600,
            DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_PARSED: 30 * 24 * 3600,
        }
        if cache_ttls:
            # 允许传入 {DatasetType: seconds} 或 {str: seconds}
            for k, v in cache_ttls.items():
                try:
                    ds = k if isinstance(k, DatasetType) else DatasetType(str(k))
                    self.cache_ttls[ds] = int(v)
                except Exception:
                    continue

    def _ttl(self, dataset: DatasetType) -> int:
        return int(self.cache_ttls.get(dataset, self.cache.ttl_seconds))

    def resolve_symbol(self, raw: str, market: str = "CN", prefer_sources: Optional[List[str]] = None) -> Symbol:
        """把“股票名称/股票代码”解析为统一代码。"""

        return self.symbols.resolve(raw=raw, market=market, prefer_sources=prefer_sources)

    def _provider_candidates(self, dataset: DatasetType, prefer: Optional[List[str]] = None):
        candidates = [p for p in self.providers if p.supports(dataset)]
        if prefer:
            # prefer 中的 provider 名称越靠前优先级越高
            prefer_order = {name: i for i, name in enumerate(prefer)}
            candidates.sort(key=lambda p: prefer_order.get(getattr(p, "name", ""), 9999))
        return candidates

    def get_price_ohlcv_daily(
        self,
        req: PriceOHLCVRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        dataset = DatasetType.PRICE_OHLCV_DAILY

        resolved = self.resolve_symbol(req.symbol, market=req.market, prefer_sources=prefer_sources)
        req = PriceOHLCVRequest(
            symbol=resolved.code,
            start_date=req.start_date,
            end_date=req.end_date,
            adjust=req.adjust,
            market=req.market,
            extra={
                **(req.extra or {}),
                "symbol_raw": req.symbol,
                "symbol_resolved": {"code": resolved.code, "name": resolved.name},
            },
        )

        providers = self._provider_candidates(dataset, prefer_sources)
        if not providers:
            raise DatasetNotSupportedError(f"未注册可用 Provider：{dataset}")

        cache_key = self.cache.make_key(
            namespace=dataset.value,
            payload=json.dumps(asdict(req), sort_keys=True, ensure_ascii=False),
        )
        if use_cache:
            cached = self.cache.get(cache_key, ttl_seconds=self._ttl(dataset))
            if cached is not None and isinstance(cached, pd.DataFrame):
                return DataResult(
                    df=cached,
                    meta=DataMeta(
                        dataset=dataset,
                        source="cache",
                        fetched_at=datetime.utcnow(),
                        cached=True,
                        params={"cache_key": cache_key},
                    ),
                )

        errors: List[str] = []
        for p in providers:
            try:
                self.ratelimiter.wait(key=f"{p.name}:{dataset.value}")
                result = p.get_price_ohlcv_daily(req)
                if result.df is None or result.df.empty:
                    raise DataNotFoundError(f"{p.name} 返回空数据")
                if use_cache:
                    self.cache.set(cache_key, result.df)
                # 补充 meta.params：把原始与归一化 symbol 透出
                merged_params = {**(result.meta.params or {})}
                merged_params.update({"symbol_raw": req.extra.get("symbol_raw"), "symbol": resolved.code, "name": resolved.name})
                return DataResult(
                    df=result.df,
                    meta=DataMeta(
                        dataset=result.meta.dataset,
                        source=result.meta.source,
                        fetched_at=result.meta.fetched_at,
                        cached=result.meta.cached,
                        params=merged_params,
                    ),
                )
            except Exception as e:
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                continue

        raise ProviderError("所有 Provider 取数失败：" + " | ".join(errors))

    def get_spot_quote(
        self,
        req: SpotQuoteRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = False,
    ) -> DataResult:
        dataset = DatasetType.PRICE_SPOT_QUOTE

        resolved: Optional[Symbol] = None
        if req.symbol:
            resolved = self.resolve_symbol(req.symbol, market=req.market, prefer_sources=prefer_sources)
            req = SpotQuoteRequest(
                symbol=resolved.code,
                market=req.market,
                extra={
                    **(req.extra or {}),
                    "symbol_raw": req.symbol,
                    "symbol_resolved": {"code": resolved.code, "name": resolved.name},
                },
            )

        providers = self._provider_candidates(dataset, prefer_sources)
        if not providers:
            raise DatasetNotSupportedError(f"未注册可用 Provider：{dataset}")

        # spot 行情默认不缓存
        errors: List[str] = []
        for p in providers:
            try:
                self.ratelimiter.wait(key=f"{p.name}:{dataset.value}")
                result = p.get_spot_quote(req)
                if result.df is None or result.df.empty:
                    raise DataNotFoundError(f"{p.name} 返回空数据")
                if resolved is None:
                    return result
                merged_params = {**(result.meta.params or {})}
                merged_params.update({"symbol_raw": req.extra.get("symbol_raw"), "symbol": resolved.code, "name": resolved.name})
                return DataResult(
                    df=result.df,
                    meta=DataMeta(
                        dataset=result.meta.dataset,
                        source=result.meta.source,
                        fetched_at=result.meta.fetched_at,
                        cached=result.meta.cached,
                        params=merged_params,
                    ),
                )
            except Exception as e:
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                continue
        raise ProviderError("所有 Provider 取数失败：" + " | ".join(errors))

    def get_financial_statements_raw(
        self,
        req: FinancialStatementsRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        """获取三表 raw 数据（statement + 原始字段宽表）。

        当前实现：CN 走 EastMoneyProvider。
        """

        dataset = DatasetType.FUNDAMENTALS_FIN_STMT_RAW
        # 财报目前仅支持“代码/名称” -> CN 代码（6位）
        resolved = self.resolve_symbol(req.symbol, market=req.market, prefer_sources=prefer_sources)
        req = FinancialStatementsRequest(
            symbol=resolved.code,
            market=req.market,
            report_date=req.report_date,
            extra={
                **(req.extra or {}),
                "symbol_raw": req.symbol,
                "symbol_resolved": {"code": resolved.code, "name": resolved.name},
            },
        )

        providers = self._provider_candidates(dataset, prefer_sources)
        if not providers:
            raise DatasetNotSupportedError(f"未注册可用 Provider：{dataset}")

        cache_key = self.cache.make_key(
            namespace=dataset.value,
            payload=json.dumps(asdict(req), sort_keys=True, ensure_ascii=False),
        )
        if use_cache:
            cached = self.cache.get(cache_key, ttl_seconds=self._ttl(dataset))
            if cached is not None and isinstance(cached, pd.DataFrame):
                return DataResult(
                    df=cached,
                    meta=DataMeta(
                        dataset=dataset,
                        source="cache",
                        fetched_at=datetime.utcnow(),
                        cached=True,
                        params={"cache_key": cache_key, "symbol": resolved.code, "name": resolved.name},
                    ),
                )

        errors: List[str] = []
        for p in providers:
            try:
                self.ratelimiter.wait(key=f"{p.name}:{dataset.value}")
                result = p.get_financial_statements_raw(req)
                if result.df is None or result.df.empty:
                    raise DataNotFoundError(f"{p.name} 返回空数据")
                if use_cache:
                    self.cache.set(cache_key, result.df)
                merged_params = {**(result.meta.params or {})}
                merged_params.update({"symbol_raw": req.extra.get("symbol_raw"), "symbol": resolved.code, "name": resolved.name})
                return DataResult(
                    df=result.df,
                    meta=DataMeta(
                        dataset=result.meta.dataset,
                        source=result.meta.source,
                        fetched_at=result.meta.fetched_at,
                        cached=result.meta.cached,
                        params=merged_params,
                    ),
                )
            except Exception as e:
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                continue
        raise ProviderError("所有 Provider 取数失败：" + " | ".join(errors))

    def get_financial_statements_normalized(
        self,
        req: FinancialStatementsRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        """获取“七步验证链常用指标集”（可选产出）。

        设计：先取 raw，再做统一归一化。
        """

        dataset = DatasetType.FUNDAMENTALS_FIN_STMT_NORMALIZED
        raw_res = self.get_financial_statements_raw(req, prefer_sources=prefer_sources, use_cache=use_cache)

        cache_key = self.cache.make_key(
            namespace=dataset.value,
            payload=json.dumps(raw_res.meta.params, sort_keys=True, ensure_ascii=False),
        )
        if use_cache:
            cached = self.cache.get(cache_key, ttl_seconds=self._ttl(dataset))
            if cached is not None and isinstance(cached, pd.DataFrame):
                return DataResult(
                    df=cached,
                    meta=DataMeta(
                        dataset=dataset,
                        source="cache",
                        fetched_at=datetime.utcnow(),
                        cached=True,
                        params={"cache_key": cache_key, "from": "raw"},
                    ),
                )

        df = normalize_financial_statements(raw_res.df)
        if df is None or df.empty:
            raise DataNotFoundError("normalized 输出为空")
        if use_cache:
            self.cache.set(cache_key, df)
        return DataResult(
            df=df,
            meta=DataMeta(
                dataset=dataset,
                source=f"normalized({raw_res.meta.source})",
                fetched_at=datetime.utcnow(),
                cached=False,
                params={"from": raw_res.meta.source, **(raw_res.meta.params or {})},
            ),
        )

    def get_announcement_pdf_raw(
        self,
        req: AnnouncementPDFRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        """下载公告 PDF 原文并落盘，返回元数据 + 本地路径。"""

        dataset = DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_RAW
        market = (req.market or "CN").upper()
        if market != "CN":
            raise DatasetNotSupportedError(f"公告 PDF 当前仅支持 CNInfo（market=CN），收到：{market}")

        resolved = self.resolve_symbol(req.symbol, market=req.market, prefer_sources=prefer_sources)
        req = AnnouncementPDFRequest(
            symbol=resolved.code,
            market=req.market,
            start_date=req.start_date,
            end_date=req.end_date,
            keyword=req.keyword,
            announcement_id=req.announcement_id,
            page_size=req.page_size,
            extra={
                **(req.extra or {}),
                "symbol_raw": req.symbol,
                "symbol_resolved": {"code": resolved.code, "name": resolved.name},
            },
        )

        providers = self._provider_candidates(dataset, prefer_sources)
        if not providers:
            raise DatasetNotSupportedError(f"未注册可用 Provider：{dataset}")

        cache_key = self.cache.make_key(
            namespace=dataset.value,
            payload=json.dumps(asdict(req), sort_keys=True, ensure_ascii=False),
        )
        if use_cache:
            cached = self.cache.get(cache_key, ttl_seconds=self._ttl(dataset))
            if cached is not None and isinstance(cached, pd.DataFrame):
                return DataResult(
                    df=cached,
                    meta=DataMeta(
                        dataset=dataset,
                        source="cache",
                        fetched_at=datetime.utcnow(),
                        cached=True,
                        params={"cache_key": cache_key},
                    ),
                )

        errors: List[str] = []
        for p in providers:
            try:
                self.ratelimiter.wait(key=f"{p.name}:{dataset.value}")
                result = p.get_announcement_pdf_raw(req)
                if result.df is None or result.df.empty:
                    raise DataNotFoundError(f"{p.name} 返回空数据")
                if "pdf_bytes" not in result.df.columns:
                    raise ProviderError(f"{p.name} 未返回 pdf_bytes")
                pdf_bytes = result.df.iloc[0]["pdf_bytes"]
                if not isinstance(pdf_bytes, (bytes, bytearray)):
                    raise ProviderError("pdf_bytes 类型不正确")

                sha = sha256_bytes(bytes(pdf_bytes))
                filename_hint = str(result.df.iloc[0].get("filename_hint") or f"{sha}.pdf")
                pdf_path = self.docs_dir / f"{sha}__{filename_hint}"
                if not pdf_path.exists():
                    pdf_path.write_bytes(bytes(pdf_bytes))

                out_df = result.df.copy()
                out_df["pdf_sha256"] = sha
                out_df["pdf_path"] = str(pdf_path)
                out_df["pdf_size_bytes"] = len(pdf_bytes)
                out_df = out_df.drop(columns=["pdf_bytes"], errors="ignore")

                if use_cache:
                    self.cache.set(cache_key, out_df)

                merged_params = {**(result.meta.params or {})}
                merged_params.update({"symbol": resolved.code, "name": resolved.name, "pdf_path": str(pdf_path), "pdf_sha256": sha})
                return DataResult(
                    df=out_df,
                    meta=DataMeta(
                        dataset=dataset,
                        source=result.meta.source,
                        fetched_at=result.meta.fetched_at,
                        cached=False,
                        params=merged_params,
                    ),
                )
            except Exception as e:
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                continue
        raise ProviderError("所有 Provider 取数失败：" + " | ".join(errors))

    def get_announcement_pdf_parsed(
        self,
        req: AnnouncementPDFRequest,
        prefer_sources: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> DataResult:
        """解析公告 PDF，返回 page 级文本，用于可追溯引用。"""

        dataset = DatasetType.DOCUMENTS_ANNOUNCEMENTS_PDF_PARSED
        raw = self.get_announcement_pdf_raw(req, prefer_sources=prefer_sources, use_cache=use_cache)
        if raw.df is None or raw.df.empty:
            raise DataNotFoundError("raw 为空")
        pdf_path = raw.df.iloc[0].get("pdf_path")
        if not pdf_path:
            raise ProviderError("raw 未返回 pdf_path")

        cache_key = self.cache.make_key(
            namespace=dataset.value,
            payload=json.dumps({"pdf_path": pdf_path, "pdf_sha256": raw.df.iloc[0].get("pdf_sha256")}, sort_keys=True, ensure_ascii=False),
        )
        if use_cache:
            cached = self.cache.get(cache_key, ttl_seconds=self._ttl(dataset))
            if cached is not None and isinstance(cached, pd.DataFrame):
                return DataResult(
                    df=cached,
                    meta=DataMeta(
                        dataset=dataset,
                        source="cache",
                        fetched_at=datetime.utcnow(),
                        cached=True,
                        params={"cache_key": cache_key, "pdf_path": pdf_path},
                    ),
                )

        pdf_bytes = Path(str(pdf_path)).read_bytes()
        pages_df = parse_pdf_to_pages(pdf_bytes)
        if pages_df is None or pages_df.empty:
            raise DataNotFoundError("PDF 解析为空")
        pages_df.insert(0, "pdf_path", str(pdf_path))
        pages_df.insert(1, "pdf_sha256", raw.df.iloc[0].get("pdf_sha256"))

        if use_cache:
            self.cache.set(cache_key, pages_df)

        return DataResult(
            df=pages_df,
            meta=DataMeta(
                dataset=dataset,
                source=f"parsed({raw.meta.source})",
                fetched_at=datetime.utcnow(),
                cached=False,
                params={"pdf_path": str(pdf_path), **(raw.meta.params or {})},
            ),
        )
