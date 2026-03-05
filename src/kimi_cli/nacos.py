"""Nacos configuration center HTTP client.

Provides a lightweight, synchronous client to fetch remote configuration
(e.g. API keys for video / LLM providers) from a Nacos server.  Only called
once at startup; errors are logged as warnings and never block the process.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from kimi_cli.utils.logging import logger

_LOGIN_PATH = "/nacos/v1/auth/login"
_CONFIG_PATH = "/nacos/v1/cs/configs"
_DEFAULT_GROUP = "DEFAULT_GROUP"


class NacosClient:
    """Minimal Nacos HTTP client (synchronous, read-only)."""

    def __init__(
        self,
        server_addr: str,
        namespace: str = "",
        username: str = "",
        password: str = "",
        group: str = _DEFAULT_GROUP,
    ) -> None:
        self._server_addr = server_addr.rstrip("/")
        self._namespace = namespace
        self._username = username
        self._password = password
        self._group = group
        self._access_token: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate with Nacos and store the access token."""
        if not self._username:
            return
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self._server_addr}{_LOGIN_PATH}",
                    data={"username": self._username, "password": self._password},
                )
                resp.raise_for_status()
                self._access_token = resp.json().get("accessToken", "")
            logger.debug("Nacos login succeeded")
        except Exception as exc:
            logger.warning("Nacos login failed: {exc}", exc=exc)

    def get_config(self, data_id: str) -> dict[str, Any]:
        """Fetch a single configuration item and parse it as JSON.

        Returns an empty dict on any failure so callers can safely proceed.
        """
        params: dict[str, str] = {
            "dataId": data_id,
            "group": self._group,
            "tenant": self._namespace,
        }
        if self._access_token:
            params["accessToken"] = self._access_token

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self._server_addr}{_CONFIG_PATH}",
                    params=params,
                )
                resp.raise_for_status()
                return json.loads(resp.text)
        except Exception as exc:
            logger.warning(
                "Nacos get_config({data_id}) failed: {exc}",
                data_id=data_id,
                exc=exc,
            )
            return {}
