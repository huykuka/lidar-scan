"""
Unit tests for WebhookSender.

Tests: from_config factory, auth header construction, send/sync_post behavior.

TDD: Tests written before implementation to drive development.
"""
import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.modules.flow_control.output.webhook import WebhookSender


# ---------------------------------------------------------------------------
# B6.2 — from_config tests
# ---------------------------------------------------------------------------

class TestWebhookSenderFromConfig:
    """Tests for WebhookSender.from_config class method."""

    def test_from_config_returns_none_when_disabled(self):
        """from_config returns None if webhook_enabled is False."""
        config = {
            "webhook_enabled": False,
            "webhook_url": "https://example.com/hook",
        }
        result = WebhookSender.from_config(config)
        assert result is None

    def test_from_config_returns_none_when_url_empty(self):
        """from_config returns None if webhook_url is empty string."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "",
        }
        result = WebhookSender.from_config(config)
        assert result is None

    def test_from_config_returns_none_when_url_whitespace_only(self):
        """from_config returns None if webhook_url is whitespace only."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "   ",
        }
        result = WebhookSender.from_config(config)
        assert result is None

    def test_from_config_returns_none_when_url_missing(self):
        """from_config returns None if webhook_url key is absent."""
        config = {"webhook_enabled": True}
        result = WebhookSender.from_config(config)
        assert result is None

    def test_from_config_returns_sender_when_valid(self):
        """from_config returns a WebhookSender when enabled and URL is valid."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        result = WebhookSender.from_config(config)
        assert isinstance(result, WebhookSender)

    def test_from_config_includes_content_type_header(self):
        """from_config always adds Content-Type: application/json."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }
        sender = WebhookSender.from_config(config)
        assert sender is not None
        assert sender._headers.get("Content-Type") == "application/json"

    def test_from_config_invalid_custom_headers_json_ignored(self):
        """Invalid JSON in webhook_custom_headers is silently ignored."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
            "webhook_custom_headers": "not-valid-json{{{",
        }
        sender = WebhookSender.from_config(config)
        assert sender is not None  # Should still succeed
        assert sender._headers.get("Content-Type") == "application/json"

    def test_from_config_merges_custom_headers(self):
        """Custom headers from JSON string are merged into _headers."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
            "webhook_custom_headers": '{"X-Source": "lidar-standalone", "X-Env": "prod"}',
        }
        sender = WebhookSender.from_config(config)
        assert sender is not None
        assert sender._headers.get("X-Source") == "lidar-standalone"
        assert sender._headers.get("X-Env") == "prod"

    def test_from_config_merges_custom_headers_as_dict(self):
        """Custom headers supplied as a dict (already deserialized) are merged."""
        config = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
            "webhook_custom_headers": {"X-Source": "lidar"},
        }
        sender = WebhookSender.from_config(config)
        assert sender is not None
        assert sender._headers.get("X-Source") == "lidar"


# ---------------------------------------------------------------------------
# B6.2 — _build_auth_headers tests
# ---------------------------------------------------------------------------

