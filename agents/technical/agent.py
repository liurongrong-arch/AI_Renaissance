"""
技术指标 Agent - 专家2组

signal_type: technical
Skill 域: skills/technical/
核心能力：传统技术指标融合、量价背离与反转、公司发展沿革辅助研究
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


_TECHNICAL_FUSION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "technical"
    / "traditional_model_fusion"
)
if str(_TECHNICAL_FUSION_ROOT) not in sys.path:
    sys.path.insert(0, str(_TECHNICAL_FUSION_ROOT))

try:
    from fusion_traditional_models.fusion import fuse_signals
    from fusion_traditional_models.runner import (
        RunContext,
        load_rows_from_code,
        load_rows_from_csv,
        run_models,
    )
except Exception:  # pragma: no cover - analyze() 会返回带错误信息的 neutral Signal
    fuse_signals = None
    RunContext = None
    load_rows_from_code = None
    load_rows_from_csv = None
    run_models = None

try:
    from data_sources.cninfo import CninfoDataSource
except Exception:  # pragma: no cover - cninfo 为可选数据源
    CninfoDataSource = None


class TechnicalAgent(BaseAgent):
    """技术指标 Agent（专家2组）"""

    signal_type = "technical"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="技术指标Agent", config=config or {})
        self.load_skills_from_domain("technical")
        self.load_skills_from_domain("data")

    def analyze(self, stock_code: str) -> Signal:
        """
        运行专家2组三类技术 Skill：

        1. traditional_model_fusion：四模型传统技术指标融合；
        2. volume_price_reversal：量价背离与短期反转识别；
        3. company_evolution_analysis：公司发展沿革/节点叙事作为技术信号背景约束。

        数据优先级：
        1. config["ohlcv_rows"] 注入的测试/上游数据；
        2. config["ohlcv_data_source"] 提供的 get_ohlcv/fetch_ohlcv 方法；
        3. config["csv_path"] 指定的 OHLCV CSV；
        4. config["use_live_data"]=True 时尝试 EastMoney 拉取；
        5. 离线兜底样本，保证 Agent 合约测试和本地无网环境可运行。
        """
        self.log(f"开始技术指标分析：{stock_code}")

        if not all([fuse_signals, RunContext, run_models]):
            return self._create_error_signal(
                "传统指标融合模块导入失败，请检查 skills/technical/traditional_model_fusion",
                stock_code,
            )

        try:
            rows, data_status, uncertainties = self._load_ohlcv_rows(stock_code)
            skill_results = [
                self._run_traditional_model_fusion(stock_code, rows, data_status),
                self._run_volume_price_reversal(stock_code, rows, data_status),
                self._run_company_evolution_analysis(stock_code),
            ]
            return self._merge_skill_results(stock_code, rows, data_status, skill_results, uncertainties)
        except Exception as exc:
            self.log(f"技术指标分析失败：{exc}", level="error")
            return self._create_error_signal(str(exc), stock_code)

    def _run_traditional_model_fusion(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
    ) -> Dict[str, Any]:
        """调用 traditional_model_fusion 工程化 Skill。"""
        ctx = RunContext(
            stock_code=stock_code,
            target=self.config.get("target") or stock_code,
            source_name=data_status,
        )
        model_signals = run_models(rows, ctx)
        result = fuse_signals(
            model_signals,
            threshold=float(self.config.get("fusion_threshold", 0.6)),
        )
        fused = result.get("fused_signal", {})
        test_report = self._build_traditional_model_fusion_test_report(
            stock_code=stock_code,
            rows=rows,
            data_status=data_status,
            fusion_result=result,
            ctx=ctx,
        )
        meta = dict(fused.get("meta") or {})
        meta.update(
            {
                "skill_name": "traditional_model_fusion",
                "model_signals": result.get("model_signals", []),
                "validation_report": result.get("validation_report", {}),
                "test_report": test_report,
                "traditional_model_fusion_test_report": test_report,
            }
        )
        return {
            "skill_name": "traditional_model_fusion",
            "direction": str(fused.get("direction", "neutral")),
            "confidence": self._clamp(float(fused.get("confidence", 0.2) or 0.2)),
            "reasoning": str(fused.get("reasoning") or "传统技术指标融合完成。"),
            "signals": list(fused.get("signals") or []),
            "weight": float(fused.get("weight", 1.0) or 1.0),
            "meta": meta,
        }

    def _build_traditional_model_fusion_test_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        fusion_result: Dict[str, Any],
        ctx: Any,
    ) -> Dict[str, Any]:
        """构造 traditional_model_fusion 的可回放测试报告。

        报告结构对齐 `fusion_traditional_models.cli` 的核心 JSON 输出：
        `fused_signal`、`model_signals`、`validation_report`，并补充 Agent 运行时
        的数据来源、样本区间和执行参数，便于 debug_ui/测试用例直接断言。
        """
        fused_signal = dict(fusion_result.get("fused_signal") or {})
        model_signals = list(fusion_result.get("model_signals") or [])
        validation_report = dict(fusion_result.get("validation_report") or {})
        first_row = rows[0] if rows else {}
        last_row = rows[-1] if rows else {}
        model_summary = []
        for item in model_signals:
            signal = item.get("signal") if isinstance(item, dict) else {}
            signal = signal if isinstance(signal, dict) else {}
            model_summary.append(
                {
                    "name": item.get("name") if isinstance(item, dict) else "",
                    "direction": signal.get("direction"),
                    "confidence": signal.get("confidence"),
                    "base_weight": item.get("base_weight") if isinstance(item, dict) else None,
                    "effective_weight": item.get("effective_weight") if isinstance(item, dict) else None,
                    "vote": item.get("vote") if isinstance(item, dict) else None,
                    "notes": item.get("notes", []) if isinstance(item, dict) else [],
                }
            )

        return {
            "report_type": "traditional_model_fusion_test_report",
            "report_version": "0.1-runtime",
            "generated_at": datetime.now().isoformat(),
            "runner": "fusion_traditional_models.runner.run_models + fusion_traditional_models.fusion.fuse_signals",
            "stock_code": stock_code,
            "target": getattr(ctx, "target", stock_code),
            "data_status": data_status,
            "rows_count": len(rows),
            "row_range": {
                "start": first_row.get("date", ""),
                "end": last_row.get("date", ""),
            },
            "data_period": self._rows_date_range(rows),
            "final_signal": {
                "direction": fused_signal.get("direction", "neutral"),
                "confidence": fused_signal.get("confidence", 0.2),
                "reasoning": fused_signal.get("reasoning", ""),
                "signals": list(fused_signal.get("signals") or []),
            },
            "model_count": len(model_signals),
            "model_summary": model_summary,
            "model_signals": model_signals,
            "validation_report": validation_report,
            "raw_fusion_result": {
                "fused_signal": fused_signal,
                "model_signals": model_signals,
                "validation_report": validation_report,
            },
        }

    def _run_volume_price_reversal(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
    ) -> Dict[str, Any]:
        """执行 volume_price_reversal 文档规则的轻量确定性版本。"""
        uncertainties: List[str] = []
        evidence: List[Dict[str, Any]] = []
        if len(rows) < 60:
            uncertainties.append("历史数据不足 60 日，量价背离/反转信号可信度降低。")

        if not rows:
            return self._neutral_skill_result(
                "volume_price_reversal",
                "缺少 OHLCV 行情，无法完成量价背离与反转分析。",
                weight=float(self.config.get("volume_price_reversal_weight", 0.35)),
                confidence=0.2,
                meta={"needs_human_review": True, "uncertainties": ["缺少行情数据"]},
            )

        latest = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else latest
        close = self._to_float(latest.get("close")) or 0.0
        prev_close = self._to_float(prev.get("close")) or close
        volume = self._to_float(latest.get("volume")) or 0.0
        high = self._to_float(latest.get("high")) or close
        low = self._to_float(latest.get("low")) or close
        open_value = self._to_float(latest.get("open")) or close

        recent_20 = rows[-20:] if len(rows) >= 20 else rows
        recent_60 = rows[-60:] if len(rows) >= 60 else rows
        prev_20 = rows[-21:-1] if len(rows) >= 21 else rows[:-1]
        prev_60 = rows[-61:-1] if len(rows) >= 61 else rows[:-1]
        volumes_20 = [self._to_float(r.get("volume")) or 0.0 for r in prev_20 if self._to_float(r.get("volume")) is not None]
        volumes_60 = [self._to_float(r.get("volume")) or 0.0 for r in prev_60 if self._to_float(r.get("volume")) is not None]
        avg_volume_20 = sum(volumes_20) / len(volumes_20) if volumes_20 else volume
        std_volume_60 = self._stddev(volumes_60) or max(avg_volume_20 * 0.25, 1.0)
        vol_surp = (volume - avg_volume_20) / std_volume_60 if std_volume_60 else 0.0
        latest_volume_meta = self._volume_display_meta(volume, allow_decimal=latest.get("volume_raw_unit") == "股")
        avg_volume_20_meta = self._volume_display_meta(avg_volume_20, allow_decimal=any(r.get("volume_raw_unit") == "股" for r in prev_20))

        closes = [self._to_float(r.get("close")) or 0.0 for r in recent_20]
        high_20 = max(closes) if closes else close
        low_20 = min(closes) if closes else close
        is_new_high = close >= high_20 and len(recent_20) >= 10
        is_new_low = close <= low_20 and len(recent_20) >= 10
        day_return = (close - prev_close) / prev_close if prev_close else 0.0
        volume_ratio_20 = volume / avg_volume_20 if avg_volume_20 else 1.0

        full_range = max(high - low, 0.0)
        body = abs(close - open_value)
        upper_shadow = high - max(open_value, close)
        lower_shadow = min(open_value, close) - low
        range_ratio = full_range / prev_close if prev_close else 0.0
        upper_shadow_ratio = upper_shadow / full_range if full_range else 0.0
        lower_shadow_ratio = lower_shadow / full_range if full_range else 0.0
        long_upper_shadow = upper_shadow >= body * 2 and upper_shadow_ratio >= 0.5 and range_ratio >= 0.03
        long_lower_shadow = lower_shadow >= body * 2 and lower_shadow_ratio >= 0.5 and range_ratio >= 0.03
        is_doji = bool(full_range and body / full_range < 0.1 and upper_shadow_ratio >= 0.3 and lower_shadow_ratio >= 0.3)

        amount = self._latest_amount(latest)
        avg_amount_20 = self._average_amount(rows[-20:])
        amount_threshold = self._amount_threshold(stock_code)
        needs_human_review = False
        if amount is None:
            uncertainties.append("成交额字段缺失，绝对成交额过滤器未执行。")
        elif amount < amount_threshold:
            uncertainties.append("绝对成交额不足，VolSurp 信号可能失真。")
        if avg_amount_20 is not None and avg_amount_20 < amount_threshold * 0.5:
            needs_human_review = True
            reasoning = "长期成交额低于分市场阈值的一半，量价反转框架不适用。"
            return self._neutral_skill_result(
                "volume_price_reversal",
                reasoning,
                weight=float(self.config.get("volume_price_reversal_weight", 0.35)),
                confidence=0.25,
                meta={
                    "needs_human_review": True,
                    "risk_level": "high",
                    "time_horizon": "short",
                    "uncertainties": uncertainties + [reasoning],
                    "evidence": evidence,
                },
            )

        direction = "neutral"
        confidence = 0.35
        risk_level = "medium"
        signals: List[str] = []
        key_findings: List[str] = []

        if is_doji:
            confidence = 0.45
            signals.append("十字星犹豫：实体极小且上下影线较长，等待次日方向选择")
            key_findings.append("高位/低位十字星，多空胶着，等待次日方向选择。")
        elif is_new_high and vol_surp < -1:
            direction = "bearish"
            confidence = 0.62 + (0.05 if vol_surp < -1.5 else 0.0)
            risk_level = "medium"
            signals.append(f"形态一·顶背离：20日新高但缩量，VolSurp {vol_surp:.2f}")
        elif is_new_low and vol_surp < -1:
            direction = "bullish"
            confidence = 0.62 + (0.05 if vol_surp < -1.5 else 0.0)
            risk_level = "low"
            signals.append(f"形态二·底背离：20日新低但缩量，VolSurp {vol_surp:.2f}")
        elif day_return >= 0.05 and volume_ratio_20 >= 1.5 and long_upper_shadow:
            direction = "bearish"
            confidence = 0.82 if upper_shadow_ratio > 0.7 else 0.75
            risk_level = "high"
            signals.append(f"形态三·量价齐升乏力：涨幅 {day_return:.2%}，放量 {volume_ratio_20:.2f}x，长上影")
            key_findings.append("巨量长上影线信号须关注 A 股 T+1 与尾盘执行约束。")
        elif day_return <= -0.05 and volume_ratio_20 >= 1.5 and long_lower_shadow:
            direction = "bullish"
            confidence = 0.78 if lower_shadow_ratio > 0.7 else 0.70
            risk_level = "medium"
            signals.append(f"形态四·量价齐跌衰竭：跌幅 {day_return:.2%}，放量 {volume_ratio_20:.2f}x，长下影")
            key_findings.append("放量大跌后承接信号受 T+1 制度约束，需预留次日波动缓冲。")
        else:
            signals.append("无明确量价背离或反转形态触发")
            if abs(day_return) >= 0.05 and -1 <= vol_surp <= 1:
                uncertainties.append("价格大幅波动但量能无明显异常，反转信号可信度偏低。")

        if amount is not None and amount < amount_threshold:
            confidence = max(0.2, confidence - 0.1)
        if len(rows) < 60:
            confidence = min(confidence, 0.3 if direction == "neutral" else 0.55)
            needs_human_review = True

        evidence.extend(
            [
                {
                    "source_type": "market_data",
                    "source_name": data_status,
                    "date": latest.get("date", ""),
                    "metric": "VolSurp（异常成交量 Z 分数）",
                    "value": round(vol_surp, 4),
                    "comparison": f"今日成交量 {latest_volume_meta['display']} vs 20日均量 {avg_volume_20_meta['display']}",
                    "note": self._volume_surprise_note(vol_surp),
                },
                {
                    "source_type": "market_data",
                    "source_name": data_status,
                    "date": latest.get("date", ""),
                    "metric": "日涨跌幅 / 20日位置",
                    "value": f"{day_return:.2%}",
                    "comparison": f"20日高点 {high_20:.4f} / 低点 {low_20:.4f}",
                    "note": "价格处于20日新高/新低位置" if is_new_high or is_new_low else "",
                },
                {
                    "source_type": "market_data",
                    "source_name": data_status,
                    "date": latest.get("date", ""),
                    "metric": "影线占振幅",
                    "value": {
                        "upper_shadow_ratio": round(upper_shadow_ratio, 4),
                        "lower_shadow_ratio": round(lower_shadow_ratio, 4),
                    },
                    "comparison": "长影线需满足影线≥实体2倍、影线/振幅≥50%、振幅/昨收≥3%",
                    "note": self._shadow_note(upper_shadow_ratio, lower_shadow_ratio, long_upper_shadow, long_lower_shadow),
                },
            ]
        )

        reasoning = "；".join(signals)
        if uncertainties:
            reasoning += "；不确定性：" + "；".join(uncertainties[:2])
        return {
            "skill_name": "volume_price_reversal",
            "direction": direction,
            "confidence": self._clamp(confidence),
            "reasoning": reasoning,
            "signals": signals,
            "weight": float(self.config.get("volume_price_reversal_weight", 0.35)),
            "meta": {
                "skill_name": "volume_price_reversal",
                "output_version": "0.1-runtime",
                "time_horizon": "short",
                "risk_level": risk_level,
                "key_findings": key_findings,
                "evidence": evidence,
                "metrics": {
                    "day_return": day_return,
                    "latest_volume": volume,
                    "latest_volume_display": latest_volume_meta["display"],
                    "latest_volume_shares": latest_volume_meta["shares"],
                    "avg_volume_20": avg_volume_20,
                    "avg_volume_20_display": avg_volume_20_meta["display"],
                    "avg_volume_20_shares": avg_volume_20_meta["shares"],
                    "volume_unit": latest_volume_meta["unit"],
                    "volume_share_multiplier": latest_volume_meta["share_multiplier"],
                    "volume_ratio_20": volume_ratio_20,
                    "vol_surp": vol_surp,
                    "amount": amount,
                    "avg_amount_20": avg_amount_20,
                    "amount_threshold": amount_threshold,
                },
                "uncertainties": uncertainties,
                "needs_human_review": needs_human_review,
            },
        }

    def _run_company_evolution_analysis(self, stock_code: str) -> Dict[str, Any]:
        """调用 company_evolution_analysis 的运行时适配层。

        该 Skill 的完整形态依赖联网搜索和长报告生成；Agent 的实时技术指标流程中不做
        事实编造，优先接收 config 注入的 company_evolution/company_profile_source 结果；
        未注入时尝试调用 skills/data/cninfo 契约对应的 data_sources.cninfo，用法定公告
        标题/报告元数据提取公司节点、催化和风险，作为技术信号的背景约束。
        """
        payload = self.config.get("company_evolution") or self.config.get("company_profile")
        payload_source = "config:company_evolution" if self.config.get("company_evolution") else "config:company_profile"
        source = self.config.get("company_profile_source")
        if payload is None and source is not None:
            payload = self._load_company_profile(source, stock_code)
            payload_source = "config:company_profile_source"
        if payload is None and self.config.get("use_cninfo_company_data", True):
            payload = self._load_company_profile_from_cninfo(stock_code)
            payload_source = "data_sources.cninfo"

        if not payload:
            return self._neutral_skill_result(
                "company_evolution_analysis",
                "公司发展沿革 Skill 已加载；未取得注入画像或 cninfo 公告数据，故仅作为中性背景约束。",
                weight=float(self.config.get("company_evolution_analysis_weight", 0.10)),
                confidence=0.2,
                meta={
                    "skill_name": "company_evolution_analysis",
                    "requires_web_search_for_full_report": True,
                    "needs_human_review": True,
                    "uncertainties": ["未注入公司节点叙事，且未取得 cninfo 公告数据，避免凭空生成公司发展结论。"],
                },
            )

        direction = str(payload.get("direction") or payload.get("technical_bias") or "neutral")
        if direction not in {"bullish", "bearish", "neutral"}:
            direction = "neutral"
        confidence = self._clamp(float(payload.get("confidence", 0.35) or 0.35))
        nodes = list(payload.get("nodes") or payload.get("key_nodes") or [])
        catalysts = list(payload.get("catalysts") or payload.get("growth_drivers") or [])
        risks = list(payload.get("risks") or payload.get("risk_notes") or [])
        signals = list(payload.get("signals") or [])
        if not signals:
            if catalysts:
                signals.append("公司节点叙事：存在可验证增长催化，作为技术信号背景加分项")
            if risks:
                signals.append("公司节点叙事：存在可验证发展风险，作为技术信号风险约束")
            if not signals:
                signals.append("公司节点叙事：已注入背景资料，但未形成明确方向约束")

        return {
            "skill_name": "company_evolution_analysis",
            "direction": direction,
            "confidence": confidence,
            "reasoning": str(payload.get("reasoning") or "基于注入的公司发展节点事实形成背景约束。"),
            "signals": signals,
            "weight": float(self.config.get("company_evolution_analysis_weight", 0.10)),
            "meta": {
                "skill_name": "company_evolution_analysis",
                "nodes": nodes,
                "catalysts": catalysts,
                "risks": risks,
                "current_position": list(payload.get("current_position") or []),
                "future_outlook": list(payload.get("future_outlook") or []),
                "evidence": list(payload.get("evidence") or []),
                "data_source_meta": dict(payload.get("data_source_meta") or {}),
                "source": str(payload.get("source") or payload_source),
                "requires_web_search_for_full_report": bool(payload.get("requires_web_search_for_full_report", True)),
                "needs_human_review": bool(payload.get("needs_human_review", False)),
                "uncertainties": list(payload.get("uncertainties") or []),
            },
        }

    def _merge_skill_results(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        skill_results: List[Dict[str, Any]],
        data_uncertainties: List[str],
    ) -> Signal:
        """以 traditional_model_fusion/run_models 融合结果为最终 Signal。

        `runner.run_models()` 是专家2组技术指标模型的唯一四模型执行入口，
        TechnicalAgent 不再在 Agent 层重新做二次方向加权，避免与
        `fusion_traditional_models.cli` 的输出口径不一致。其他两个 technical skill
        作为辅助分析写入 meta，不改写最终 direction/confidence/reasoning/signals。
        """
        primary = next((item for item in skill_results if item.get("skill_name") == "traditional_model_fusion"), None)
        if primary is None:
            return self._create_error_signal("缺少 traditional_model_fusion 结果，无法对齐 run_models 输出。", stock_code)

        auxiliary_results = [item for item in skill_results if item is not primary]
        all_uncertainties = list(data_uncertainties)
        for item in skill_results:
            meta_uncertainties = item.get("meta", {}).get("uncertainties", [])
            all_uncertainties.extend(meta_uncertainties)

        primary_meta = dict(primary.get("meta") or {})
        primary_meta.setdefault("uncertainties", [])
        primary_meta["uncertainties"] = self._dedupe_strings(
            list(primary_meta.get("uncertainties") or []) + all_uncertainties
        )
        data_period = self._rows_date_range(rows)
        analysis_reports = self._build_analysis_reports(
            stock_code=stock_code,
            rows=rows,
            data_status=data_status,
            data_period=data_period,
            skill_results=skill_results,
            data_uncertainties=data_uncertainties,
            primary_meta=primary_meta,
        )

        meta = {
            **primary_meta,
            "data_status": data_status,
            "rows_count": len(rows),
            "data_period": data_period,
            "analysis_start_date": data_period.get("start"),
            "analysis_end_date": data_period.get("end"),
            "loaded_skills": self.list_skills(),
            "skill_results": {item.get("skill_name", "unknown_skill"): item for item in skill_results},
            "analysis_reports": analysis_reports,
            "reports": analysis_reports,
            "report_order": [
                "traditional_model_fusion",
                "company_evolution_analysis",
                "volume_price_reversal",
            ],
            "traditional_model_fusion": primary_meta,
            "volume_price_reversal": next((item.get("meta", {}) for item in skill_results if item.get("skill_name") == "volume_price_reversal"), {}),
            "company_evolution_analysis": next((item.get("meta", {}) for item in skill_results if item.get("skill_name") == "company_evolution_analysis"), {}),
            "technical_agent_policy": {
                "primary_skill": "traditional_model_fusion",
                "primary_execution": "fusion_traditional_models.runner.run_models + fuse_signals",
                "final_signal_aligned_with_run_models": True,
                "auxiliary_skills_do_not_override_direction": [item.get("skill_name") for item in auxiliary_results],
            },
            "auxiliary_signals": {
                item.get("skill_name", "unknown_skill"): {
                    "direction": item.get("direction"),
                    "confidence": item.get("confidence"),
                    "reasoning": item.get("reasoning"),
                    "signals": item.get("signals", []),
                }
                for item in auxiliary_results
            },
            "related_skills": [
                "traditional_model_fusion",
                "volume_price_reversal",
                "company_evolution_analysis",
            ],
            "uncertainties": self._dedupe_strings(all_uncertainties),
        }
        return Signal(
            direction=str(primary.get("direction", "neutral")),
            confidence=self._clamp(float(primary.get("confidence", 0.2) or 0.2)),
            reasoning=str(primary.get("reasoning") or "传统技术指标融合完成。"),
            signals=list(primary.get("signals") or []),
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            weight=float(primary.get("weight", self.config.get("weight", 1.0)) or 1.0),
            meta=meta,
        )

    def _build_analysis_reports(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        skill_results: List[Dict[str, Any]],
        data_uncertainties: List[str],
        primary_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按三个 technical Skill 的 SKILL.md 契约组织 Agent 返回报告。"""
        result_by_name = {item.get("skill_name", "unknown_skill"): item for item in skill_results}
        return {
            "traditional_model_fusion": self._build_traditional_model_fusion_analysis_report(
                stock_code=stock_code,
                rows=rows,
                data_status=data_status,
                data_period=data_period,
                primary=result_by_name.get("traditional_model_fusion", {}),
                primary_meta=primary_meta,
                data_uncertainties=data_uncertainties,
            ),
            "company_evolution_analysis": self._build_company_evolution_report(
                stock_code=stock_code,
                data_period=data_period,
                result=result_by_name.get("company_evolution_analysis", {}),
            ),
            "volume_price_reversal": self._build_volume_price_reversal_report(
                stock_code=stock_code,
                rows=rows,
                data_status=data_status,
                data_period=data_period,
                result=result_by_name.get("volume_price_reversal", {}),
            ),
        }

    def _build_traditional_model_fusion_analysis_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        primary: Dict[str, Any],
        primary_meta: Dict[str, Any],
        data_uncertainties: List[str],
    ) -> Dict[str, Any]:
        """按 traditional_model_fusion/SKILL.md 的中文解读模板组织报告。"""
        validation = dict(primary_meta.get("validation_report") or {})
        model_signals = list(primary_meta.get("model_signals") or [])
        test_report = dict(primary_meta.get("traditional_model_fusion_test_report") or primary_meta.get("test_report") or {})
        risk_level = str(primary_meta.get("risk_level") or "medium")
        needs_review = bool(primary_meta.get("needs_human_review", False))
        direction = str(primary.get("direction") or "neutral")
        confidence = self._clamp(float(primary.get("confidence", 0.2) or 0.2))
        threshold = ((validation.get("final_thresholds") or {}).get("threshold"))
        total_vote = validation.get("total_vote")
        model_rows = []
        model_interpretations = []
        for row in model_signals:
            signal = row.get("signal") if isinstance(row, dict) else {}
            signal = signal if isinstance(signal, dict) else {}
            meta = signal.get("meta") if isinstance(signal.get("meta"), dict) else {}
            name = str(row.get("name") or "unknown_model") if isinstance(row, dict) else "unknown_model"
            model_rows.append(
                {
                    "model": name,
                    "model_label": self._traditional_model_label(name),
                    "direction": signal.get("direction", "neutral"),
                    "confidence": signal.get("confidence", 0.0),
                    "risk_level": meta.get("risk_level", "medium"),
                    "needs_human_review": bool(meta.get("needs_human_review", False)),
                    "effective_weight": row.get("effective_weight") if isinstance(row, dict) else None,
                    "vote": row.get("vote") if isinstance(row, dict) else None,
                    "notes": row.get("notes", []) if isinstance(row, dict) else [],
                    "reasoning": signal.get("reasoning", ""),
                }
            )
            model_interpretations.append(
                {
                    "title": self._traditional_model_label(name),
                    "model": name,
                    "direction": signal.get("direction", "neutral"),
                    "summary": signal.get("reasoning", "未返回子模型解释。"),
                    "key_findings": list(meta.get("key_findings") or []),
                    "uncertainties": list(meta.get("uncertainties") or []),
                    "evidence": list(meta.get("evidence") or []),
                }
            )

        conflicts = list(validation.get("conflicts") or [])
        gates = list(validation.get("gates_triggered") or [])
        if direction == "neutral":
            neutral_note = "本次融合结果未跨过做多/做空阈值，或因门控/风险折扣保持保守，并不等同于明确看空。"
        else:
            neutral_note = f"本次融合结果为 {direction}，表示技术面方向倾向已跨过阈值，但仍不是交易指令。"

        sections = [
            {
                "title": "1. 一句话结论",
                "content": [
                    f"融合总信号：{direction}",
                    f"置信度：{confidence:.2f}",
                    f"风险等级：{risk_level}",
                    f"是否需要人工复核：{needs_review}",
                    str(primary.get("reasoning") or "传统技术指标融合完成。"),
                ],
            },
            {"title": "2. 这不是简单看多或看空", "content": [neutral_note]},
            {
                "title": "3. 融合投票是怎么来的",
                "content": [f"total_vote={self._format_optional_number(total_vote, 4)}，threshold={self._format_optional_number(threshold, 2)}，最终方向={direction}。"],
                "table": model_rows,
            },
            {"title": "4. 四个子模型分别在说什么", "items": model_interpretations},
            {
                "title": "5. 风险和人工复核点",
                "content": self._dedupe_strings(
                    list(primary_meta.get("risk_notes") or [])
                    + list(primary_meta.get("uncertainties") or [])
                    + list(data_uncertainties or [])
                )
                or ["未发现额外风险说明；仍需结合基本面、消息面和更长周期复核。"],
            },
            {
                "title": "6. 门控与冲突",
                "content": [
                    f"门控触发数量：{len(gates)}。",
                    f"方向冲突数量：{len(conflicts)}。",
                    "没有直接多空冲突时，也需关注未确认指标、有效权重调整和风险折扣。",
                ],
                "gates_triggered": gates,
                "conflicts": conflicts,
            },
            {
                "title": "7. 对结果的使用建议",
                "content": ["该结果适合作为技术面过滤器和复核线索，不是交易指令；建议结合更长周期、基本面、消息面和人工复核。"],
            },
            {
                "title": "8. 后续改进建议",
                "content": [
                    "数据：补充更稳定的复权口径、成交额、换手率和行业横截面数据。",
                    "模型：补充强趋势/弱趋势市场状态识别。",
                    "融合规则：持续复盘门控阈值和风险折扣。",
                    "回测验证：按行业、波动率和市值分层评估命中率。",
                ],
            },
        ]
        return {
            "report_type": "traditional_model_fusion_analysis_report",
            "skill_name": "traditional_model_fusion",
            "skill_contract": "skills/technical/traditional_model_fusion/SKILL.md",
            "title": f"{stock_code} 传统模型融合结果解读",
            "data_status": data_status,
            "rows_count": len(rows),
            "data_period": data_period,
            "summary": {
                "direction": direction,
                "confidence": confidence,
                "risk_level": risk_level,
                "needs_human_review": needs_review,
                "total_vote": total_vote,
                "threshold": threshold,
            },
            "sections": sections,
            "json_result": test_report.get("raw_fusion_result") or {
                "fused_signal": test_report.get("final_signal") or {},
                "model_signals": model_signals,
                "validation_report": validation,
            },
            "test_report": test_report,
        }

    def _build_company_evolution_report(self, *, stock_code: str, data_period: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """按 company_evolution_analysis/SKILL.md 的节点叙事结构组织报告。"""
        meta = dict(result.get("meta") or {})
        nodes = list(meta.get("nodes") or [])
        catalysts = list(meta.get("catalysts") or [])
        risks = list(meta.get("risks") or [])
        data_source_meta = dict(meta.get("data_source_meta") or {})
        requires_web_search = bool(meta.get("requires_web_search_for_full_report", True))
        if data_source_meta.get("provider") == "cninfo" and data_source_meta.get("status") == "success":
            status = "ready_from_cninfo_disclosures"
        elif data_source_meta.get("provider") == "cninfo":
            status = "cninfo_unavailable"
        elif nodes or catalysts or risks:
            status = "ready_from_injected_profile"
        else:
            status = "requires_web_search_or_injected_profile"
        if data_source_meta.get("provider") == "cninfo":
            integrity_note = str(result.get("reasoning") or "基于 cninfo 法定披露数据形成公司发展路径背景约束。")
        elif requires_web_search and status != "ready_from_injected_profile":
            integrity_note = "未注入联网检索后的公司节点事实；为避免编造，本报告只返回结构化占位和复核要求。"
        else:
            integrity_note = str(result.get("reasoning") or "基于注入的公司节点事实形成背景约束。")

        return {
            "report_type": "company_evolution_analysis_report",
            "skill_name": "company_evolution_analysis",
            "skill_contract": "skills/technical/company_evolution_analysis/SKILL.md",
            "title": f"{stock_code} 公司发展路径节点叙事分析",
            "status": status,
            "data_period": data_period,
            "summary": {
                "direction": result.get("direction", "neutral"),
                "confidence": result.get("confidence", 0.2),
                "requires_web_search_for_full_report": requires_web_search,
                "needs_human_review": bool(meta.get("needs_human_review", True)),
                "integrity_note": integrity_note,
                "source": meta.get("source"),
                "data_source_meta": data_source_meta,
            },
            "sections": [
                {
                    "title": "公司版图演进总览",
                    "content": self._dedupe_strings(
                        [integrity_note]
                        + ([f"cninfo 公告窗口：{data_source_meta.get('since')} 至 {data_source_meta.get('until')}，去重公告 {data_source_meta.get('announcements_total')} 条。"] if data_source_meta.get("provider") == "cninfo" else [])
                    ),
                },
                {
                    "title": "关键节点叙事",
                    "items": nodes,
                    "empty_state": "cninfo 公告未识别出并购、融资、控制权变更、资产交易等关键节点；完整发展史仍需结合招股书、年报正文和外部检索。",
                },
                {
                    "title": "当前格局陈述",
                    "content": list(meta.get("current_position") or []),
                    "empty_state": "未注入最新财报、市场份额、客户结构、竞争对手和现金流等事实。",
                },
                {
                    "title": "当前增长点的事实陈述",
                    "items": catalysts,
                    "empty_state": "未注入在建产能、研发转订单、新客户、新业务或产业变量契合度等可追溯事实。",
                },
                {
                    "title": "未来几年趋势的可能走向",
                    "content": list(meta.get("future_outlook") or []),
                    "empty_state": "需要基于真实节点、订单和产能事实分短期/中期/中长期推演。",
                },
                {
                    "title": "风险与挑战",
                    "items": risks,
                    "empty_state": "未注入技术路线、竞争、客户集中、地缘政治、业绩兑现或估值消化风险。",
                },
                {
                    "title": "cninfo 事实锚与复核要求",
                    "items": list(meta.get("evidence") or []),
                    "empty_state": "暂无 cninfo 事实锚。",
                },
            ],
            "raw_signal": result,
            "data_source_meta": data_source_meta,
        }

    def _build_volume_price_reversal_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按 volume_price_reversal/SKILL.md 的标准 JSON + 摘要结构组织报告。"""
        meta = dict(result.get("meta") or {})
        direction = str(result.get("direction") or "neutral")
        confidence = self._clamp(float(result.get("confidence", 0.2) or 0.2))
        risk_level = str(meta.get("risk_level") or "medium")
        latest = rows[-1] if rows else {}
        metrics = dict(meta.get("metrics") or {})
        trigger_pattern = self._extract_trigger_pattern(list(result.get("signals") or []))
        standard_json = {
            "direction": direction,
            "confidence": confidence,
            "reasoning": result.get("reasoning", ""),
            "signals": list(result.get("signals") or []),
            "source": "volume-price-reversal",
            "signal_type": "technical",
            "stock_code": stock_code,
            "weight": float(result.get("weight", 1.0) or 1.0),
            "meta": {
                "output_version": meta.get("output_version", "0.1-runtime"),
                "skill_name": "volume-price-reversal",
                "owner_group": "专家2组（指标）",
                "target": stock_code,
                "period": data_status,
                "time_horizon": meta.get("time_horizon", "short"),
                "risk_level": risk_level,
                "key_findings": list(meta.get("key_findings") or []),
                "evidence": list(meta.get("evidence") or []),
                "risk_notes": list(meta.get("risk_notes") or []),
                "uncertainties": list(meta.get("uncertainties") or []),
                "needs_human_review": bool(meta.get("needs_human_review", False)),
            },
        }
        summary = {
            "target": stock_code,
            "direction": direction,
            "confidence": confidence,
            "risk_level": risk_level,
            "trigger_pattern": trigger_pattern,
            "signal_brief": self._short_text(str(result.get("reasoning") or ""), 80),
        }
        return {
            "report_type": "volume_price_reversal_report",
            "skill_name": "volume_price_reversal",
            "skill_contract": "skills/technical/volume_price_reversal/SKILL.md",
            "title": f"{stock_code} 高盛量价背离与反转信号识别",
            "data_status": data_status,
            "rows_count": len(rows),
            "data_period": data_period,
            "latest_bar": latest,
            "summary_table": [summary],
            "standard_json": standard_json,
            "markdown_summary": {
                "headline": f"{stock_code} — `{direction}` / {confidence:.2f} / {risk_level}",
                "overview": (list(result.get("signals") or [])[:1] or [result.get("reasoning") or "无形态触发。"])[0],
                "metrics": {
                    "day_return": metrics.get("day_return"),
                    "latest_volume": metrics.get("latest_volume"),
                    "latest_volume_display": metrics.get("latest_volume_display"),
                    "latest_volume_shares": metrics.get("latest_volume_shares"),
                    "avg_volume_20": metrics.get("avg_volume_20"),
                    "avg_volume_20_display": metrics.get("avg_volume_20_display"),
                    "avg_volume_20_shares": metrics.get("avg_volume_20_shares"),
                    "volume_unit": metrics.get("volume_unit"),
                    "volume_share_multiplier": metrics.get("volume_share_multiplier"),
                    "volume_ratio_20": metrics.get("volume_ratio_20"),
                    "vol_surp": metrics.get("vol_surp"),
                    "amount": metrics.get("amount"),
                    "avg_amount_20": metrics.get("avg_amount_20"),
                    "amount_threshold": metrics.get("amount_threshold"),
                },
                "evidence": list(meta.get("evidence") or []),
                "execution_constraints": list(meta.get("key_findings") or []) + list(meta.get("uncertainties") or []),
            },
            "raw_signal": result,
        }

    def _load_ohlcv_rows(self, stock_code: str) -> Tuple[List[Dict[str, Any]], str, List[str]]:
        """加载 OHLCV 行情，返回 rows、数据状态和不确定性说明。"""
        uncertainties: List[str] = []

        injected_rows = self.config.get("ohlcv_rows")
        if injected_rows:
            return self._normalize_ohlcv_rows(injected_rows), "config:ohlcv_rows", uncertainties

        data_source = self.config.get("ohlcv_data_source")
        if data_source is not None:
            rows = self._load_from_data_source(data_source, stock_code)
            if rows:
                return self._normalize_ohlcv_rows(rows), "config:ohlcv_data_source", uncertainties
            uncertainties.append("ohlcv_data_source 未返回有效 K 线数据。")

        csv_path = self.config.get("csv_path")
        if csv_path and load_rows_from_csv:
            rows, csv_uncertainties = load_rows_from_csv(str(csv_path))
            uncertainties.extend(csv_uncertainties)
            if rows:
                return self._normalize_ohlcv_rows(rows), f"csv:{csv_path}", uncertainties

        if self.config.get("use_live_data") and load_rows_from_code:
            start, end = self._default_date_range()
            rows, live_uncertainties = load_rows_from_code(
                stock_code,
                self.config.get("start", start),
                self.config.get("end", end),
                freq=self.config.get("freq", "D"),
                adjust=self.config.get("adjust", "qfq"),
            )
            uncertainties.extend(live_uncertainties)
            if rows:
                source_name = self._extract_market_source(live_uncertainties, f"market_data:{stock_code}")
                return self._normalize_ohlcv_rows(rows), source_name, uncertainties

        uncertainties.append("未配置实时行情或外部数据源，使用离线 OHLCV 样本完成传统指标融合自检。")
        return self._build_offline_rows(), "offline:synthetic_ohlcv", uncertainties

    def _load_from_data_source(self, data_source: Any, stock_code: str) -> List[Dict[str, Any]]:
        """兼容不同注入数据源形态。"""
        if callable(data_source):
            data = data_source(stock_code)
        elif hasattr(data_source, "get_ohlcv"):
            data = data_source.get_ohlcv(stock_code)
        elif hasattr(data_source, "fetch_ohlcv"):
            data = data_source.fetch_ohlcv(stock_code)
        else:
            return []

        if isinstance(data, dict):
            return list(data.get("rows") or data.get("kline") or data.get("data") or [])
        return list(data or [])

    def _load_company_profile(self, source: Any, stock_code: str) -> Dict[str, Any]:
        """兼容注入的公司发展沿革数据源。"""
        if callable(source):
            data = source(stock_code)
        elif isinstance(source, dict):
            data = source.get(stock_code) or source.get("default") or source
        elif hasattr(source, "get_company_evolution"):
            data = source.get_company_evolution(stock_code)
        elif hasattr(source, "get_company_profile"):
            data = source.get_company_profile(stock_code)
        else:
            data = {}
        return dict(data or {}) if isinstance(data, dict) else {}

    def _load_company_profile_from_cninfo(self, stock_code: str) -> Dict[str, Any]:
        """基于 cninfo 法定披露公告构造公司发展路径分析输入。"""
        source = self.config.get("cninfo_data_source")
        if source is None:
            if CninfoDataSource is None:
                return {
                    "source": "data_sources.cninfo",
                    "direction": "neutral",
                    "confidence": 0.2,
                    "reasoning": "cninfo 数据源模块不可用，无法基于法定公告生成公司发展路径分析。",
                    "signals": ["公司节点叙事：cninfo 数据源不可用，保持中性背景约束"],
                    "uncertainties": ["data_sources.cninfo 导入失败；请检查 cninfo 数据源依赖。"],
                    "requires_web_search_for_full_report": True,
                    "needs_human_review": True,
                    "data_source_meta": {"provider": "cninfo", "status": "error", "error": "data_sources.cninfo import failed"},
                }
            source = CninfoDataSource()

        until = str(self.config.get("cninfo_until") or date.today().isoformat())
        if self.config.get("cninfo_since"):
            since = str(self.config.get("cninfo_since"))
        else:
            lookback_days = int(self.config.get("cninfo_lookback_days", 730) or 730)
            since = (date.today() - timedelta(days=lookback_days)).isoformat()

        announcements_result = self._call_cninfo_announcements(source, stock_code, since, until)
        announcements = []
        if announcements_result.get("status") == "success":
            announcements = self._dedupe_cninfo_announcements(announcements_result.get("announcements") or [])

        periodic_reports: List[Dict[str, Any]] = []
        if self.config.get("cninfo_fetch_periodic_report", False):
            periodic_reports = self._load_cninfo_periodic_reports(source, stock_code)

        payload = self._build_company_profile_from_cninfo_announcements(
            stock_code=stock_code,
            since=since,
            until=until,
            announcements=announcements,
            periodic_reports=periodic_reports,
            announcements_result=announcements_result,
        )
        return payload

    def _call_cninfo_announcements(self, source: Any, stock_code: str, since: str, until: str) -> Dict[str, Any]:
        """兼容真实 CninfoDataSource 和测试 fake source 的公告列表调用。"""
        try:
            if hasattr(source, "get_announcements"):
                return dict(source.get_announcements(stock_code, since=since, until=until, download=False) or {})
            if callable(source):
                data = source(stock_code, since=since, until=until)
                return dict(data or {}) if isinstance(data, dict) else {"status": "success", "announcements": list(data or [])}
        except Exception as exc:
            return {"status": "error", "stock_code": stock_code, "error": f"cninfo 公告调用失败：{type(exc).__name__}: {exc}"}
        return {"status": "error", "stock_code": stock_code, "error": "cninfo 数据源不支持 get_announcements 接口。"}

    def _load_cninfo_periodic_reports(self, source: Any, stock_code: str) -> List[Dict[str, Any]]:
        """可选拉取最近一期定期报告元数据；默认关闭，避免实时调试链路过慢。"""
        if not hasattr(source, "get_periodic_report"):
            return []
        today = date.today()
        candidates: List[Tuple[int, str]] = []
        if today.month >= 5:
            candidates.append((today.year, "q1"))
            candidates.append((today.year - 1, "annual"))
        else:
            candidates.append((today.year - 1, "annual"))
            candidates.append((today.year - 1, "q3"))

        reports: List[Dict[str, Any]] = []
        for year, kind in candidates[: int(self.config.get("cninfo_periodic_report_limit", 2) or 2)]:
            try:
                result = source.get_periodic_report(stock_code, year=year, kind=kind)
            except Exception as exc:
                reports.append({"status": "error", "year": year, "kind": kind, "error": str(exc)})
                continue
            report = dict((result or {}).get("report") or {}) if isinstance(result, dict) else {}
            if report:
                report["year"] = year
                report["kind"] = kind
                reports.append(report)
        return reports

    def _build_company_profile_from_cninfo_announcements(
        self,
        *,
        stock_code: str,
        since: str,
        until: str,
        announcements: List[Dict[str, Any]],
        periodic_reports: List[Dict[str, Any]],
        announcements_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if announcements_result.get("status") != "success":
            error = str(announcements_result.get("error") or "unknown error")
            return {
                "source": "data_sources.cninfo",
                "direction": "neutral",
                "confidence": 0.2,
                "reasoning": f"未能从 cninfo 获取公司公告：{error}",
                "signals": ["公司节点叙事：cninfo 公告获取失败，保持中性背景约束"],
                "uncertainties": [f"cninfo 公告获取失败：{error}"],
                "requires_web_search_for_full_report": True,
                "needs_human_review": True,
                "data_source_meta": {
                    "provider": "cninfo",
                    "status": announcements_result.get("status"),
                    "since": since,
                    "until": until,
                    "error": error,
                },
            }

        classified = [self._classify_cninfo_announcement(item) for item in announcements]
        nodes = [item for item in classified if item.get("node_type") in {"capital_action", "strategy_change", "major_transaction", "governance_change"}]
        catalysts = [item for item in classified if item.get("node_type") in {"growth_catalyst", "positive_performance", "shareholder_return"}]
        risks = [item for item in classified if item.get("node_type") == "risk_event"]
        current_position = [item for item in classified if item.get("node_type") == "periodic_report"]

        nodes = nodes[: int(self.config.get("cninfo_company_nodes_limit", 10) or 10)]
        catalysts = catalysts[: int(self.config.get("cninfo_company_catalysts_limit", 8) or 8)]
        risks = risks[: int(self.config.get("cninfo_company_risks_limit", 8) or 8)]
        current_position = current_position[:6]

        for report in periodic_reports:
            title = str(report.get("title") or "定期报告")
            current_position.append(
                {
                    "date": self._format_cninfo_date(report.get("ann_date")),
                    "title": title,
                    "node_type": "periodic_report",
                    "interpretation": "已获取 cninfo 定期报告元数据，可作为后续深读管理层讨论、财务指标和订单线索的入口。",
                    "source": "cninfo_periodic_report",
                    "evidence": title,
                    "md_path": report.get("md_path"),
                    "pdf_url": report.get("pdf_url"),
                }
            )

        evidence = [
            {"date": item.get("date"), "title": item.get("title"), "node_type": item.get("node_type"), "source": item.get("source")}
            for item in (nodes + catalysts + risks + current_position)[:20]
        ]
        total_direction_score = len(catalysts) - len(risks)
        if total_direction_score >= 2:
            direction = "bullish"
        elif total_direction_score <= -2:
            direction = "bearish"
        else:
            direction = "neutral"
        confidence = self._clamp(0.25 + min(len(evidence), 12) * 0.02)

        if announcements:
            reasoning = (
                f"基于 cninfo 法定披露公告（{since} 至 {until}，去重后 {len(announcements)} 条）抽取公司发展节点；"
                f"识别关键节点 {len(nodes)} 条、增长/回报线索 {len(catalysts)} 条、风险事件 {len(risks)} 条。"
            )
        else:
            reasoning = f"cninfo 在 {since} 至 {until} 窗口未返回公告，暂无法形成公司发展路径节点叙事。"

        signals = []
        if catalysts:
            signals.append(f"公司节点叙事：cninfo 披露中存在 {len(catalysts)} 条增长/股东回报线索")
        if risks:
            signals.append(f"公司节点叙事：cninfo 披露中存在 {len(risks)} 条风险事件，需约束技术信号")
        if nodes:
            signals.append(f"公司节点叙事：识别 {len(nodes)} 条资本运作/治理/战略节点")
        if not signals:
            signals.append("公司节点叙事：cninfo 公告未识别出明确方向约束")

        return {
            "source": "data_sources.cninfo",
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "signals": signals,
            "nodes": nodes,
            "catalysts": catalysts,
            "risks": risks,
            "current_position": [self._cninfo_item_to_sentence(item) for item in current_position[:8]],
            "future_outlook": self._build_cninfo_future_outlook(nodes, catalysts, risks),
            "evidence": evidence,
            "requires_web_search_for_full_report": False,
            "needs_human_review": True,
            "uncertainties": self._dedupe_strings(
                [
                    "公司发展路径分析基于 cninfo 公告标题和可选定期报告元数据，未默认下载 PDF 全文；交易金额、客户、产能和财务科目仍需深读公告/年报正文验证。",
                    "公告标题可识别方向性节点，但不能替代完整的公司发展史、行业格局和财务环比分析。",
                ]
                + ([] if announcements else ["cninfo 公告列表为空，当前报告只保留结构化空状态。"])
            ),
            "data_source_meta": {
                "provider": "cninfo",
                "status": "success",
                "since": since,
                "until": until,
                "announcements_total": len(announcements),
                "periodic_reports_total": len(periodic_reports),
                "download_reports": bool(self.config.get("cninfo_fetch_periodic_report", False)),
            },
        }

    def _classify_cninfo_announcement(self, item: Dict[str, Any]) -> Dict[str, Any]:
        title = str(item.get("title") or item.get("announcementTitle") or "")
        compact_title = title.replace(" ", "")
        date_text = self._format_cninfo_date(item.get("ann_date") or item.get("announcementTime"))
        node_type = "other_disclosure"
        interpretation = "法定披露公告，可作为公司发展路径分析的事实锚。"

        if self._contains_any(compact_title, ["年度报告", "半年度报告", "季度报告", "一季报", "三季报"]):
            node_type = "periodic_report"
            interpretation = "定期报告披露，是验证主营业务、财务质量、订单和战略展望的核心入口。"
        if self._contains_any(compact_title, ["重大资产重组", "购买资产", "出售资产", "收购", "并购", "吸收合并", "对外投资", "投资建设", "设立子公司"]):
            node_type = "major_transaction"
            interpretation = "资本开支/并购/资产交易类公告，可能改变公司能力边界或版图结构。"
        if self._contains_any(compact_title, ["非公开发行", "定向增发", "向特定对象发行", "可转换公司债券", "配股", "上市", "募集资金"]):
            node_type = "capital_action"
            interpretation = "融资或资本市场动作，可能影响资本结构、扩张节奏和战略资源。"
        if self._contains_any(compact_title, ["控制权", "实际控制人", "控股股东", "权益变动", "董事会换届", "高级管理人员", "总经理", "董事长"]):
            node_type = "governance_change"
            interpretation = "控制权/治理结构变化，可能改变公司的战略定力、资源导入和风险偏好。"
        if self._contains_any(compact_title, ["战略合作", "重大合同", "中标", "项目合同", "订单", "产能", "投产", "扩产", "新产品", "获得认证"]):
            node_type = "growth_catalyst"
            interpretation = "订单、产能、产品或战略合作线索，可能构成当前增长点。"
        if self._contains_any(compact_title, ["业绩预增", "扭亏", "利润分配", "现金分红", "股份回购", "回购股份"]):
            node_type = "positive_performance" if not self._contains_any(compact_title, ["分红", "回购"]) else "shareholder_return"
            interpretation = "业绩改善或股东回报线索，可作为基本面/市场预期的正向事实锚。"
        if self._contains_any(compact_title, ["减持", "立案", "处罚", "监管函", "问询函", "诉讼", "仲裁", "冻结", "质押", "终止", "延期", "亏损", "预亏", "业绩下降", "业绩预减", "退市风险"]):
            node_type = "risk_event"
            interpretation = "风险类公告，需要作为技术信号的背景约束和人工复核重点。"

        return {
            "date": date_text,
            "title": title,
            "node_type": node_type,
            "interpretation": interpretation,
            "source": "cninfo_announcement",
            "ann_id": item.get("ann_id") or item.get("announcementId"),
            "evidence": title,
        }

    def _dedupe_cninfo_announcements(self, announcements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        rows: List[Dict[str, Any]] = []
        for item in announcements:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("announcementTitle") or "")
            ann_date = str(item.get("ann_date") or item.get("announcementTime") or "")
            key = (ann_date[:8], title)
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)
        rows.sort(key=lambda row: str(row.get("ann_date") or row.get("announcementTime") or ""), reverse=True)
        return rows

    def _build_cninfo_future_outlook(self, nodes: List[Dict[str, Any]], catalysts: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> List[str]:
        outlook = []
        if catalysts:
            outlook.append("短期看，需跟踪公告中的订单/产能/新产品线索是否继续在后续定期报告中兑现为收入、合同负债和现金流。")
        if nodes:
            outlook.append("中期看，资本运作、治理或资产交易节点是否形成真实协同，是判断公司版图扩张质量的关键。")
        if risks:
            outlook.append("风险侧，减持、问询、诉讼、处罚、项目终止或业绩下修类公告需要优先人工复核。")
        return outlook or ["当前 cninfo 公告未给出明确新增节点，未来走向需等待更多法定披露和财务正文验证。"]

    def _cninfo_item_to_sentence(self, item: Dict[str, Any]) -> str:
        date_text = item.get("date") or "日期未知"
        title = item.get("title") or "公告标题未知"
        interpretation = item.get("interpretation") or "法定披露事实锚。"
        return f"{date_text}：{title}。{interpretation}"

    def _format_cninfo_date(self, value: Any) -> str:
        text = str(value or "").strip()
        if len(text) >= 8 and text[:8].isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return text or ""

    def _contains_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _extract_market_source(self, uncertainties: List[str], default: str) -> str:
        for item in uncertainties:
            text = str(item)
            if text.startswith("行情来源："):
                return text.replace("行情来源：", "", 1)
        return default

    def _normalize_ohlcv_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把上游字段统一为 fusion_traditional_models 需要的 OHLCV 格式。"""
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            close = self._to_float(row.get("close"))
            high = self._to_float(row.get("high"))
            low = self._to_float(row.get("low"))
            volume = self._to_float(row.get("volume"))
            if close is None or high is None or low is None or volume is None:
                continue
            open_value = self._to_float(row.get("open"))
            normalized_row = {
                "date": str(row.get("date") or row.get("trade_date") or ""),
                "open": close if open_value is None else open_value,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for optional_key in ("amount", "turnover", "money", "turnover_rate", "volume_raw"):
                optional_value = self._to_float(row.get(optional_key))
                if optional_value is not None:
                    normalized_row[optional_key] = optional_value
            for optional_key in ("volume_unit", "volume_raw_unit"):
                if row.get(optional_key):
                    normalized_row[optional_key] = str(row.get(optional_key))
            normalized.append(normalized_row)
        return normalized

    def _build_offline_rows(self, periods: int = 120) -> List[Dict[str, Any]]:
        """构造确定性离线行情样本，避免无网环境下 Agent 退化为未实现。"""
        start = date.today() - timedelta(days=periods * 2)
        rows: List[Dict[str, Any]] = []
        previous_close = 10.0
        for idx in range(periods):
            trade_date = start + timedelta(days=idx)
            trend = idx * 0.035
            wave = math.sin(idx / 6.0) * 0.25
            close = 10.0 + trend + wave
            open_value = previous_close + math.sin(idx / 5.0) * 0.05
            high = max(open_value, close) + 0.18 + abs(math.sin(idx / 7.0)) * 0.08
            low = min(open_value, close) - 0.18 - abs(math.cos(idx / 8.0)) * 0.06
            volume = 1_000_000 + idx * 8_000 + int((math.sin(idx / 4.0) + 1.2) * 120_000)
            rows.append(
                {
                    "date": trade_date.isoformat(),
                    "open": round(open_value, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": float(volume),
                }
            )
            previous_close = close
        return rows

    def _default_date_range(self) -> Tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=240)
        return start.isoformat(), end.isoformat()

    def _neutral_skill_result(
        self,
        skill_name: str,
        reasoning: str,
        weight: float,
        confidence: float = 0.25,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "skill_name": skill_name,
            "direction": "neutral",
            "confidence": self._clamp(confidence),
            "reasoning": reasoning,
            "signals": [reasoning],
            "weight": weight,
            "meta": {"skill_name": skill_name, **(meta or {})},
        }

    def _stddev(self, values: List[float]) -> float:
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            return 0.0
        mean = sum(clean) / len(clean)
        variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1)
        return math.sqrt(max(variance, 0.0))

    def _latest_amount(self, row: Dict[str, Any]) -> Optional[float]:
        amount = self._to_float(row.get("amount") or row.get("turnover") or row.get("money"))
        if amount is not None:
            return amount
        close = self._to_float(row.get("close"))
        volume = self._to_float(row.get("volume"))
        if close is None or volume is None:
            return None
        volume_amount_multiplier = float(self.config.get("volume_amount_multiplier", 100.0))
        return close * volume * volume_amount_multiplier

    def _average_amount(self, rows: List[Dict[str, Any]]) -> Optional[float]:
        amounts = [self._latest_amount(row) for row in rows]
        clean = [amount for amount in amounts if amount is not None]
        if not clean:
            return None
        return sum(clean) / len(clean)

    def _amount_threshold(self, stock_code: str) -> float:
        """按 A 股主要板块给出成交额过滤阈值，单位与 amount 保持一致（默认人民币元）。"""
        code = (stock_code or "").strip()
        if code.startswith(("688", "300")):
            return 50_000_000.0
        if code.startswith(("83", "87", "92")):
            return 20_000_000.0
        return 100_000_000.0

    def _volume_surprise_note(self, vol_surp: float) -> str:
        if vol_surp > 3:
            return "巨量：极端放量，量能远超正常水平，方向需结合 K 线形态判断。"
        if vol_surp > 2:
            return "爆量：今日成交量显著高于均量，配合大涨/大跌时反转概率上升。"
        if vol_surp > 1:
            return "温和放量：成交量适度增加，多空换手活跃度提升。"
        if vol_surp < -1.5:
            return "地量：极端缩量，市场惜售/惜买达到极致。"
        if vol_surp < -1:
            return "缩量：成交量明显萎缩，配合创新高/新低时触发顶/底背离观察。"
        return ""

    def _shadow_note(
        self,
        upper_shadow_ratio: float,
        lower_shadow_ratio: float,
        long_upper_shadow: bool,
        long_lower_shadow: bool,
    ) -> str:
        if long_upper_shadow:
            label = "极端长上影线" if upper_shadow_ratio > 0.7 else "标准长上影线"
            return f"{label}：全天波动中较大比例被抛压打回，构成潜在顶部反转信号。"
        if long_lower_shadow:
            label = "极端长下影线" if lower_shadow_ratio > 0.7 else "标准长下影线"
            return f"{label}：全天波动中较大比例被买盘拉回，构成潜在底部承接信号。"
        return ""

    def _clamp(self, value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        if math.isnan(value) or math.isinf(value):
            return lower
        return max(lower, min(upper, value))

    def _dedupe_strings(self, values: List[str]) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    def _traditional_model_label(self, name: str) -> str:
        labels = {
            "volume_price_momentum_analysis": "量价模型",
            "advanced_trend_tracking_system": "趋势模型",
            "oscillator_check": "震荡模型",
            "trend_application_dulling_divergence": "钝化/背离模型",
        }
        return labels.get(name, name)

    def _format_optional_number(self, value: Any, digits: int = 2) -> str:
        number = self._to_float(value)
        if number is None:
            return "—"
        return f"{number:.{digits}f}"

    def _volume_display_meta(self, volume: float, *, allow_decimal: bool = False) -> Dict[str, Any]:
        """统一成交量展示口径，避免 debug_ui 中“手/股”混淆。"""
        share_multiplier = float(self.config.get("volume_amount_multiplier", 100.0))
        configured_unit = str(self.config.get("volume_unit", "")).strip()
        if configured_unit:
            unit = configured_unit
        elif abs(share_multiplier - 100.0) < 1e-9:
            unit = "手"
        elif abs(share_multiplier - 1.0) < 1e-9:
            unit = "股"
        else:
            unit = f"原始单位×{share_multiplier:g}股"

        shares = volume * share_multiplier
        if unit == "手":
            hand_display = f"{volume:,.2f}" if allow_decimal and abs(volume - round(volume)) >= 1e-9 else f"{volume:,.0f}"
            display = f"{hand_display}手（{shares:,.0f}股）"
        elif unit == "股":
            display = f"{volume:,.0f}股"
        else:
            display = f"{volume:,.0f}{unit}（折合{shares:,.0f}股）"
        return {
            "raw": volume,
            "unit": unit,
            "share_multiplier": share_multiplier,
            "shares": shares,
            "display": display,
        }

    def _rows_date_range(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """返回实际参与分析的行情样本起止时间，便于校验数据与模型结果。"""
        if not rows:
            return {"start": "", "end": "", "rows_count": 0}
        start = str((rows[0] or {}).get("date") or (rows[0] or {}).get("trade_date") or "")[:10]
        end = str((rows[-1] or {}).get("date") or (rows[-1] or {}).get("trade_date") or "")[:10]
        return {"start": start, "end": end, "rows_count": len(rows)}

    def _extract_trigger_pattern(self, signals: List[str]) -> str:
        if not signals:
            return "无形态触发"
        first = str(signals[0])
        patterns = [
            "形态一·顶背离",
            "形态二·底背离",
            "形态三·量价齐升乏力",
            "形态四·量价齐跌衰竭",
            "十字星犹豫",
        ]
        for pattern in patterns:
            if pattern in first:
                return pattern
        if "无明确量价背离" in first or "无形态" in first:
            return "无形态触发"
        return first.split("：", 1)[0][:24]

    def _short_text(self, text: str, limit: int = 80) -> str:
        clean = " ".join(str(text or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 1)] + "…"

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _create_error_signal(self, error_message: str, stock_code: str) -> Signal:
        return neutral_signal(
            confidence=0.1,
            reasoning=f"技术指标分析执行失败: {error_message}",
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            meta={
                "error": error_message,
                "needs_human_review": True,
                "loaded_skills": self.list_skills(),
            },
        )
