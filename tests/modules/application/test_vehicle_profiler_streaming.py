"""
Unit tests for ProfileStreamer.

Covers:
  - Topic naming from node_id
  - enabled/disabled toggle
  - broadcast skips when disabled
  - broadcast skips when no subscribers
  - broadcast packs and sends LIDR binary when subscribers present
  - broadcast swallows exceptions gracefully
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.modules.application.vehicle_profiler.utils.streaming import ProfileStreamer


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sample_points(n: int = 10) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(-1, 1, (n, 3)).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def streamer() -> ProfileStreamer:
    return ProfileStreamer("vp-001234", enabled=True)


@pytest.fixture
def disabled_streamer() -> ProfileStreamer:
    return ProfileStreamer("vp-001234", enabled=False)


# ─────────────────────────────────────────────────────────────────────────────
# TestInstantiation
# ─────────────────────────────────────────────────────────────────────────────

class TestInstantiation:
    def test_topic_derived_from_node_id(self, streamer):
        assert streamer.topic == "profile_partial_streaming_vp-00123"

    def test_enabled_by_default_false(self):
        s = ProfileStreamer("abc")
        assert s.enabled is False

    def test_enabled_when_set(self, streamer):
        assert streamer.enabled is True

    def test_enabled_setter(self, disabled_streamer):
        disabled_streamer.enabled = True
        assert disabled_streamer.enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# TestBroadcast
# ─────────────────────────────────────────────────────────────────────────────

class TestBroadcast:
    @pytest.mark.asyncio
    async def test_noop_when_disabled(self, disabled_streamer):
        with patch("app.modules.application.vehicle_profiler.utils.streaming.ws_manager") as mock_ws:
            await disabled_streamer.broadcast(_sample_points(), 1.0)
            mock_ws.has_subscribers.assert_not_called()
            mock_ws.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_when_no_subscribers(self, streamer):
        with patch("app.modules.application.vehicle_profiler.utils.streaming.ws_manager") as mock_ws:
            mock_ws.has_subscribers.return_value = False
            await streamer.broadcast(_sample_points(), 1.0)
            mock_ws.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcasts_binary_when_subscribers(self, streamer):
        with patch("app.modules.application.vehicle_profiler.utils.streaming.ws_manager") as mock_ws:
            mock_ws.has_subscribers.return_value = True
            mock_ws.broadcast = AsyncMock()
            await streamer.broadcast(_sample_points(), 1.0)
            mock_ws.broadcast.assert_called_once()
            topic_arg = mock_ws.broadcast.call_args[0][0]
            binary_arg = mock_ws.broadcast.call_args[0][1]
            assert topic_arg == streamer.topic
            assert isinstance(binary_arg, bytes)
            assert binary_arg[:4] == b"LIDR"

    @pytest.mark.asyncio
    async def test_broadcast_swallows_exception(self, streamer):
        with patch("app.modules.application.vehicle_profiler.utils.streaming.ws_manager") as mock_ws:
            mock_ws.has_subscribers.return_value = True
            mock_ws.broadcast = AsyncMock(side_effect=RuntimeError("boom"))
            # Should not raise
            await streamer.broadcast(_sample_points(), 1.0)

    @pytest.mark.asyncio
    async def test_broadcast_checks_correct_topic(self, streamer):
        with patch("app.modules.application.vehicle_profiler.utils.streaming.ws_manager") as mock_ws:
            mock_ws.has_subscribers.return_value = False
            await streamer.broadcast(_sample_points(), 1.0)
            mock_ws.has_subscribers.assert_called_once_with(streamer.topic)
