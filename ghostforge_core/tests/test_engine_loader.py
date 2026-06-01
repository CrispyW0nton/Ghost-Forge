"""Loader: env-driven EngineConfig + default registry shape."""

from __future__ import annotations

import json

import pytest

from ghostforge_core.engines import (
    UnityEngineAdapter,
    UnrealEngineAdapter,
    config_from_env,
    default_engine_adapters,
)


def test_default_registry_has_unity_and_unreal():
    registry = default_engine_adapters()
    assert set(registry.names()) == {"unity", "unreal"}
    assert isinstance(registry.get("unity"), UnityEngineAdapter)
    assert isinstance(registry.get("unreal"), UnrealEngineAdapter)


def test_get_unknown_engine_raises():
    registry = default_engine_adapters()
    with pytest.raises(KeyError):
        registry.get("nope")


def test_config_from_env_defaults_to_none(monkeypatch):
    monkeypatch.delenv("GHOSTFORGE_UNITY_MCP_TRANSPORT", raising=False)
    cfg = config_from_env("unity")
    assert cfg.name == "unity"
    assert cfg.transport == "none"
    assert cfg.command == []


def test_config_from_env_stdio(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_COMMAND", "python -m unity_mcp_ghost --port 0")
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_PROJECT", "C:/Projects/Game")
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_TIMEOUT", "45")
    cfg = config_from_env("unity")
    assert cfg.transport == "stdio"
    assert cfg.command == ["python", "-m", "unity_mcp_ghost", "--port", "0"]
    assert cfg.project_path == "C:/Projects/Game"
    assert cfg.timeout_seconds == 45.0


def test_config_from_env_http_with_headers(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_UNREAL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("GHOSTFORGE_UNREAL_MCP_URL", "http://localhost:7777/mcp")
    monkeypatch.setenv(
        "GHOSTFORGE_UNREAL_MCP_HEADERS", json.dumps({"Authorization": "Bearer x"})
    )
    cfg = config_from_env("unreal")
    assert cfg.transport == "http"
    assert cfg.url == "http://localhost:7777/mcp"
    assert cfg.headers == {"Authorization": "Bearer x"}


def test_config_from_env_stdio_without_command_falls_back_to_none(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("GHOSTFORGE_UNITY_MCP_COMMAND", raising=False)
    cfg = config_from_env("unity")
    assert cfg.transport == "none"


def test_config_from_env_http_without_url_falls_back_to_none(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_UNREAL_MCP_TRANSPORT", "http")
    monkeypatch.delenv("GHOSTFORGE_UNREAL_MCP_URL", raising=False)
    cfg = config_from_env("unreal")
    assert cfg.transport == "none"


def test_config_from_env_unknown_transport_falls_back(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_UNITY_MCP_TRANSPORT", "carrier-pigeon")
    cfg = config_from_env("unity")
    assert cfg.transport == "none"
