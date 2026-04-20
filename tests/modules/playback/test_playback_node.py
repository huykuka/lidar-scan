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
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip_recording(tmp_path: Path, frame_count: int = 3) -> Path:
    """Create a minimal valid ZIP recording file for tests."""
    zip_path = tmp_path / "test_recording.zip"
    points = np.random.rand(10, 3).astype(np.float32)
    timestamps = [float(i) for i in range(frame_count)]

    with zipfile.ZipFile(zip_path, "w") as zf:
        metadata = {
            "frame_count": frame_count,
            "timestamps": timestamps,
            "start_timestamp": 0.0,
            "end_timestamp": float(max(frame_count - 1, 0)),
            "fields": ["x", "y", "z"],
        }
        zf.writestr("metadata.json", json.dumps(metadata))
        for i in range(frame_count):
            header = (
                "# .PCD v0.7 - Point Cloud Data file format\n"
                "VERSION 0.7\n"
                "FIELDS x y z\n"
                "SIZE 4 4 4\n"
                "TYPE F F F\n"
                "COUNT 1 1 1\n"
                f"WIDTH {len(points)}\n"
                "HEIGHT 1\n"
                "VIEWPOINT 0 0 0 1 0 0 0\n"
                f"POINTS {len(points)}\n"
                "DATA binary\n"
            )
            zf.writestr(f"frame_{i:05d}.pcd", header.encode("ascii") + points.tobytes())

    return zip_path


def _make_mock_manager() -> MagicMock:
    manager = MagicMock()
    manager.forward_data = AsyncMock(return_value=None)
    return manager


def _patch_db(mock_record: Any):
    """Return a context manager that patches SessionLocal + RecordingRepository."""
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = mock_record
    mock_repo_cls = MagicMock(return_value=mock_repo)

    mock_db = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_db)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_sl = MagicMock(return_value=mock_cm)

    return (
        patch("app.modules.playback.node.SessionLocal", mock_sl),
        patch("app.modules.playback.node.RecordingRepository", mock_repo_cls),
    )


# ---------------------------------------------------------------------------
# Unit: constructor + speed validation
# ---------------------------------------------------------------------------

