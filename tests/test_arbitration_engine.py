from arbitration.engine import ArbitrationEngine


def test_generate_reasoning_chain_uses_numeric_signal_counts():
    engine = ArbitrationEngine()

    chain = engine._generate_reasoning_chain(
        signals_summary={"total": 1, "bullish": 1, "bearish": 0, "neutral": 0},
        direction="bullish",
        confidence=0.74,
        position_ratio=0.3,
        risks=[],
    )

    assert chain[0] == "📊 信号汇总：共1个信号，看多1个，看空0个，中性0个"
