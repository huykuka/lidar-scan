"""
Unit tests for ResultStorageNode.

Covers:
  - Instantiation and config storage
  - on_input with single PCD (payload["points"])
  - on_input with multi PCD (payload["pcds"])
  - on_input with no PCD data (skip)
  - on_input when results_service is None (error)
  - _extract_pcds: multi-PCD, single-PCD, empty
  - _extract_metadata: dict metadata, scalar fallback
  - emit_status: idle, after save, after error
  - _build_o3d_pcds: labels → coloured PointCloud objects, color_map overrides
"""
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.modules.flow_control.result_storage.node import ResultStorageNode
from app.schemas.status import OperationalState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "color_map": {},
}


def _make_node(
    config: Dict[str, Any] | None = None,
    results_service: Any = None,
    node_id: str = "rs-001",
) -> tuple[ResultStorageNode, MagicMock]:
    manager = MagicMock()
    manager.forward_data = AsyncMock()
    cfg = config if config is not None else DEFAULT_CONFIG.copy()
    node = ResultStorageNode(
        manager=manager,
        node_id=node_id,
        name="Test Result Storage",
        config=cfg,
        results_service=results_service,
    )
    return node, manager


def _random_pts(n: int = 100, dims: int = 3) -> np.ndarray:
    return np.random.default_rng(42).uniform(-1, 1, (n, dims)).astype(np.float64)


# ─────────────────────────────────────────────────────────────────────────────
# TestInit
# ─────────────────────────────────────────────────────────────────────────────

class TestResultStorageNodeInit:
    def test_id_set_correctly(self):
        node, _ = _make_node(node_id="my-rs")
        assert node.id == "my-rs"

    def test_empty_color_map_default(self):
        node, _ = _make_node()
        assert node._color_map == {}

    def test_custom_color_map(self):
        cmap = {"empty": "#FF0000", "loaded": "#00FF00"}
        node, _ = _make_node(config={"color_map": cmap})
        assert node._color_map == cmap

    def test_color_map_non_dict_defaults_empty(self):
        node, _ = _make_node(config={"color_map": "not-a-dict"})
        assert node._color_map == {}

    def test_color_map_missing_defaults_empty(self):
        node, _ = _make_node(config={})
        assert node._color_map == {}

    def test_initial_stats(self):
        node, _ = _make_node()
        assert node.last_input_at is None
        assert node.last_save_at is None
        assert node.last_error is None
        assert node._save_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestExtractPcds
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractPcds:
    def test_multi_pcd(self):
        pts_a = _random_pts(50)
        pts_b = _random_pts(30)
        payload = {"pcds": {"empty": pts_a, "loaded": pts_b}}
        result = ResultStorageNode._extract_pcds(payload)
        assert set(result.keys()) == {"empty", "loaded"}
        assert result["empty"].shape == (50, 3)
        assert result["loaded"].shape == (30, 3)

    def test_single_pcd_fallback(self):
        pts = _random_pts(40)
        payload = {"points": pts}
        result = ResultStorageNode._extract_pcds(payload)
        assert set(result.keys()) == {"result"}
        assert result["result"].shape == (40, 3)

    def test_empty_payload_returns_empty(self):
        result = ResultStorageNode._extract_pcds({})
        assert result == {}

    def test_empty_points_returns_empty(self):
        result = ResultStorageNode._extract_pcds({"points": np.array([])})
        assert result == {}

    def test_pcds_with_none_values_filtered(self):
        pts = _random_pts(20)
        payload = {"pcds": {"good": pts, "bad": None}}
        result = ResultStorageNode._extract_pcds(payload)
        assert set(result.keys()) == {"good"}

    def test_pcds_with_empty_arrays_filtered(self):
        pts = _random_pts(20)
        payload = {"pcds": {"good": pts, "empty_arr": np.array([])}}
        result = ResultStorageNode._extract_pcds(payload)
        assert set(result.keys()) == {"good"}

    def test_multi_pcd_takes_precedence_over_points(self):
        payload = {
            "pcds": {"label_a": _random_pts(10)},
            "points": _random_pts(20),
        }
        result = ResultStorageNode._extract_pcds(payload)
        assert "label_a" in result
        assert "result" not in result