class TestPlaybackNodeConstruction:
    """PlaybackNode constructor validates playback_speed strictly."""

    def test_valid_speed_1_0(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0,
        )
        assert node._playback_speed == 1.0

    def test_valid_speed_0_5(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", playback_speed=0.5,
        )
        assert node._playback_speed == 0.5

    def test_valid_speed_0_25(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", playback_speed=0.25,
        )
        assert node._playback_speed == 0.25

    def test_valid_speed_0_1(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", playback_speed=0.1,
        )
        assert node._playback_speed == 0.1

    def test_invalid_speed_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(), node_id="n1", name="T",
                recording_id="rec", playback_speed=0.75,
            )

    def test_speed_greater_than_1_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(), node_id="n1", name="T",
                recording_id="rec", playback_speed=2.0,
            )

    def test_speed_zero_raises_value_error(self):
        from app.modules.playback.node import PlaybackNode
        with pytest.raises(ValueError, match="playback_speed"):
            PlaybackNode(
                manager=_make_mock_manager(), node_id="n1", name="T",
                recording_id="rec", playback_speed=0.0,
            )

    def test_loopable_default_false(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        assert node._loopable is False

    def test_loopable_true(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", loopable=True,
        )
        assert node._loopable is True

    def test_initial_status_is_idle(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        assert node._status == "idle"

    def test_initial_task_is_none(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        assert node._task is None

    def test_id_and_name_set(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="abc-123", name="My Playback",
            recording_id="rec",
        )
        assert node.id == "abc-123"
        assert node.name == "My Playback"

    def test_recording_id_stored(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="my-rec",
        )
        assert node._recording_id == "my-rec"

    def test_throttle_ms_stored(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", throttle_ms=100.0,
        )
        assert node._throttle_ms == 100.0


# ---------------------------------------------------------------------------
# Unit: emit_status
# ---------------------------------------------------------------------------

class TestPlaybackNodeEmitStatus:
    """emit_status() maps _status → OperationalState correctly."""

    def _node(self, **kw):
        from app.modules.playback.node import PlaybackNode
        return PlaybackNode(manager=_make_mock_manager(), node_id="n1", name="T",
                            recording_id="rec", **kw)

    def test_idle_maps_to_stopped(self):
        from app.schemas.status import OperationalState
        node = self._node()
        assert node.emit_status().operational_state == OperationalState.STOPPED

    def test_idle_application_state_value(self):
        node = self._node()
        status = node.emit_status()
        assert status.application_state is not None
        assert status.application_state.value == "idle"

    def test_playing_maps_to_running(self):
        from app.schemas.status import OperationalState
        node = self._node()
        node._status = "playing"
        node._current_frame = 5
        node._total_frames = 10
        assert node.emit_status().operational_state == OperationalState.RUNNING

    def test_playing_application_state_contains_frame_counter(self):
        node = self._node()
        node._status = "playing"
        node._current_frame = 5
        node._total_frames = 10
        val = str(node.emit_status().application_state.value)
        assert "5" in val and "10" in val

    def test_error_maps_to_error_state(self):
        from app.schemas.status import OperationalState
        node = self._node()
        node._status = "error"
        node._error_message = "file not found"
        assert node.emit_status().operational_state == OperationalState.ERROR

    def test_error_message_propagated(self):
        node = self._node()
        node._status = "error"
        node._error_message = "file not found"
        assert node.emit_status().error_message == "file not found"

    def test_status_has_correct_node_id(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="playback-xyz", name="T",
            recording_id="rec",
        )
        assert node.emit_status().node_id == "playback-xyz"


# ---------------------------------------------------------------------------
# Unit: on_input (source node no-op)
# ---------------------------------------------------------------------------

class TestPlaybackNodeOnInput:
    """Source node: on_input must be a no-op."""

    @pytest.mark.asyncio
    async def test_on_input_is_noop(self):
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        await node.on_input({"points": np.zeros((10, 3)), "timestamp": 0.0})
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
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="nonexistent-uuid",
        )
        p_sl, p_repo = _patch_db(None)
        with p_sl, p_repo:
            await node.start()
        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_missing_file_on_disk_sets_error(self, tmp_path: Path):
        """DB record present but file missing → _status = 'error'."""
        from app.modules.playback.node import PlaybackNode
        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        fake_record = {
            "id": "rec",
            "file_path": str(tmp_path / "nonexistent"),
            "frame_count": 5,
            "duration_seconds": 5.0,
        }
        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo:
            await node.start()
        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_zero_frames_sets_error(self, tmp_path: Path):
        """Recording with zero frames → _status = 'error'."""
        from app.modules.playback.node import PlaybackNode

        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("metadata.json", json.dumps({
                "frame_count": 0, "timestamps": [],
                "start_timestamp": 0.0, "end_timestamp": 0.0,
            }))

        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        fake_record = {
            "id": "rec",
            "file_path": str(tmp_path / "empty"),
            "frame_count": 0,
            "duration_seconds": 0.0,
        }
        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo:
            await node.start()
        assert node._status == "error"

    @pytest.mark.asyncio
    async def test_start_valid_recording_spawns_task(self, tmp_path: Path):
        """Valid recording → task is created."""
        from app.modules.playback.node import PlaybackNode

        zip_path = _make_zip_recording(tmp_path, frame_count=2)
        file_path_no_ext = str(zip_path.with_suffix(""))

        node = PlaybackNode(
            manager=_make_mock_manager(), node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0,
        )
        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": 2,
            "duration_seconds": 2.0,
        }
        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo:
            await node.start()

        assert node._task is not None
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
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": 5,
            "duration_seconds": 5.0,
        }
        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo:
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
            manager=_make_mock_manager(), node_id="n1", name="T", recording_id="rec",
        )
        await node.stop()
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
            manager=manager, node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0, loopable=False,
        )
        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": float(frame_count),
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, \
             patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

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
            manager=manager, node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0,
        )
        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": 1,
            "duration_seconds": 1.0,
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, \
             patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        assert manager.forward_data.called
        node_id_arg, payload = manager.forward_data.call_args[0]
        assert node_id_arg == "n1"
        assert "points" in payload
        assert "timestamp" in payload
        assert "node_id" in payload
        assert "metadata" in payload
        meta = payload["metadata"]
        assert meta["source"] == "playback"
        assert meta["recording_id"] == "rec"
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
            manager=manager, node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0, loopable=True,
        )
        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": float(frame_count),
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo:
            with patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
                await node.start()
                # Give thread-pool tasks time to complete
                await asyncio.sleep(0.1)
                await node.stop()

        assert manager.forward_data.call_count >= frame_count