class TestBuildAuthHeaders:
    """Tests for WebhookSender._build_auth_headers static method."""

    def test_build_auth_headers_none_returns_empty(self):
        """auth_type='none' returns empty dict."""
        config = {"webhook_auth_type": "none"}
        result = WebhookSender._build_auth_headers(config)
        assert result == {}

    def test_build_auth_headers_missing_type_returns_empty(self):
        """Missing webhook_auth_type defaults to 'none' behavior (empty dict)."""
        result = WebhookSender._build_auth_headers({})
        assert result == {}

    def test_build_auth_headers_bearer(self):
        """auth_type='bearer' creates correct Authorization: Bearer header."""
        config = {
            "webhook_auth_type": "bearer",
            "webhook_auth_token": "my-secret-token",
        }
        result = WebhookSender._build_auth_headers(config)
        assert result == {"Authorization": "Bearer my-secret-token"}

    def test_build_auth_headers_bearer_empty_token(self):
        """Bearer with empty token still creates the header (empty value)."""
        config = {
            "webhook_auth_type": "bearer",
            "webhook_auth_token": "",
        }
        result = WebhookSender._build_auth_headers(config)
        assert "Authorization" in result
        assert result["Authorization"].startswith("Bearer ")

    def test_build_auth_headers_basic_base64(self):
        """auth_type='basic' creates correct base64-encoded Authorization header."""
        config = {
            "webhook_auth_type": "basic",
            "webhook_auth_username": "user",
            "webhook_auth_password": "pass",
        }
        result = WebhookSender._build_auth_headers(config)
        expected_encoded = base64.b64encode(b"user:pass").decode()
        assert result == {"Authorization": f"Basic {expected_encoded}"}

    def test_build_auth_headers_basic_special_chars(self):
        """Basic auth handles special characters in username/password."""
        config = {
            "webhook_auth_type": "basic",
            "webhook_auth_username": "user@domain.com",
            "webhook_auth_password": "p@ss:w0rd!",
        }
        result = WebhookSender._build_auth_headers(config)
        assert "Authorization" in result
        # Should be decodable
        b64_part = result["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(b64_part).decode()
        assert "user@domain.com" in decoded

    def test_build_auth_headers_api_key(self):
        """auth_type='api_key' creates custom header with key_name and key_value."""
        config = {
            "webhook_auth_type": "api_key",
            "webhook_auth_key_name": "X-API-Key",
            "webhook_auth_key_value": "secret-key-value",
        }
        result = WebhookSender._build_auth_headers(config)
        assert result == {"X-API-Key": "secret-key-value"}

    def test_build_auth_headers_api_key_custom_name(self):
        """API key header uses the configured key_name."""
        config = {
            "webhook_auth_type": "api_key",
            "webhook_auth_key_name": "X-Custom-Token",
            "webhook_auth_key_value": "abc123",
        }
        result = WebhookSender._build_auth_headers(config)
        assert "X-Custom-Token" in result
        assert result["X-Custom-Token"] == "abc123"

    def test_build_auth_headers_api_key_defaults_to_x_api_key(self):
        """API key uses 'X-API-Key' as default key_name when not specified."""
        config = {
            "webhook_auth_type": "api_key",
            "webhook_auth_key_value": "abc123",
        }
        result = WebhookSender._build_auth_headers(config)
        assert "X-API-Key" in result


# ---------------------------------------------------------------------------
# B6.2 — send / _sync_post behavior tests
# ---------------------------------------------------------------------------

class TestWebhookSenderSend:
    """Tests for WebhookSender.send and _sync_post."""

    @pytest.mark.asyncio
    async def test_send_calls_sync_post(self):
        """send() calls _sync_post via asyncio.to_thread."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        with patch.object(sender, "_sync_post") as mock_sync_post:
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=None) as mock_thread:
                await sender.send({"type": "output_node_metadata"})
                mock_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_failure_logs_error_does_not_raise(self):
        """send() logs an ERROR and does NOT re-raise on exception."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        with patch(
            "asyncio.to_thread", side_effect=Exception("connection refused")
        ), patch(
            "app.modules.flow_control.output.webhook.logger"
        ) as mock_logger:
            # Should NOT raise
            await sender.send({"type": "output_node_metadata"})
            mock_logger.error.assert_called_once()

    def test_sync_post_logs_debug_on_2xx(self):
        """_sync_post logs DEBUG when server returns 2xx."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post = Mock(return_value=mock_response)

        with patch("httpx.Client", return_value=mock_client), patch(
            "app.modules.flow_control.output.webhook.logger"
        ) as mock_logger:
            sender._sync_post('{"type": "test"}')
            mock_logger.debug.assert_called_once()
            mock_logger.error.assert_not_called()

    def test_sync_post_logs_error_on_4xx(self):
        """_sync_post logs ERROR when server returns 4xx."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post = Mock(return_value=mock_response)

        with patch("httpx.Client", return_value=mock_client), patch(
            "app.modules.flow_control.output.webhook.logger"
        ) as mock_logger:
            sender._sync_post('{"type": "test"}')
            mock_logger.error.assert_called_once()
            mock_logger.debug.assert_not_called()

    def test_sync_post_logs_error_on_5xx(self):
        """_sync_post logs ERROR when server returns 5xx."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        mock_response = Mock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post = Mock(return_value=mock_response)

        with patch("httpx.Client", return_value=mock_client), patch(
            "app.modules.flow_control.output.webhook.logger"
        ) as mock_logger:
            sender._sync_post('{"type": "test"}')
            mock_logger.error.assert_called_once()

    def test_sync_post_does_not_log_credentials(self):
        """ERROR log message on 4xx must not include auth header values."""
        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Authorization": "Bearer super-secret", "Content-Type": "application/json"},
        )
        mock_response = Mock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post = Mock(return_value=mock_response)

        with patch("httpx.Client", return_value=mock_client), patch(
            "app.modules.flow_control.output.webhook.logger"
        ) as mock_logger:
            sender._sync_post('{"type": "test"}')
            # Check that the logged message does not leak the token
            call_args = str(mock_logger.error.call_args)
            assert "super-secret" not in call_args

    @pytest.mark.asyncio
    async def test_send_sends_correct_json_body(self):
        """send() serializes the payload to JSON and passes it to _sync_post."""
        import json

        sender = WebhookSender(
            url="https://example.com/hook",
            headers={"Content-Type": "application/json"},
        )
        captured_body: list = []

        def fake_sync_post(body: str):
            captured_body.append(body)

        # Patch _sync_post directly on the instance, then patch asyncio.to_thread
        # to call our sync function synchronously so we can capture its arg.
        with patch.object(sender, "_sync_post", side_effect=fake_sync_post):
            with patch("asyncio.to_thread") as mock_thread:
                async def thread_sim(fn, arg):
                    fn(arg)

                mock_thread.side_effect = thread_sim
                payload = {"type": "output_node_metadata", "node_id": "n1", "metadata": {"x": 1}}
                await sender.send(payload)

        assert len(captured_body) == 1
        parsed = json.loads(captured_body[0])
        assert parsed["type"] == "output_node_metadata"
        assert parsed["node_id"] == "n1"
