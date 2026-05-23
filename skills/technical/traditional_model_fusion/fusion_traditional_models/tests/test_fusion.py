import unittest

from fusion_traditional_models.fusion import fuse_signals


def _signal(direction: str, confidence: float, *, risk_level: str = "low", needs_review: bool = False):
    return {
        "direction": direction,
        "confidence": float(confidence),
        "reasoning": "",
        "signals": [],
        "source": "x",
        "signal_type": "technical",
        "stock_code": "000001",
        "weight": 1.0,
        "meta": {
            "risk_level": risk_level,
            "needs_human_review": needs_review,
            "uncertainties": [],
            "sub_signals": {},
            "target": "000001",
            "period": "2026-01-01 至 2026-05-01",
        },
    }


class TestFusionLogic(unittest.TestCase):
    def test_all_bullish_outputs_bullish(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("bullish", 0.85),
            "volume_price_momentum_analysis": _signal("bullish", 0.85),
            "oscillator_check": _signal("bullish", 0.85),
            "trend_application_dulling_divergence": _signal("bullish", 0.65),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["direction"], "bullish")

    def test_adx_gate_downweights_trend(self):
        trend = _signal("neutral", 0.2)
        trend["reasoning"] = "ADX<20，判定为震荡环境，趋势模块输出 neutral（门控）。"
        trend["meta"]["sub_signals"] = {"adx14": {"gate": "ranging"}}
        model_signals = {
            "advanced_trend_tracking_system": trend,
            "volume_price_momentum_analysis": _signal("bullish", 0.9),
            "oscillator_check": _signal("bullish", 0.7),
            "trend_application_dulling_divergence": _signal("neutral", 0.4, risk_level="medium", needs_review=True),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertIn("gates_triggered", out["validation_report"])
        gates = out["validation_report"]["gates_triggered"]
        self.assertTrue(any(g.get("gate") == "adx_ranging_downweight_trend" for g in gates))

    def test_conflict_reported_and_neutral_when_vote_small(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("bullish", 0.9),
            "volume_price_momentum_analysis": _signal("bullish", 0.9),
            "oscillator_check": _signal("bearish", 0.9),
            "trend_application_dulling_divergence": _signal("neutral", 0.4),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["direction"], "neutral")
        self.assertGreaterEqual(len(out["validation_report"]["conflicts"]), 1)

    def test_high_risk_propagates_to_fused(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("neutral", 0.3, risk_level="medium", needs_review=True),
            "volume_price_momentum_analysis": _signal("bullish", 0.8),
            "oscillator_check": _signal("neutral", 0.4, risk_level="medium", needs_review=True),
            "trend_application_dulling_divergence": _signal("neutral", 0.3, risk_level="high", needs_review=True),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["meta"]["risk_level"], "high")
        self.assertTrue(out["fused_signal"]["meta"]["needs_human_review"])


if __name__ == "__main__":
    unittest.main()