# ---------------------------------------------------------------------------
# Unit: VALID_SPEEDS constant
# ---------------------------------------------------------------------------

class TestValidSpeeds:
    """VALID_SPEEDS must contain exactly the four documented speeds."""

    def test_valid_speeds_set(self):
        from app.modules.playback.node import VALID_SPEEDS
        assert VALID_SPEEDS == frozenset({0.1, 0.25, 0.5, 1.0})

    def test_all_valid_speeds_accepted(self):
        from app.modules.playback.node import PlaybackNode, VALID_SPEEDS
        for speed in VALID_SPEEDS:
            node = PlaybackNode(
                manager=_make_mock_manager(), node_id="n1", name="T",
                recording_id="rec", playback_speed=speed,
            )
            assert node._playback_speed == speed


# ---------------------------------------------------------------------------
# Integration: config update / recording_id change — no duplicate loops
# ---------------------------------------------------------------------------

class TestPlaybackNodeConfigUpdate:
    """Changing recording_id via start() must stop the old loop before spawning a new one."""

    @pytest.mark.asyncio
    async def test_start_while_running_cancels_old_task(self, tmp_path: Path):
        """Calling start() while a loop is running must cancel it first (only 1 task live)."""
        from app.modules.playback.node import PlaybackNode

        dir_a = tmp_path / "recA"
        dir_a.mkdir()
        dir_b = tmp_path / "recB"
        dir_b.mkdir()

        zip_a = _make_zip_recording(dir_a, frame_count=10)
        file_a = str(zip_a.with_suffix(""))

        zip_b = _make_zip_recording(dir_b, frame_count=10)
        file_b = str(zip_b.with_suffix(""))

        manager = _make_mock_manager()
        node = PlaybackNode(
            manager=manager, node_id="n1", name="T",
            recording_id="rec-a", playback_speed=1.0, loopable=True,
        )

        record_a = {"id": "rec-a", "file_path": file_a, "frame_count": 10, "duration_seconds": 10.0}
        record_b = {"id": "rec-b", "file_path": file_b, "frame_count": 10, "duration_seconds": 10.0}

        # Start with recording A
        p_sl, p_repo = _patch_db(record_a)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()

        first_task = node._task
        assert first_task is not None
        assert not first_task.done()

        # Simulate config update: change recording_id and call start() again
        node._recording_id = "rec-b"
        p_sl2, p_repo2 = _patch_db(record_b)
        with p_sl2, p_repo2, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()

        # The old task MUST be cancelled/done
        assert first_task.done(), "Old playback task must be cancelled before new one starts"
        # Only one task is live
        assert node._task is not None
        assert node._task is not first_task, "A new task must replace the old one"

        # Cleanup
        await node.stop()

    @pytest.mark.asyncio
    async def test_only_new_recording_emits_after_config_change(self, tmp_path: Path):
        """After changing recording_id, only frames from the new recording are forwarded."""
        from app.modules.playback.node import PlaybackNode

        frame_count = 2
        zip_a = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_a = str(zip_a.with_suffix(""))

        # Build a second recording in a subdirectory
        sub = tmp_path / "sub"
        sub.mkdir()
        zip_b = _make_zip_recording(sub, frame_count=frame_count)
        file_b = str(zip_b.with_suffix(""))

        manager = _make_mock_manager()
        node = PlaybackNode(
            manager=manager, node_id="n1", name="T",
            recording_id="rec-a", playback_speed=1.0, loopable=False,
        )

        record_a = {"id": "rec-a", "file_path": file_a, "frame_count": frame_count, "duration_seconds": 2.0}
        record_b = {"id": "rec-b", "file_path": file_b, "frame_count": frame_count, "duration_seconds": 2.0}

        sleep_mock = AsyncMock()

        # Start first recording and let it finish
        p_sl, p_repo = _patch_db(record_a)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", sleep_mock):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        calls_after_a = manager.forward_data.call_count
        assert calls_after_a == frame_count

        # Change recording and start again — must NOT double-emit from rec-a
        manager.forward_data.reset_mock()
        node._recording_id = "rec-b"

        p_sl2, p_repo2 = _patch_db(record_b)
        with p_sl2, p_repo2, patch("app.modules.playback.node.asyncio_sleep", sleep_mock):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # Exactly frame_count calls from rec-b only
        assert manager.forward_data.call_count == frame_count
        # All payloads reference rec-b
        for call in manager.forward_data.call_args_list:
            _, payload = call[0]
            assert payload["metadata"]["recording_id"] == "rec-b", (
                f"Expected rec-b but got {payload['metadata']['recording_id']}"
            )

    @pytest.mark.asyncio
    async def test_start_logs_only_one_loop_active(self, tmp_path: Path, caplog):
        """start() must log that it stops the old loop before starting a new one."""
        import logging
        from app.modules.playback.node import PlaybackNode

        zip_path = _make_zip_recording(tmp_path, frame_count=3)
        file_path = str(zip_path.with_suffix(""))
        manager = _make_mock_manager()
        node = PlaybackNode(
            manager=manager, node_id="n1", name="T",
            recording_id="rec", playback_speed=1.0, loopable=True,
        )
        record = {"id": "rec", "file_path": file_path, "frame_count": 3, "duration_seconds": 3.0}

        p_sl, p_repo = _patch_db(record)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()

        first_task = node._task

        with caplog.at_level(logging.INFO, logger="app.modules.playback.node"):
            p_sl2, p_repo2 = _patch_db(record)
            with p_sl2, p_repo2, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
                await node.start()

        assert any("stopping" in r.message.lower() or "cancel" in r.message.lower()
                   for r in caplog.records), (
            "Expected a log message about stopping/cancelling old loop"
        )
        assert first_task.done()
        await node.stop()


