"""Tests for the Nacos client and config integration."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from kimi_cli.config import (
    Config,
    NacosSettings,
    VideoProviderConfig,
    _merge_nacos_configs,
    _resolve_nacos_settings,
    get_default_config,
)


class TestNacosSettings:
    """Tests for NacosSettings validation."""

    def test_defaults(self):
        settings = NacosSettings()
        assert settings.server_addr == ""
        assert settings.namespace == ""
        assert settings.username == ""
        assert settings.password == ""
        assert settings.group == "DEFAULT_GROUP"

    def test_custom_values(self):
        settings = NacosSettings(
            server_addr="http://10.0.0.1:8848",
            namespace="ns1",
            username="admin",
            password="secret",
            group="MY_GROUP",
        )
        assert settings.server_addr == "http://10.0.0.1:8848"
        assert settings.namespace == "ns1"
        assert settings.group == "MY_GROUP"

    def test_config_has_nacos_field(self):
        config = get_default_config()
        assert config.nacos is None

    def test_config_with_nacos(self):
        config = Config(
            nacos=NacosSettings(
                server_addr="http://localhost:8848",
                namespace="test",
            )
        )
        assert config.nacos is not None
        assert config.nacos.server_addr == "http://localhost:8848"


class TestResolveNacosSettings:
    """Tests for _resolve_nacos_settings."""

    def test_returns_none_when_no_config_or_env(self):
        config = get_default_config()
        assert _resolve_nacos_settings(config) is None

    def test_returns_settings_from_config(self):
        config = Config(
            nacos=NacosSettings(
                server_addr="http://10.0.0.1:8848",
                namespace="ns1",
            )
        )
        result = _resolve_nacos_settings(config)
        assert result is not None
        assert result.server_addr == "http://10.0.0.1:8848"

    def test_env_vars_take_precedence(self):
        config = Config(
            nacos=NacosSettings(
                server_addr="http://from-config:8848",
            )
        )
        env = {
            "NACOS_IP": "10.0.0.2",
            "NACOS_NAMESPACE": "env-ns",
            "NACOS_USERNAME": "env-user",
            "NACOS_PASSWORD": "env-pass",
        }
        with patch.dict(os.environ, env, clear=False):
            result = _resolve_nacos_settings(config)
        assert result is not None
        assert result.server_addr == "http://10.0.0.2:8848"
        assert result.namespace == "env-ns"
        assert result.username == "env-user"

    def test_env_custom_port(self):
        env = {"NACOS_IP": "10.0.0.3", "NACOS_PORT": "9999"}
        with patch.dict(os.environ, env, clear=False):
            result = _resolve_nacos_settings(get_default_config())
        assert result is not None
        assert result.server_addr == "http://10.0.0.3:9999"

    def test_returns_none_when_nacos_has_empty_server_addr(self):
        config = Config(nacos=NacosSettings(server_addr=""))
        assert _resolve_nacos_settings(config) is None


class TestNacosClient:
    """Tests for the NacosClient HTTP calls."""

    def test_login_success(self, httpx_mock):
        from kimi_cli.nacos import NacosClient

        httpx_mock.add_response(
            url="http://localhost:8848/nacos/v1/auth/login",
            method="POST",
            json={"accessToken": "tok123"},
        )

        client = NacosClient(
            server_addr="http://localhost:8848",
            username="admin",
            password="pass",
        )
        client.login()
        assert client._access_token == "tok123"

    def test_login_failure_does_not_raise(self, httpx_mock):
        from kimi_cli.nacos import NacosClient

        httpx_mock.add_response(
            url="http://localhost:8848/nacos/v1/auth/login",
            method="POST",
            status_code=403,
        )

        client = NacosClient(
            server_addr="http://localhost:8848",
            username="admin",
            password="wrong",
        )
        client.login()  # Should not raise
        assert client._access_token == ""

    def test_login_skipped_when_no_username(self):
        from kimi_cli.nacos import NacosClient

        client = NacosClient(server_addr="http://localhost:8848")
        client.login()  # no-op
        assert client._access_token == ""

    def test_get_config_success(self, httpx_mock):
        from kimi_cli.nacos import NacosClient

        httpx_mock.add_response(
            method="GET",
            text=json.dumps({"api_key": "sk-123", "base_url": "https://api.example.com"}),
        )

        client = NacosClient(
            server_addr="http://localhost:8848",
            namespace="ns1",
        )
        result = client.get_config("sora_config")
        assert result["api_key"] == "sk-123"
        assert result["base_url"] == "https://api.example.com"

    def test_get_config_failure_returns_empty_dict(self, httpx_mock):
        from kimi_cli.nacos import NacosClient

        httpx_mock.add_response(
            method="GET",
            status_code=404,
        )

        client = NacosClient(server_addr="http://localhost:8848")
        result = client.get_config("nonexistent")
        assert result == {}

    def test_get_config_includes_access_token(self, httpx_mock):
        from kimi_cli.nacos import NacosClient

        httpx_mock.add_response(
            url="http://localhost:8848/nacos/v1/auth/login",
            method="POST",
            json={"accessToken": "tok456"},
        )
        httpx_mock.add_response(
            method="GET",
            text=json.dumps({"key": "val"}),
        )

        client = NacosClient(
            server_addr="http://localhost:8848",
            namespace="ns",
            username="u",
            password="p",
        )
        client.login()
        client.get_config("test")

        # Verify the GET request included accessToken param
        requests = httpx_mock.get_requests()
        get_req = [r for r in requests if r.method == "GET"][0]
        assert "accessToken=tok456" in str(get_req.url)


class TestMergeNacosConfigs:
    """Tests for _merge_nacos_configs integration."""

    def test_sora_config_merged(self):
        """sora_config from Nacos should create a video_providers['sora'] entry."""
        config = get_default_config()

        mock_nacos_data = {
            "sora_config": {"api_key": "sk-sora", "base_url": "https://api.apiyi.com", "model": "sora"},
        }

        with patch("kimi_cli.config._resolve_nacos_settings") as mock_resolve, \
             patch("kimi_cli.nacos.NacosClient") as MockClient:
            mock_resolve.return_value = NacosSettings(server_addr="http://fake:8848")
            mock_client = MockClient.return_value
            mock_client.get_config.side_effect = lambda data_id: mock_nacos_data.get(data_id, {})

            _merge_nacos_configs(config)

        assert "sora" in config.video_providers
        assert config.video_providers["sora"].type == "apiyi"
        assert config.video_providers["sora"].api_key.get_secret_value() == "sk-sora"

    def test_sora_config_does_not_overwrite_local(self):
        """If video_providers['sora'] already exists locally, Nacos should not overwrite."""
        config = get_default_config()
        config.video_providers["sora"] = VideoProviderConfig(
            type="sora", api_key=SecretStr("local-key")
        )

        mock_nacos_data = {
            "sora_config": {"api_key": "sk-remote", "base_url": "https://api.apiyi.com"},
        }

        with patch("kimi_cli.config._resolve_nacos_settings") as mock_resolve, \
             patch("kimi_cli.nacos.NacosClient") as MockClient:
            mock_resolve.return_value = NacosSettings(server_addr="http://fake:8848")
            mock_client = MockClient.return_value
            mock_client.get_config.side_effect = lambda data_id: mock_nacos_data.get(data_id, {})

            _merge_nacos_configs(config)

        # Local config should be preserved
        assert config.video_providers["sora"].api_key.get_secret_value() == "local-key"
        assert config.video_providers["sora"].type == "sora"

    def test_openai_config_merged(self):
        """openai_config from Nacos should create providers['main'] and models['default']."""
        config = get_default_config()

        mock_nacos_data = {
            "sora_config": {},
            "openai_config": {
                "api_key": "sk-openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
            },
        }

        with patch("kimi_cli.config._resolve_nacos_settings") as mock_resolve, \
             patch("kimi_cli.nacos.NacosClient") as MockClient:
            mock_resolve.return_value = NacosSettings(server_addr="http://fake:8848")
            mock_client = MockClient.return_value
            mock_client.get_config.side_effect = lambda data_id: mock_nacos_data.get(data_id, {})

            _merge_nacos_configs(config)

        assert "main" in config.providers
        assert config.providers["main"].api_key.get_secret_value() == "sk-openai"
        assert "default" in config.models
        assert config.models["default"].model == "gpt-4o"
        assert config.default_model == "default"

    def test_openai_config_skipped_when_main_exists(self):
        """If providers['main'] already exists, openai_config should be skipped."""
        from kimi_cli.config import LLMProvider

        config = get_default_config()
        config.providers["main"] = LLMProvider(
            type="openai_legacy",
            base_url="https://local.api",
            api_key=SecretStr("local-key"),
        )

        mock_nacos_data = {
            "sora_config": {},
            "openai_config": {"api_key": "sk-remote", "base_url": "https://remote.api"},
        }

        with patch("kimi_cli.config._resolve_nacos_settings") as mock_resolve, \
             patch("kimi_cli.nacos.NacosClient") as MockClient:
            mock_resolve.return_value = NacosSettings(server_addr="http://fake:8848")
            mock_client = MockClient.return_value
            mock_client.get_config.side_effect = lambda data_id: mock_nacos_data.get(data_id, {})

            _merge_nacos_configs(config)

        assert config.providers["main"].api_key.get_secret_value() == "local-key"

    def test_no_nacos_settings_is_noop(self):
        """When no Nacos settings available, _merge_nacos_configs should be a no-op."""
        config = get_default_config()

        with patch("kimi_cli.config._resolve_nacos_settings", return_value=None):
            _merge_nacos_configs(config)

        assert config.video_providers == {}
        assert config.providers == {}
