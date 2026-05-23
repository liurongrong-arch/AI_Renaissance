import math
import random
import unittest

from fusion_traditional_models.models.oscillator import analyze as analyze_osc
from fusion_traditional_models.models.trend_application import analyze as analyze_trend_app
from fusion_traditional_models.models.trend_tracking import analyze as analyze_trend
from fusion_traditional_models.models.volume_price import analyze as analyze_volume


def _make_rows(n: int, seed: int = 7):
    random.seed(seed)
    rows = []
    price = 100.0
    for i in range(n):
        # mild trend + noise to avoid extreme RSI
        drift = 0.05
        noise = (random.random() - 0.5) * 0.8
        price = max(1.0, price + drift + noise)
        high = price * (1.0 + 0.005)
        low = price * (1.0 - 0.005)
        open_ = price * (1.0 + (random.random() - 0.5) * 0.002)
        volume = 1_000_000 + int((random.random() - 0.5) * 200_000)
        rows.append(
            {
                "date": f"2026-01-{(i%28)+1:02d}",
                "open": open_,
                "high": high,
                "low": low,
                "close": price,
                "volume": float(volume),
            }
        )
    return rows


class TestModelOutputs(unittest.TestCase):
    def test_volume_price_schema_minimal(self):
        rows = _make_rows(10)
        sig = analyze_volume(rows, stock_code="000001", target="t", source_name="x.csv")
        self.assertIn("direction", sig)
        self.assertIn("confidence", sig)
        self.assertIn("meta", sig)
        self.assertIsInstance(sig["meta"], dict)

    def test_oscillator_requires_30(self):
        rows = _make_rows(20)
        sig = analyze_osc(rows)
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_trend_requires_60(self):
        rows = _make_rows(40)
        sig = analyze_trend(rows)
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_trend_app_requires_30(self):
        rows = _make_rows(20)
        sig = analyze_trend_app(rows)
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_volume_price_marks_missing_volume(self):
        rows = _make_rows(80)
        rows[-1]["volume"] = math.nan
        sig = analyze_volume(rows)
        self.assertTrue(sig["meta"]["needs_human_review"])
        self.assertIn("volume", " ".join(sig["meta"].get("uncertainties", [])))


if __name__ == "__main__":
    unittest.main()