# ---------------------------------------------------------------------------
# TDD: Zombie task prevention — DAG reload / selective reload lifecycle
# ---------------------------------------------------------------------------

class TestZombieTaskPrevention:
    """
    After a DAG reload or selective reload:
      - No zombie playback tasks remain for the prior node_id.
      - forward_data must NOT be called when the node_id is no longer registered.
      - Only 1 active task ever emits per node.
    """

    @pytest.mark.asyncio
    async def test_no_zombie_emit_after_node_removed_from_manager(self, tmp_path: Path):
        """
        Simulate what happens when a node is removed from manager.nodes while its
        _run_loop is still executing: it must detect the deregistration and stop emitting.

        Before fix: _run_loop calls manager.forward_data unconditionally, even after
        the node_id has been removed from manager.nodes (zombie emit).
        After fix: each loop iteration checks if self.id is in manager.nodes first;
        if not, it logs a warning and exits cleanly without calling forward_data.
        """
        from app.modules.playback.node import PlaybackNode

        frame_count = 5
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))

        # Manager with a real nodes dict so the guard check works
        mock_manager = _make_mock_manager()
        mock_manager.nodes = {}

        node = PlaybackNode(
            manager=mock_manager, node_id="zombie-node", name="T",
            recording_id="rec", playback_speed=1.0, loopable=True,
        )
        # Register the node in the manager dict (simulating orchestrator registration)
        mock_manager.nodes["zombie-node"] = node

        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": 5.0,
        }

        sleep_call_count = 0
        original_node_ref = node

        async def tracking_sleep(s):
            nonlocal sleep_call_count
            sleep_call_count += 1
            # After 2 frames, simulate DAG reload by removing node from manager
            if sleep_call_count == 2:
                mock_manager.nodes.pop("zombie-node", None)
            await asyncio.sleep(0)

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", tracking_sleep):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # Must have stopped emitting after deregistration — at most 3 calls (2 before removal + maybe 1 more before guard fires)
        assert mock_manager.forward_data.call_count <= 3, (
            f"Zombie task emitted {mock_manager.forward_data.call_count} frames — expected ≤3 after deregistration"
        )

    @pytest.mark.asyncio
    async def test_forward_data_not_called_when_unregistered(self, tmp_path: Path):
        """
        When node_id is removed from manager.nodes BEFORE the loop starts emitting,
        forward_data must NEVER be called.
        """
        from app.modules.playback.node import PlaybackNode

        frame_count = 3
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))

        mock_manager = _make_mock_manager()
        mock_manager.nodes = {}  # node NOT registered → guard should prevent all emits

        node = PlaybackNode(
            manager=mock_manager, node_id="unregistered-node", name="T",
            recording_id="rec", playback_speed=1.0, loopable=False,
        )
        # Deliberately DO NOT register node in mock_manager.nodes

        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": 3.0,
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()
            try:
                await asyncio.wait_for(node._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        assert mock_manager.forward_data.call_count == 0, (
            f"forward_data called {mock_manager.forward_data.call_count} times for unregistered node"
        )

    @pytest.mark.asyncio
    async def test_stop_all_nodes_awaits_async_stop(self, tmp_path: Path):
        """
        LifecycleManager.stop_all_nodes (used during reload) must properly await
        PlaybackNode.stop() — otherwise the task is cancelled asynchronously and
        may still emit frames during the reload window (zombie).

        This test verifies that after stop_all_nodes, no playback task is running.
        """
        from app.modules.playback.node import PlaybackNode
        from app.services.nodes.managers.lifecycle import LifecycleManager

        frame_count = 10
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))

        mock_manager = _make_mock_manager()
        mock_manager.nodes = {}
        mock_manager.data_queue = MagicMock()
        mock_manager.node_runtime_status = {}

        node = PlaybackNode(
            manager=mock_manager, node_id="n-lifecycle", name="T",
            recording_id="rec", playback_speed=1.0, loopable=True,
        )
        mock_manager.nodes["n-lifecycle"] = node

        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": 10.0,
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()

        assert node._task is not None and not node._task.done(), "Task must be running"

        # Simulate what reload_config does: stop_all_nodes → must await stop()
        lifecycle = LifecycleManager(mock_manager)
        await lifecycle.stop_all_nodes_async()

        # After proper async stop, task must be cancelled/done
        assert node._task is None or node._task.done(), (
            "PlaybackNode._task must be done after stop_all_nodes_async()"
        )
        assert node._status == "idle", "Node status must be 'idle' after stop"

    @pytest.mark.asyncio
    async def test_selective_reload_stops_old_task_before_new_starts(self, tmp_path: Path):
        """
        During selective reload (step 7: stop old instance), the old PlaybackNode's
        async stop() must be fully awaited before the new node is inserted into nodes dict.

        Verifies: after reload_single_node(), old_task.done() is True.
        """
        from app.modules.playback.node import PlaybackNode
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        frame_count = 10
        zip_path = _make_zip_recording(tmp_path, frame_count=frame_count)
        file_path_no_ext = str(zip_path.with_suffix(""))

        mock_manager = MagicMock()
        mock_manager.nodes = {}
        mock_manager.downstream_map = {}
        mock_manager._input_gates = {}
        mock_manager._rollback_slot = {}
        mock_manager.edges_data = []
        mock_manager.data_queue = MagicMock()
        mock_manager.node_runtime_status = {}
        mock_manager.is_running = True

        node = PlaybackNode(
            manager=mock_manager, node_id="sel-node", name="T",
            recording_id="rec", playback_speed=1.0, loopable=True,
        )
        # Wire forward_data to be async
        async def fake_forward(node_id, payload, **kw):
            pass
        mock_manager.forward_data = AsyncMock(side_effect=fake_forward)
        mock_manager.nodes["sel-node"] = node

        fake_record = {
            "id": "rec",
            "file_path": file_path_no_ext,
            "frame_count": frame_count,
            "duration_seconds": 10.0,
        }

        p_sl, p_repo = _patch_db(fake_record)
        with p_sl, p_repo, patch("app.modules.playback.node.asyncio_sleep", new_callable=AsyncMock):
            await node.start()

        old_task = node._task
        assert old_task is not None and not old_task.done()

        # Now simulate what SelectiveReloadManager.reload_single_node does at step 7
        # We call _stop_node_async directly (which should await stop())
        from app.services.nodes.managers.lifecycle import LifecycleManager
        lifecycle = LifecycleManager(mock_manager)
        await lifecycle._stop_node_async(node)

        assert old_task.done(), (
            "Old PlaybackNode task must be cancelled/done after _stop_node_async()"
        )
        assert node._status == "idle"
