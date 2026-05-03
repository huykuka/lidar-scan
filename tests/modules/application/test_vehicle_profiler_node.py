"""
Unit tests for VehicleProfilerNode.

Covers:
  - Instantiation and config storage
  - on_input dispatch (velocity vs profile sensors)
  - State machine transitions (IDLE -> MEASURING -> IDLE)
  - _processing concurrency guard
  - emit_status in various states
  - start / stop lifecycle
  - Profile output forwarded via manager.forward_data
"""
import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.modules.application.vehicle_profiler.node import VehicleProfilerNode, _State
from app.schemas.status import OperationalState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "bg_threshold": 0.3,
    "bg_learning_frames": 3,
    "travel_axis": 0,
    "min_scan_lines": 2,
}

VELOCITY_SENSOR = "vel-001"


def _bg_scan(n: int = 50, distance: float = 5.0) -> np.ndarray:
    angles = np.linspace(-np.pi / 4, np.pi / 4, n)
    return np.column_stack([distance * np.cos(angles), distance * np.sin(angles)])


def _vehicle_scan(n: int = 50, bg: float = 5.0, veh: float = 1.5) -> np.ndarray:
    angles = np.linspace(-np.pi / 4, np.pi / 4, n)
    distances = np.full(n, bg)
    distances[15:35] = veh
    return np.column_stack([distances * np.cos(angles), distances * np.sin(angles)])


def _side_scan(n: int = 20) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(-1, 1, (n, 2)).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager() -> MagicMock:
    m = MagicMock()
    m.forward_data = AsyncMock()
    return m


@pytest.fixture
def node(mock_manager: MagicMock) -> VehicleProfilerNode:
    return VehicleProfilerNode(
        manager=mock_manager,
        node_id="vp-001",
        name="Test Profiler",
        velocity_sensor_id=VELOCITY_SENSOR,
        config=DEFAULT_CONFIG.copy(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TestInstantiation
# ─────────────────────────────────────────────────────────────────────────────


class TestInstantiation:
    def test_id(self, node):
        assert node.id == "vp-001"

    def test_name(self, node):
        assert node.name == "Test Profiler"

    def test_initial_state_idle(self, node):
        assert node._state == _State.IDLE

    def test_processing_guard_initially_false(self, node):
        assert node._velocity_processing is False
        assert node._profile_processing is False

    def test_velocity_sensor_id_stored(self, node):
        assert node._velocity_sensor_id == VELOCITY_SENSOR


# ─────────────────────────────────────────────────────────────────────────────
# TestOnInput
# ─────────────────────────────────────────────────────────────────────────────


class TestOnInput:
    @pytest.mark.asyncio
    async def test_ignores_payload_without_source_id(self, node):
        await node.on_input({"points": _bg_scan(), "timestamp": 0.0})
        assert node.last_input_at is None

    @pytest.mark.asyncio
    async def test_ignores_empty_points(self, node):
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": np.empty((0, 2)), "timestamp": 0.0})
        assert node.last_input_at is None

    @pytest.mark.asyncio
    async def test_ignores_none_points(self, node):
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": None, "timestamp": 0.0})
        assert node.last_input_at is None

    @pytest.mark.asyncio
    async def test_velocity_frame_dispatched(self, node):
        with patch.object(node, "_handle_velocity_frame", new_callable=AsyncMock) as mock:
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": 0.0})
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_profile_frame_dispatched(self, node):
        with patch.object(node, "_handle_profile_frame", new_callable=AsyncMock) as mock:
            await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 0.0})
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_processing_guard_drops_concurrent_velocity_frame(self, node):
        node._velocity_processing = True
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": 0.0})
        # Frame was received (last_input_at set) but handler was skipped
        assert node._state == _State.IDLE

    @pytest.mark.asyncio
    async def test_processing_guard_drops_concurrent_profile_frame(self, node):
        node._profile_processing = True
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 0.0})
        assert node._state == _State.IDLE


# ─────────────────────────────────────────────────────────────────────────────
# TestStateMachine
# ─────────────────────────────────────────────────────────────────────────────


class TestStateMachine:
    @pytest.mark.asyncio
    async def test_idle_to_measuring_on_vehicle_detection(self, node):
        # Learn background
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        assert node._state == _State.IDLE

        # Vehicle detected
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        assert node._state == _State.MEASURING

    @pytest.mark.asyncio
    async def test_measuring_to_idle_on_vehicle_departure(self, node, mock_manager):
        # Learn background + detect vehicle
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        assert node._state == _State.MEASURING

        # Add enough side scans to meet min_scan_lines=2
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.1})
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.2})

        # Vehicle leaves
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": 4.0})
        assert node._state == _State.IDLE

    @pytest.mark.asyncio
    async def test_profile_frames_ignored_when_idle(self, node):
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 0.0})
        # No crash, no state change
        assert node._state == _State.IDLE