# ─────────────────────────────────────────────────────────────────────────────
# TestExtractMetadata
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractMetadata:
    def test_dict_metadata(self):
        payload = {"metadata": {"volume_m3": 1.5, "icp_valid": True}}
        result = ResultStorageNode._extract_metadata(payload)
        assert result == {"volume_m3": 1.5, "icp_valid": True}

    def test_dict_metadata_is_copy(self):
        meta = {"key": "val"}
        payload = {"metadata": meta}
        result = ResultStorageNode._extract_metadata(payload)
        assert result is not meta
        assert result == meta

    def test_scalar_fallback(self):
        payload = {
            "node_id": "n1",
            "timestamp": 1.0,
            "points": _random_pts(5),
            "volume_m3": 2.5,
            "icp_valid": True,
        }
        result = ResultStorageNode._extract_metadata(payload)
        assert "volume_m3" in result
        assert "icp_valid" in result
        assert "node_id" not in result
        assert "points" not in result

    def test_empty_payload(self):
        result = ResultStorageNode._extract_metadata({})
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# TestBuildO3dPcds
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildO3dPcds:
    def test_single_label(self):
        pcds = {"result": _random_pts(10)}
        result = ResultStorageNode._build_o3d_pcds(pcds)
        assert len(result) == 1
        label, pcd = result[0]
        assert label == "result"
        assert len(pcd.points) == 10
        assert len(pcd.colors) == 10

    def test_multi_label(self):
        pcds = {"empty": _random_pts(5), "loaded": _random_pts(8)}
        result = ResultStorageNode._build_o3d_pcds(pcds)
        assert len(result) == 2
        labels = {r[0] for r in result}
        assert labels == {"empty", "loaded"}

    def test_default_colors_applied(self):
        pcds = {"empty": _random_pts(3)}
        result = ResultStorageNode._build_o3d_pcds(pcds)
        _, pcd = result[0]
        colors = np.asarray(pcd.colors)
        assert colors.shape == (3, 3)
        # "empty" should get blue (#2196F3)
        expected_r = 0x21 / 255.0
        assert abs(colors[0, 0] - expected_r) < 0.01

    def test_color_map_overrides_default(self):
        pcds = {"empty": _random_pts(3)}
        result = ResultStorageNode._build_o3d_pcds(pcds, color_map={"empty": "#FF0000"})
        _, pcd = result[0]
        colors = np.asarray(pcd.colors)
        # Should be red (#FF0000)
        assert abs(colors[0, 0] - 1.0) < 0.01
        assert abs(colors[0, 1] - 0.0) < 0.01
        assert abs(colors[0, 2] - 0.0) < 0.01

    def test_color_map_partial_override(self):
        pcds = {"empty": _random_pts(3), "loaded": _random_pts(3)}
        result = ResultStorageNode._build_o3d_pcds(pcds, color_map={"empty": "#00FF00"})
        result_dict = {r[0]: r[1] for r in result}

        # "empty" overridden to green
        empty_colors = np.asarray(result_dict["empty"].colors)
        assert abs(empty_colors[0, 1] - 1.0) < 0.01

        # "loaded" uses default red (#F44336)
        loaded_colors = np.asarray(result_dict["loaded"].colors)
        expected_r = 0xF4 / 255.0
        assert abs(loaded_colors[0, 0] - expected_r) < 0.01

    def test_color_map_unknown_label_uses_default(self):
        pcds = {"mystery": _random_pts(3)}
        result = ResultStorageNode._build_o3d_pcds(pcds, color_map={})
        _, pcd = result[0]
        colors = np.asarray(pcd.colors)
        # Unknown label gets grey (#9E9E9E)
        expected_r = 0x9E / 255.0
        assert abs(colors[0, 0] - expected_r) < 0.01

    def test_empty_color_map_same_as_none(self):
        pcds = {"empty": _random_pts(3)}
        result_none = ResultStorageNode._build_o3d_pcds(pcds, color_map=None)
        result_empty = ResultStorageNode._build_o3d_pcds(pcds, color_map={})
        colors_none = np.asarray(result_none[0][1].colors)
        colors_empty = np.asarray(result_empty[0][1].colors)
        np.testing.assert_array_equal(colors_none, colors_empty)


