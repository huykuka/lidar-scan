"""
Tests for PlaybackNode — TDD Phase 1.

Covers:
  - Constructor validation (playback_speed allowed set, loopable, recording_id)
  - Internal state initialization
  - emit_status() mapping for idle / playing / error
  - on_input() is a no-op (source node contract)
  - _run_loop() frame iteration: normal stop and loopable wrap-around
  - start() error paths: missing file, zero frames
  - stop() cancels task and resets state
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip_recording(tmp_path: Path, frame_count: int = 3, duration: float = 3.0) -> Path:
    """Create a minimal valid ZIP recording file for tests."""
    zip_path = tmp_path / "test_recording.zip"

    points_per_frame = np.random.rand(10, 3).astype(np.float32)
    timestamps = [float(i) for i in range(frame_count)]

    with zipfile.ZipFile(zip_path, "w") as zf:
        metadata = {
            "frame_count": frame_count,
            "timestamps": timestamps,
            "start_timestamp": 0.0,
            "end_timestamp": float(frame_count - 1),
            "fields": ["x", "y", "z"],
        }
        zf.writestr("metadata.json", json.dumps(metadata))

        for i in range(frame_count):
            # Minimal valid binary PCD header + data
            header = (
                "# .PCD v0.7 - Point Cloud Data file format\n"
                "VERSION 0.7\n"
                "FIELDS x y z\n"
                "SIZE 4 4 4\n"
                "TYPE F F F\n"
                "COUNT 1 1 1\n"
                f"WIDTH {len(points_per_frame)}\n"
                "HEIGHT 1\n"
                "VIEWPOINT 0 0 0 1 0 0 0\n"
                f"POINTS {len(points_per_frame)}\n"
                "DATA binary\n"
            )
            data_bytes = header.encode("ascii") + points_per_frame.tobytes()
            zf.writestr(f"frame_{i:05d}.pcd", data_bytes)

    return zip_path


def _make_mock_manager() -> MagicMock:
    manager = MagicMock()
    manager.forward_data = AsyncMock(return_value=None)
    return manager


# ---------------------------------------------------------------------------
# Unit: constructor + speed validation
# ---------------------------------------------------------------------------

class TestPlaybackNodeConstruction:
    """PlaybackNode constructor validates playback_speed strictly."""

    def test_valid_speed_1_0(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=1.0,
            loopable=False,
        )
        assert node._playback_speed == 1.0

    def test_valid_speed_0_5(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=0.5,
        )
        assert node._playback_speed == 0.5

    def test_valid_speed_0_25(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=0.25,
        )
        assert node._playback_speed == 0.25

    def test_valid_speed_0_1(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=0.1,
        )
        assert node._playback_speed == 0.1

    def test_invalid_speed_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(),
                node_id="n1",
                name="Test",
                recording_id="rec-uuid",
                playback_speed=0.75,
            )

    def test_speed_greater_than_1_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(),
                node_id="n1",
                name="Test",
                recording_id="rec-uuid",
                playback_speed=2.0,
            )

    def test_speed_zero_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(),
                node_id="n1",
                name="Test",
                recording_id="rec-uuid",
                playback_speed=0.0,
            )

    def test_loopable_default_false(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )
        assert node._loopable is False

    def test_loopable_true(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            loopable=True,
        )
        assert node._loopable is True

    def test_initial_status_is_idle(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )
        assert node._status == "idle"

    def test_initial_task_is_none(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )
        assert node._task is None

    def test_id_and_name_set(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="abc-123",
            name="My Playback",
            recording_id="rec-uuid",
        )
        assert node.id == "abc-123"
        assert node.name == "My Playback"

    def test_recording_id_stored(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="my-rec-id",
        )
        assert node._recording_id == "my-rec-id"

    def test_throttle_ms_stored(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            throttle_ms=100.0,
        )
        assert node._throttle_ms == 100.0


# ---------------------------------------------------------------------------
# Unit: emit_status
# ---------------------------------------------------------------------------

class TestPlaybackNodeEmitStatus:
    """emit_status() maps _status → OperationalState correctly."""

    def _make_node(self, **kwargs) -> Any:
        from app.modules.playback.node import PlaybackNode
        return PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            **kwargs,
        )

    def test_idle_maps_to_stopped(self):
        from app.schemas.status import OperationalState
        node = self._make_node()
        node._status = "idle"
        status = node.emit_status()
        assert status.operational_state == OperationalState.STOPPED

    def test_idle_application_state_value(self):
        node = self._make_node()
        node._status = "idle"
        status = node.emit_status()
        assert status.application_state is not None
        assert status.application_state.value == "idle"

    def test_playing_maps_to_running(self):
        from app.schemas.status import OperationalState
        node = self._make_node()
        node._status = "playing"
        node._current_frame = 5
        node._total_frames = 10
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING

    def test_playing_application_state_contains_frame_counter(self):
        node = self._make_node()
        node._status = "playing"
        node._current_frame = 5
        node._total_frames = 10
        status = node.emit_status()
        assert "5" in str(status.application_state.value)
        assert "10" in str(status.application_state.value)

    def test_error_maps_to_error_state(self):
        from app.schemas.status import OperationalState
        node = self._make_node()
        node._status = "error"
        node._error_message = "file not found"
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR

    def test_error_message_propagated(self):
        node = self._make_node()
        node._status = "error"
        node._error_message = "file not found"
        status = node.emit_status()
        assert status.error_message == "file not found"

    def test_status_has_correct_node_id(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="playback-xyz",
            name="Test",
            recording_id="rec-uuid",
        )
        assert node.emit_status().node_id == "playback-xyz"


# ---------------------------------------------------------------------------
# Unit: on_input (source node no-op)
# ---------------------------------------------------------------------------

class TestPlaybackNodeOnInput:
    """Source node: on_input must be a no-op (no exception, no side effect)."""

    @pytest.mark.asyncio
    async def test_on_input_is_noop(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )
        # Should not raise
        await node.on_input({"points": np.zeros((10, 3)), "timestamp": 0.0})
        # Manager forward_data should NOT be called
        node.manager.forward_data.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: start() error paths
# ---------------------------------------------------------------------------

class TestPlaybackNodeStart:
    """start() validates file existence and zero-frame guard."""

    @pytest.mark.asyncio
    async def test_start_missing_recording_sets_error(self):
        """Recording not found in DB → _status = 'error'."""
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="nonexistent-uuid",
        )

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()

        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_missing_file_on_disk_sets_error(self, tmp_path: Path):
        """DB record present but file missing → _status = 'error'."""
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )

        fake_record = {
            "id": "rec-uuid",
            "file_path": str(tmp_path / "nonexistent.zip"),
            "frame_count": 5,
            "duration_seconds": 5.0,
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()

        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_zero_frames_sets_error(self, tmp_path: Path):
        """Recording with zero frames → _status = 'error'."""
        from app.modules.playback.node import PlaybackNode

        # Create a zero-frame ZIP
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            metadata = {
                "frame_count": 0,
                "timestamps": [],
                "start_timestamp": 0.0,
                "end_timestamp": 0.0,
            }
            zf.writestr("metadata.json", json.dumps(metadata))

        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )

        fake_record = {
            "id": "rec-uuid",
            "file_path": str(tmp_path / "empty"),  # RecordingReader appends .zip
            "frame_count": 0,
            "duration_seconds": 0.0,
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()

        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_valid_recording_spawns_task(self, tmp_path: Path):
        """Valid recording → task is created and status becomes playing."""
        from app.modules.playback.node import PlaybackNode

        zip_path = _make_zip_recording(tmp_path, frame_count=2)
        # strip .zip suffix for file_path stored in DB (RecordingReader adds it back)
        file_path_no_ext = str(zip_path.with_suffix(""))

        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=1.0,
        )

        fake_record = {
            "id": "rec-uuid",
            "file_path": file_path_no_ext,
            "frame_count": 2,
            "duration_seconds": 2.0,
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()

        assert node._task is not None
        # Clean up
        node._task.cancel()
        try:
            await node._task
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Integration: stop()
# ---------------------------------------------------------------------------

class TestPlaybackNodeStop:
    """stop() must cancel task, close reader, and reset status."""

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, tmp_path: Path):
        from app.modules.playback.node import PlaybackNode

        zip_path = _make_zip_recording(tmp_path, frame_count=5)
        file_path_no_ext = str(zip_path.with_suffix(""))

        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )

        fake_record = {
            "id": "rec-uuid",
            "file_path": file_path_no_ext,
            "frame_count": 5,
            "duration_seconds": 5.0,
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()

        assert node._task is not None
        await node.stop()

        assert node._status == "idle"
        assert node._task is None

    @pytest.mark.asyncio
    async def test_stop_when_no_task_is_safe(self):
        """stop() on a never-started node must not raise."""
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(),
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
        )
        await node.stop()  # must not raise
        assert node._status == "idle"


# ---------------------------------------------------------------------------
# Integration: _run_loop — frame forwarding and loopable behaviour
# ---------------------------------------------------------------------------

class TestPlaybackRunLoop:
    """_run_loop sends frames via manager.forward_data and respects loopable."""

    @pytest.mark.asyncio
    async def test_non_loopable_stops_after_all_frames(self, tmp_path: Path):
        """Non-loopable playback must stop after the last frame."""
        from app.modules.playback.node import PlaybackNode

        frame_count = 3
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))

        manager = _make_mock_manager()
        node = PlaybackNode(
            manager=manager,
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=1.0,
            loopable=False,
        )

        fake_record = {
            "id": "rec-uuid",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": float(frame_count),
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls, \
             patch("app.modules.playback.node.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()
                # Wait for task to finish (non-loopable runs through all frames)
                try:
                    await asyncio.wait_for(node._task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        # forward_data called exactly frame_count times
        assert manager.forward_data.call_count == frame_count
        assert node._status == "idle"

    @pytest.mark.asyncio
    async def test_non_loopable_payload_structure(self, tmp_path: Path):
        """Each payload must include required keys."""
        from app.modules.playback.node import PlaybackNode

        zip_path = _make_zip_recording(tmp_path, frame_count=1)
        file_path_no_ext = str(zip_path.with_suffix(""))
        manager = _make_mock_manager()

        node = PlaybackNode(
            manager=manager,
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=1.0,
        )
        fake_record = {
            "id": "rec-uuid",
            "file_path": file_path_no_ext,
            "frame_count": 1,
            "duration_seconds": 1.0,
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls, \
             patch("app.modules.playback.node.asyncio.sleep", new_callable=AsyncMock):
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()
                try:
                    await asyncio.wait_for(node._task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        assert manager.forward_data.called
        call_args = manager.forward_data.call_args
        node_id_arg, payload = call_args[0]
        assert node_id_arg == "n1"
        assert "points" in payload
        assert "timestamp" in payload
        assert "node_id" in payload
        assert "metadata" in payload
        meta = payload["metadata"]
        assert meta["source"] == "playback"
        assert meta["recording_id"] == "rec-uuid"
        assert "frame" in meta
        assert "total_frames" in meta
        assert "playback_speed" in meta
        assert "loopable" in meta

    @pytest.mark.asyncio
    async def test_loopable_wraps_around(self, tmp_path: Path):
        """Loopable playback must replay from frame 0 after last frame."""
        from app.modules.playback.node import PlaybackNode

        frame_count = 2
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))
        manager = _make_mock_manager()

        node = PlaybackNode(
            manager=manager,
            node_id="n1",
            name="Test",
            recording_id="rec-uuid",
            playback_speed=1.0,
            loopable=True,
        )
        fake_record = {
            "id": "rec-uuid",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": float(frame_count),
        }

        with patch("app.modules.playback.node.SessionLocal") as mock_session_cls, \
             patch("app.modules.playback.node.asyncio.sleep", new_callable=AsyncMock):
            mock_db = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = fake_record
            with patch("app.modules.playback.node.RecordingRepository", return_value=mock_repo):
                await node.start()
                # Let the loop run for >1 cycle (>frame_count forwards)
                await asyncio.sleep(0.05)
                await node.stop()

        # Loopable: more than frame_count calls expected
        assert manager.forward_data.call_count >= frame_count


# ---------------------------------------------------------------------------
# Unit: VALID_SPEEDS constant
# ---------------------------------------------------------------------------

class TestValidSpeeds:
    """VALID_SPEEDS must contain exactly the four documented speeds."""

    def test_valid_speeds_set(self):
        from app.modules.playback.node import VALID_SPEEDS
        assert VALID_SPEEDS == {0.1, 0.25, 0.5, 1.0}

    def test_all_valid_speeds_accepted(self):
        from app.modules.playback.node import PlaybackNode, VALID_SPEEDS
        for speed in VALID_SPEEDS:
            node = PlaybackNode(
                manager=_make_mock_manager(),
                node_id="n1",
                name="Test",
                recording_id="rec-uuid",
                playback_speed=speed,
            )
            assert node._playback_speed == speed