# ─────────────────────────────────────────────────────────────────────────────
# TestEmitStatus
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatus:
    def test_idle_status(self, node):
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.value == "idle"
        assert status.application_state.color == "gray"

    def test_measuring_status(self, node):
        node._state = _State.MEASURING
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.value == "measuring"
        assert status.application_state.color == "blue"

    def test_error_status(self, node):
        node.last_error = "something broke"
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR
        assert status.error_message == "something broke"
        assert status.application_state.color == "red"


# ─────────────────────────────────────────────────────────────────────────────
# TestStop
# ─────────────────────────────────────────────────────────────────────────────


class TestVelocityFilter:
    @pytest.mark.asyncio
    async def test_zero_velocity_accepted_with_default_min(self, mock_manager):
        """With min_velocity=0.0 (default), zero-velocity scans pass through (< not <=)."""
        config = DEFAULT_CONFIG.copy()
        config["min_velocity"] = 0.0
        node = VehicleProfilerNode(
            manager=mock_manager, node_id="vp-001", name="Test",
            velocity_sensor_id=VELOCITY_SENSOR, config=config,
        )
        # Learn background
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        # Detect vehicle
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        assert node._state == _State.MEASURING
        # Velocity is zero on first detection — accepted because 0.0 is NOT < 0.0
        assert node._detector.current_velocity == pytest.approx(0.0, abs=0.01)
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.0})
        assert node._profiler.scan_count == 1

    @pytest.mark.asyncio
    async def test_zero_velocity_rejected_with_positive_min(self, mock_manager):
        """With min_velocity > 0, zero-velocity scans are rejected."""
        config = DEFAULT_CONFIG.copy()
        config["min_velocity"] = 0.1
        node = VehicleProfilerNode(
            manager=mock_manager, node_id="vp-001", name="Test",
            velocity_sensor_id=VELOCITY_SENSOR, config=config,
        )
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        assert node._state == _State.MEASURING
        assert node._detector.current_velocity == pytest.approx(0.0, abs=0.01)
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.0})
        assert node._profiler.scan_count == 0

    @pytest.mark.asyncio
    async def test_profile_accepted_when_velocity_positive(self, mock_manager):
        """Scan lines should be accepted once velocity becomes positive."""
        config = DEFAULT_CONFIG.copy()
        config["min_velocity"] = 0.0
        node = VehicleProfilerNode(
            manager=mock_manager, node_id="vp-001", name="Test",
            velocity_sensor_id=VELOCITY_SENSOR, config=config,
        )
        # Learn background
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        # Detect vehicle — first frame at one position
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        assert node._state == _State.MEASURING
        # Move vehicle forward (closer beams shift along travel axis)
        veh2 = _vehicle_scan()
        veh2[:, 0] += 0.5  # shift along X (travel_axis=0)
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": veh2, "timestamp": 3.5})
        # Velocity should now be positive
        assert node._detector.current_velocity > 0
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.5})
        assert node._profiler.scan_count >= 1

    @pytest.mark.asyncio
    async def test_min_velocity_threshold(self, mock_manager):
        """Higher min_velocity rejects slow-moving vehicles."""
        config = DEFAULT_CONFIG.copy()
        config["min_velocity"] = 5.0  # very high threshold
        node = VehicleProfilerNode(
            manager=mock_manager, node_id="vp-001", name="Test",
            velocity_sensor_id=VELOCITY_SENSOR, config=config,
        )
        # Learn background
        for i in range(3):
            await node.on_input({"node_id": VELOCITY_SENSOR, "points": _bg_scan(), "timestamp": float(i)})
        # Detect vehicle
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": _vehicle_scan(), "timestamp": 3.0})
        veh2 = _vehicle_scan()
        veh2[:, 0] += 0.5
        await node.on_input({"node_id": VELOCITY_SENSOR, "points": veh2, "timestamp": 3.5})
        # Velocity is positive but below 5.0 m/s — should be rejected
        assert node._detector.current_velocity < 5.0
        await node.on_input({"node_id": "side-001", "points": _side_scan(), "timestamp": 3.5})
        assert node._profiler.scan_count == 0


class TestStop:
    def test_stop_transitions_to_idle(self, node):
        node._state = _State.MEASURING
        node.stop()
        assert node._state == _State.IDLE
