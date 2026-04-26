"""Unit tests for DetectionNode."""
import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.modules.detection.models.base import (
    Detection3D,
    DetectionModel,
    MODEL_REGISTRY,
    register_model,
)
from app.modules.detection.node import DetectionNode


# ── Fake model for testing (no torch dependency) ──────────────────────────

@register_model("test_fake", display_name="Fake (Test)")
class _FakeModel(DetectionModel):
    """Always returns two fixed detections."""

    _loaded = False

    def load(self, checkpoint_path: str, device: str = "cpu") -> None:
        self._loaded = True

    def detect(self, points: np.ndarray, **kwargs: Any) -> List[Detection3D]:
        if not self._loaded:
            raise RuntimeError("Not loaded")
        return [
            Detection3D(
                center=[1.0, 2.0, 0.5],
                size=[4.0, 2.0, 1.5],
                label="Car",
                score=0.95,
            ),
            Detection3D(
                center=[5.0, -3.0, 0.8],
                size=[0.6, 0.8, 1.7],
                label="Pedestrian",
                score=0.72,
            ),
        ]

    @property
    def supported_classes(self) -> List[str]:
        return ["Car", "Pedestrian"]

    @property
    def is_loaded(self) -> bool:
        return self._loaded


def _make_node(config_overrides: Dict[str, Any] | None = None) -> DetectionNode:
    """Create a DetectionNode with a mock manager and fake model config."""
    manager = MagicMock()
    manager.forward_data = AsyncMock()

    config = {
        "model": "test_fake",
        "checkpoint": "/fake/weights.pth",
        "device": "cpu",
        "confidence_threshold": 0.3,
    }
    if config_overrides:
        config.update(config_overrides)

    node = DetectionNode(
        manager=manager,
        node_id="det_test_01",
        name="Test Detection",
        config=config,
    )
    return node


class TestDetectionNodeInit:
    def test_default_state(self):
        node = _make_node()
        assert node.id == "det_test_01"
        assert node._model_name == "test_fake"
        assert node._model_loaded is False
        assert node.detection_count == 0

    def test_start_loads_model(self):
        node = _make_node()
        node.start()
        assert node._model_loaded is True
        assert node._model is not None
        assert node.last_error is None

    def test_start_with_missing_model(self):
        node = _make_node({"model": "nonexistent_model_xyz"})
        node.start()
        assert node._model_loaded is False
        assert "Unknown model" in node.last_error

    def test_start_without_checkpoint(self):
        node = _make_node({"checkpoint": ""})
        node.start()
        assert node._model_loaded is False
        assert "No checkpoint" in node.last_error

    def test_stop_clears_model(self):
        node = _make_node()
        node.start()
        node.stop()
        assert node._model is None
        assert node._model_loaded is False


class TestDetectionNodeInference:
    @pytest.mark.asyncio
    async def test_on_input_produces_detections(self):
        node = _make_node()
        node.start()

        points = np.random.rand(1000, 14).astype(np.float32)
        payload = {"points": points, "timestamp": 1.0, "node_id": "upstream"}

        await node.on_input(payload)

        assert node.detection_count == 2
        assert node.processing_time_ms > 0
        assert node.last_error is None

        # Verify shapes were emitted
        shapes = node.collect_and_clear_shapes()
        assert len(shapes) == 2
        assert shapes[0].label == "Car 95%"

    @pytest.mark.asyncio
    async def test_on_input_forwards_downstream(self):
        node = _make_node()
        node.start()

        points = np.random.rand(100, 14).astype(np.float32)
        await node.on_input({"points": points})

        # Wait briefly for the fire-and-forget task
        await asyncio.sleep(0.05)

        node.manager.forward_data.assert_called_once()
        call_args = node.manager.forward_data.call_args
        forwarded_payload = call_args[0][1]
        assert forwarded_payload["detection_count"] == 2
        assert len(forwarded_payload["detections"]) == 2
        assert forwarded_payload["detections"][0]["label"] == "Car"

    @pytest.mark.asyncio
    async def test_on_input_empty_points_skips(self):
        node = _make_node()
        node.start()

        await node.on_input({"points": np.zeros((0, 14), dtype=np.float32)})

        assert node.detection_count == 0
        node.manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_input_none_points_skips(self):
        node = _make_node()
        node.start()

        await node.on_input({"timestamp": 1.0})

        assert node.detection_count == 0
        node.manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_input_skips_when_not_loaded(self):
        node = _make_node()
        # Do NOT call start() — model not loaded

        points = np.random.rand(100, 14).astype(np.float32)
        await node.on_input({"points": points})

        assert node.detection_count == 0
        node.manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_detections_cap(self):
        # Register a model that returns many detections
        @register_model("test_many", display_name="Many (Test)")
        class _ManyModel(DetectionModel):
            _loaded = False

            def load(self, checkpoint_path, device="cpu"):
                self._loaded = True

            def detect(self, points, **kwargs):
                return [
                    Detection3D(center=[i, 0, 0], size=[1, 1, 1], label="Car", score=0.9 - i * 0.01)
                    for i in range(100)
                ]

            @property
            def supported_classes(self):
                return ["Car"]

            @property
            def is_loaded(self):
                return self._loaded

        node = _make_node({"model": "test_many", "max_detections": 5})
        node.start()

        points = np.random.rand(100, 14).astype(np.float32)
        await node.on_input({"points": points})

        assert node.detection_count == 5

        # Clean up
        del MODEL_REGISTRY["test_many"]


class TestDetectionNodeStatus:
    def test_status_error(self):
        node = _make_node({"model": "nonexistent_xyz"})
        node.start()

        status = node.emit_status()
        assert status.operational_state == "ERROR"
        assert "Unknown model" in status.error_message

    def test_status_not_loaded(self):
        node = _make_node()
        status = node.emit_status()
        assert status.operational_state == "STOPPED"

    def test_status_running(self):
        node = _make_node()
        node.start()
        status = node.emit_status()
        assert status.operational_state == "RUNNING"
        assert status.application_state.label == "model"

    @pytest.mark.asyncio
    async def test_status_with_detections(self):
        node = _make_node()
        node.start()
        points = np.random.rand(100, 14).astype(np.float32)
        await node.on_input({"points": points})

        status = node.emit_status()
        assert status.operational_state == "RUNNING"
        assert status.application_state.label == "detections"
        assert status.application_state.value == 2
