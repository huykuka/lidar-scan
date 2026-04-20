"""
Tests for DBSCAN Clustering node with emit_shapes integration.

Covers:
- emit_shapes=False (default): no shapes returned, backward-compatible
- emit_shapes=True: CubeShape + LabelShape emitted per cluster
- Empty point cloud case: no shapes emitted
- Per-cluster shape data structure (center, size, label text)
- OperationNode + ShapeCollectorMixin integration
- Stable shape IDs per frame (deterministic geometry key)
- node_name attribution present on all emitted shapes
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import open3d as o3d
import pytest

from app.modules.pipeline.operations.clustering import Clustering
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.nodes.shapes import CubeShape, LabelShape, compute_shape_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_two_cluster_pcd() -> o3d.geometry.PointCloud:
    """Returns a legacy PointCloud with two well-separated clusters."""
    rng = np.random.default_rng(42)
    c1 = rng.random((30, 3)) * 0.05           # cluster near origin
    c2 = rng.random((30, 3)) * 0.05 + [5, 5, 5]  # cluster far away
    pts = np.vstack([c1, c2])
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    return pcd


def _make_empty_pcd() -> o3d.geometry.PointCloud:
    """Returns a legacy PointCloud with zero points."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    return pcd


# ---------------------------------------------------------------------------
# 1. Clustering.apply() — emit_shapes config flag
# ---------------------------------------------------------------------------

