"""
WebhookSender - Async fire-and-forget HTTP POST helper for the Output Node.

Supports Bearer, Basic Auth, API Key, and custom header authentication.
All failures are logged at ERROR level; exceptions are never re-raised.
"""
import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class WebhookSender:
    """Async fire-and-forget HTTP POST to a configured endpoint."""

    def __init__(self, url: str, headers: Dict[str, str], timeout: float = 10.0) -> None:
        self._url = url
        self._headers = headers
        self._timeout = timeout

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> Optional["WebhookSender"]:
        """
        Build a WebhookSender from node config dict.

        Returns None if webhook_enabled is falsy or webhook_url is empty.
        """
        if not config.get("webhook_enabled"):
            return None
        url = (config.get("webhook_url") or "").strip()
        if not url:
            return None

        headers = cls._build_auth_headers(config)

        # Parse custom headers — accept dict (already deserialized) or JSON string
        custom_raw = config.get("webhook_custom_headers") or "{}"
        if isinstance(custom_raw, dict):
            custom: Dict[str, str] = custom_raw
        else:
            try:
                parsed = json.loads(custom_raw)
                custom = parsed if isinstance(parsed, dict) else {}
            except Exception:
                logger.warning(
                    "webhook_custom_headers is not valid JSON — ignoring custom headers"
                )
                custom = {}

        headers.update(custom)
        headers["Content-Type"] = "application/json"
        return cls(url=url, headers=headers)

    @staticmethod
    def _build_auth_headers(config: Dict[str, Any]) -> Dict[str, str]:
        """Build authentication headers based on auth_type config."""
        auth_type = config.get("webhook_auth_type", "none")
        if auth_type == "bearer":
            token = config.get("webhook_auth_token", "") or ""
            return {"Authorization": f"Bearer {token}"}
        elif auth_type == "basic":
            user = config.get("webhook_auth_username", "") or ""
            pwd = config.get("webhook_auth_password", "") or ""
            encoded = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        elif auth_type == "api_key":
            key_name = config.get("webhook_auth_key_name") or "X-API-Key"
            key_value = config.get("webhook_auth_key_value", "") or ""
            return {key_name: key_value}
        return {}

    async def send(self, payload: Dict[str, Any]) -> None:
        """POST payload as JSON. Logs errors; never raises."""
        try:
            body = json.dumps(payload)
            await asyncio.to_thread(self._sync_post, body)
        except Exception as e:
            logger.error(f"Webhook POST failed [{self._url}]: {e}")

    def _sync_post(self, body: str) -> None:
        """Synchronous HTTP POST — runs in a thread pool via asyncio.to_thread."""
        import httpx  # Lazy import to avoid startup cost when webhook is disabled

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, content=body, headers=self._headers)
            if resp.status_code >= 400:
                logger.error(f"Webhook [{self._url}] returned {resp.status_code}")
            else:
                logger.debug(f"Webhook [{self._url}] returned {resp.status_code}")
