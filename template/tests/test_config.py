import pytest

import config


def test_enable_mcp_apps_defaults_to_on(monkeypatch):
    monkeypatch.delenv("ENABLE_MCP_APPS", raising=False)

    assert config._env_flag("ENABLE_MCP_APPS") is True


@pytest.mark.parametrize("value", ["false", "FALSE", "False", "0", "no", "No", " no "])
def test_enable_mcp_apps_disabling_values(monkeypatch, value):
    monkeypatch.setenv("ENABLE_MCP_APPS", value)

    assert config._env_flag("ENABLE_MCP_APPS") is False


@pytest.mark.parametrize("value", ["true", "1", "yes", ""])
def test_enable_mcp_apps_other_values_stay_on(monkeypatch, value):
    monkeypatch.setenv("ENABLE_MCP_APPS", value)

    assert config._env_flag("ENABLE_MCP_APPS") is True


def test_config_exposes_enable_mcp_apps():
    assert isinstance(config.ENABLE_MCP_APPS, bool)