# ─────────────────────────────────────────────────────────────────────────────
# TestOnInput
# ─────────────────────────────────────────────────────────────────────────────

class TestOnInput:
    @pytest.mark.asyncio
    async def test_no_service_sets_error(self):
        node, _ = _make_node(results_service=None)
        await node.on_input({"points": _random_pts(10)})
        assert node.last_error == "Results service unavailable"

    @pytest.mark.asyncio
    async def test_empty_payload_skips(self):
        svc = AsyncMock()
        node, _ = _make_node(results_service=svc)
        await node.on_input({})
        svc.save_result.assert_not_called()
        assert node._save_count == 0

    @pytest.mark.asyncio
    async def test_single_pcd_saves(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(return_value="result-001")
        node, _ = _make_node(results_service=svc)

        pts = _random_pts(20)
        await node.on_input({"points": pts, "metadata": {"key": "val"}})

        svc.save_result.assert_called_once()
        call_kwargs = svc.save_result.call_args[1]
        assert call_kwargs["node_id"] == "rs-001"
        assert call_kwargs["status"] == "success"
        assert len(call_kwargs["pcds"]) == 1
        assert call_kwargs["pcds"][0][0] == "result"
        assert node._save_count == 1
        assert node.last_error is None

    @pytest.mark.asyncio
    async def test_multi_pcd_saves(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(return_value="result-002")
        node, _ = _make_node(results_service=svc)

        await node.on_input({
            "pcds": {"empty": _random_pts(15), "loaded": _random_pts(25)},
            "metadata": {"volume_m3": 1.2},
        })

        svc.save_result.assert_called_once()
        call_kwargs = svc.save_result.call_args[1]
        assert len(call_kwargs["pcds"]) == 2
        labels = {p[0] for p in call_kwargs["pcds"]}
        assert labels == {"empty", "loaded"}

    @pytest.mark.asyncio
    async def test_save_error_sets_last_error(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(side_effect=RuntimeError("disk full"))
        node, _ = _make_node(results_service=svc)

        await node.on_input({"points": _random_pts(5)})
        assert node.last_error == "disk full"
        assert node._save_count == 0

    @pytest.mark.asyncio
    async def test_always_saves_with_success_status(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(return_value="r-003")
        node, _ = _make_node(results_service=svc)

        await node.on_input({
            "points": _random_pts(5),
            "metadata": {"icp_valid": False},
        })

        call_kwargs = svc.save_result.call_args[1]
        assert call_kwargs["status"] == "success"

    @pytest.mark.asyncio
    async def test_color_map_passed_to_build(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(return_value="r-004")
        cmap = {"result": "#FF0000"}
        node, _ = _make_node(config={"color_map": cmap}, results_service=svc)

        await node.on_input({"points": _random_pts(5)})

        svc.save_result.assert_called_once()
        call_kwargs = svc.save_result.call_args[1]
        _, pcd = call_kwargs["pcds"][0]
        colors = np.asarray(pcd.colors)
        # Red from color_map
        assert abs(colors[0, 0] - 1.0) < 0.01
        assert abs(colors[0, 1] - 0.0) < 0.01

    @pytest.mark.asyncio
    async def test_all_metadata_stored(self):
        svc = AsyncMock()
        svc.save_result = AsyncMock(return_value="r-005")
        node, _ = _make_node(results_service=svc)

        meta = {"volume_m3": 1.5, "icp_valid": True, "confidence": 0.95}
        await node.on_input({"points": _random_pts(5), "metadata": meta})

        call_kwargs = svc.save_result.call_args[1]
        assert call_kwargs["metadata"] == meta


# ─────────────────────────────────────────────────────────────────────────────
# TestEmitStatus
# ─────────────────────────────────────────────────────────────────────────────

class TestEmitStatus:
    def test_initial_running(self):
        node, _ = _make_node()
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is None

    def test_error_state(self):
        node, _ = _make_node()
        node.last_error = "something broke"
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR
        assert status.error_message == "something broke"

    def test_after_save(self):
        node, _ = _make_node()
        node._save_count = 3
        node.last_save_at = time.time()
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state is not None
        assert status.application_state.value == 3
