from pathlib import Path

import pytest

from main import collect_signals, load_config


def test_load_config_uses_default_yaml_shape_when_missing():
    config = load_config("config/does-not-exist.yaml")

    assert config["confidence_threshold"] == 0.6
    assert config["bullish_weight"] == 1.0
    assert config["bearish_weight"] == 1.0
    assert config["agents"]["cash_flow"]["enabled"] is True
    assert config["agents"]["cash_flow"]["periods"] == 4


def test_load_config_reads_repo_default_yaml():
    config_file = Path(__file__).resolve().parents[1] / "config" / "default.yaml"

    config = load_config(str(config_file))

    assert config["confidence_threshold"] == 0.6
    assert config["agents"]["cash_flow"]["enabled"] is True


def test_collect_signals_respects_disabled_cash_flow_agent():
    bundle = collect_signals(
        stock_code="000001",
        config={
            "agents": {
                "cash_flow": {
                    "enabled": False,
                }
            }
        },
    )

    assert bundle.stock_code == "000001"
    assert bundle.signals == []


def test_load_config_supports_boolean_agent_toggle(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("agents:\n  cash_flow: false\n", encoding="utf-8")

    config = load_config(str(config_file))

    assert config["agents"]["cash_flow"]["enabled"] is False


def test_load_config_supports_legacy_agents_list(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("agents:\n  - cash_flow\n", encoding="utf-8")

    config = load_config(str(config_file))

    assert config["agents"]["cash_flow"]["enabled"] is True


def test_load_config_rejects_invalid_agents_list_entries(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("agents:\n  - 123\n", encoding="utf-8")

    with pytest.raises(ValueError, match="agents 列表中的条目必须是字符串"):
        load_config(str(config_file))