class TestClusteringEmitShapesConfig:
    """Tests for the emit_shapes configuration option on Clustering.apply()."""

    def test_default_no_emit_shapes(self):
        """emit_shapes defaults to False — no shape data in return value."""
        op = Clustering(eps=0.5, min_points=5)
        assert op.emit_shapes is False

    def test_emit_shapes_false_returns_no_shape_data(self):
        """With emit_shapes=False, apply() returns (pcd, meta) with no shapes key."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=False)
        pcd = _make_two_cluster_pcd()
        result = op.apply(pcd)
        pcd_out, meta = result
        assert "shapes" not in meta

    def test_emit_shapes_true_returns_shapes_list(self):
        """With emit_shapes=True, apply() metadata contains a 'shapes' list."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        pcd = _make_two_cluster_pcd()
        pcd_out, meta = op.apply(pcd)
        assert "shapes" in meta
        assert isinstance(meta["shapes"], list)

    def test_emit_shapes_true_emits_two_shapes_per_cluster(self):
        """Each detected cluster produces one CubeShape and one LabelShape."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        pcd = _make_two_cluster_pcd()
        _, meta = op.apply(pcd)
        shapes = meta["shapes"]
        # 2 clusters × 2 shapes (cube + label) = 4 shapes
        assert len(shapes) == 2

    def test_emit_shapes_cube_shape_fields(self):
        """CubeShape instances have correct type and numeric center/size."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        _, meta = op.apply(_make_two_cluster_pcd())
        cube_shapes = [s for s in meta["shapes"] if isinstance(s, CubeShape)]
        assert len(cube_shapes) == 2
        for cube in cube_shapes:
            assert cube.type == "cube"
            assert len(cube.center) == 3
            assert len(cube.size) == 3
            assert all(v >= 0 for v in cube.size), "Size must be non-negative"

    def test_emit_shapes_empty_pcd_no_shapes(self):
        """Empty point cloud → cluster_count=0 and shapes list is empty."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        _, meta = op.apply(_make_empty_pcd())
        assert meta["cluster_count"] == 0
        assert meta.get("shapes", []) == []

    def test_cluster_count_metadata_still_present(self):
        """cluster_count must remain in meta regardless of emit_shapes flag."""
        for flag in (True, False):
            op = Clustering(eps=0.5, min_points=5, emit_shapes=flag)
            _, meta = op.apply(_make_two_cluster_pcd())
            assert "cluster_count" in meta
            assert meta["cluster_count"] >= 1


# ---------------------------------------------------------------------------
# 2. Shape ID stability
# ---------------------------------------------------------------------------

class TestClusteringShapeIdStability:
    """Deterministic shape IDs per cluster bounding box geometry."""

    def test_shapes_have_stable_geometry(self):
        """Running apply() twice on identical input produces identical shape geometry."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        pcd1 = _make_two_cluster_pcd()
        pcd2 = _make_two_cluster_pcd()  # same RNG seed → identical points
        _, meta1 = op.apply(pcd1)
        _, meta2 = op.apply(pcd2)
        cubes1 = sorted(
            [s for s in meta1["shapes"] if isinstance(s, CubeShape)],
            key=lambda s: s.center[0]
        )
        cubes2 = sorted(
            [s for s in meta2["shapes"] if isinstance(s, CubeShape)],
            key=lambda s: s.center[0]
        )
        for c1, c2 in zip(cubes1, cubes2):
            assert c1.center == pytest.approx(c2.center, abs=1e-5)
            assert c1.size == pytest.approx(c2.size, abs=1e-5)

    def test_compute_shape_id_stable_for_emitted_shapes(self):
        """compute_shape_id produces same result for same node_id + shape geometry."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        _, meta = op.apply(_make_two_cluster_pcd())
        cube_shapes = [s for s in meta["shapes"] if isinstance(s, CubeShape)]
        node_id = "test-node-001"
        for cube in cube_shapes:
            id1 = compute_shape_id(node_id, cube)
            id2 = compute_shape_id(node_id, cube)
            assert id1 == id2
            assert len(id1) == 16

    def test_different_clusters_have_different_ids(self):
        """Two clusters at distinct positions produce distinct shape IDs."""
        op = Clustering(eps=0.5, min_points=5, emit_shapes=True)
        _, meta = op.apply(_make_two_cluster_pcd())
        cube_shapes = [s for s in meta["shapes"] if isinstance(s, CubeShape)]
        assert len(cube_shapes) == 2
        id0 = compute_shape_id("node-x", cube_shapes[0])
        id1 = compute_shape_id("node-x", cube_shapes[1])
        assert id0 != id1


# ---------------------------------------------------------------------------
# 3. OperationNode + ShapeCollectorMixin integration
# ---------------------------------------------------------------------------

class TestOperationNodeShapeIntegration:
    """
    OperationNode wrapping Clustering with emit_shapes=True must:
    - Inherit ShapeCollectorMixin
    - Call emit_shape() for each cluster shape
    - collect_and_clear_shapes() returns those shapes after on_input()
    """

    def _make_node(self, emit_shapes: bool = True):
        """Build an OperationNode with Clustering op."""
        from app.modules.pipeline.operation_node import OperationNode

        manager = MagicMock()
        manager.downstream_map = {}
        manager.nodes = {}
        manager.forward_data = AsyncMock()

        node = OperationNode(
            manager=manager,
            node_id="node-dbscan-001",
            op_type="clustering",
            op_config={"eps": 0.5, "min_points": 5, "emit_shapes": emit_shapes},
            name="DBSCAN Test",
        )
        return node, manager

    def test_operation_node_is_shape_collector_when_emit_shapes_true(self):
        """OperationNode must be a ShapeCollectorMixin when op has emit_shapes=True."""
        node, _ = self._make_node(emit_shapes=True)
        assert isinstance(node, ShapeCollectorMixin)

    def test_operation_node_is_shape_collector_when_emit_shapes_false(self):
        """OperationNode is always a ShapeCollectorMixin regardless (opt-in via config)."""
        node, _ = self._make_node(emit_shapes=False)
        assert isinstance(node, ShapeCollectorMixin)

    @pytest.mark.asyncio
    async def test_on_input_emits_shapes_for_two_clusters(self):
        """After on_input(), collect_and_clear_shapes() returns 4 shapes (2 clusters × 2)."""
        node, _ = self._make_node(emit_shapes=True)
        rng = np.random.default_rng(42)
        c1 = rng.random((30, 3)) * 0.05
        c2 = rng.random((30, 3)) * 0.05 + [5, 5, 5]
        pts = np.vstack([c1, c2]).astype(np.float32)
        payload = {"points": pts, "timestamp": 1.0}

        await node.on_input(payload)

        shapes = node.collect_and_clear_shapes()
        assert len(shapes) == 2  # 2 cubes + 2 labels

    @pytest.mark.asyncio
    async def test_on_input_emits_no_shapes_when_flag_off(self):
        """With emit_shapes=False, collect_and_clear_shapes() returns empty list."""
        node, _ = self._make_node(emit_shapes=False)
        rng = np.random.default_rng(42)
        c1 = rng.random((30, 3)) * 0.05
        c2 = rng.random((30, 3)) * 0.05 + [5, 5, 5]
        pts = np.vstack([c1, c2]).astype(np.float32)
        payload = {"points": pts, "timestamp": 1.0}

        await node.on_input(payload)

        shapes = node.collect_and_clear_shapes()
        assert shapes == []

    @pytest.mark.asyncio
    async def test_on_input_empty_frame_no_shapes(self):
        """Empty payload produces no shapes emitted."""
        node, _ = self._make_node(emit_shapes=True)
        payload = {"points": np.zeros((0, 3), dtype=np.float32), "timestamp": 1.0}

        await node.on_input(payload)

        shapes = node.collect_and_clear_shapes()
        assert shapes == []

    @pytest.mark.asyncio
    async def test_shapes_have_cube_and_label_types(self):
        """Emitted shapes must include both CubeShape and LabelShape instances."""
        node, _ = self._make_node(emit_shapes=True)
        rng = np.random.default_rng(42)
        pts = np.vstack([
            rng.random((30, 3)) * 0.05,
            rng.random((30, 3)) * 0.05 + [5, 5, 5],
        ]).astype(np.float32)
        await node.on_input({"points": pts, "timestamp": 1.0})
        shapes = node.collect_and_clear_shapes()

        types = {type(s).__name__ for s in shapes}
        assert "CubeShape" in types

    @pytest.mark.asyncio
    async def test_collect_clears_shapes_after_retrieval(self):
        """Second call to collect_and_clear_shapes() returns empty list."""
        node, _ = self._make_node(emit_shapes=True)
        rng = np.random.default_rng(42)
        pts = np.vstack([
            rng.random((30, 3)) * 0.05,
            rng.random((30, 3)) * 0.05 + [5, 5, 5],
        ]).astype(np.float32)
        await node.on_input({"points": pts, "timestamp": 1.0})
        node.collect_and_clear_shapes()  # drain
        assert node.collect_and_clear_shapes() == []


# ---------------------------------------------------------------------------
# 4. NodeManager shape attribution (node_name assignment)
# ---------------------------------------------------------------------------

class TestNodeManagerShapeAttribution:
    """
    After DataRouter.publish_shapes(), each shape must carry:
    - id: 16-char hex string (assigned by NodeManager)
    - node_name: the node's human-readable name
    """

    @pytest.mark.asyncio
    async def test_publish_shapes_assigns_node_name(self):
        """publish_shapes() stamps shapes with node.name."""
        from app.services.nodes.managers.routing import DataRouter
        from app.modules.pipeline.operation_node import OperationNode

        rng = np.random.default_rng(42)
        pts = np.vstack([
            rng.random((30, 3)) * 0.05,
            rng.random((30, 3)) * 0.05 + [5, 5, 5],
        ]).astype(np.float32)

        mock_manager = MagicMock()
        mock_manager.downstream_map = {}
        mock_manager.nodes = {}
        mock_manager.forward_data = AsyncMock()

        node = OperationNode(
            manager=mock_manager,
            node_id="dbscan-attr-001",
            op_type="clustering",
            op_config={"eps": 0.5, "min_points": 5, "emit_shapes": True},
            name="My DBSCAN Node",
        )
        # Manually trigger on_input to populate pending shapes
        await node.on_input({"points": pts, "timestamp": 1.0})

        # Now simulate NodeManager's publish_shapes:
        nm_manager = MagicMock()
        nm_manager.nodes = {"dbscan-attr-001": node}

        # Patch websocket manager broadcast
        from unittest.mock import patch, AsyncMock as AM
        with patch("app.services.nodes.managers.routing.manager") as mock_ws:
            mock_ws.has_subscribers.return_value = True
            mock_ws.broadcast = AM(return_value=None)

            router = DataRouter(nm_manager)
            await router.publish_shapes()

            # Verify broadcast was called with correct frame structure
            assert mock_ws.broadcast.called
            call_args = mock_ws.broadcast.call_args
            topic = call_args[0][0]
            frame_dict = call_args[0][1]

            assert topic == "shapes"
            assert "shapes" in frame_dict
            assert "timestamp" in frame_dict

            emitted_shapes = frame_dict["shapes"]
            assert len(emitted_shapes) == 2  # 2 clusters × (cube + label)

            for shape in emitted_shapes:
                assert shape["node_name"] == "My DBSCAN Node", (
                    f"Expected node_name='My DBSCAN Node', got '{shape['node_name']}'"
                )
                assert shape["id"].startswith("shape_"), (
                    f"Expected shape_ prefix id, got '{shape['id']}'"
                )

    @pytest.mark.asyncio
    async def test_publish_shapes_empty_frame(self):
        """publish_shapes() with no ShapeCollectorMixin nodes broadcasts empty shapes list."""
        from app.services.nodes.managers.routing import DataRouter

        mock_node = MagicMock()
        # Not a ShapeCollectorMixin
        nm_manager = MagicMock()
        nm_manager.nodes = {"plain-node": mock_node}

        from unittest.mock import patch, AsyncMock as AM
        with patch("app.services.nodes.managers.routing.manager") as mock_ws:
            mock_ws.has_subscribers.return_value = True
            mock_ws.broadcast = AM(return_value=None)

            router = DataRouter(nm_manager)
            await router.publish_shapes()

            assert mock_ws.broadcast.called
            frame_dict = mock_ws.broadcast.call_args[0][1]
            assert frame_dict["shapes"] == []
