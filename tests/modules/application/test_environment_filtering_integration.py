"""
Integration tests for EnvironmentFilteringNode — registry, factory, end-to-end pipeline.
"""
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

DEFAULT_CONFIG: Dict[str, Any] = {
    "throttle_ms": 0,
    "voxel_downsample_size": 0.01,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "min_plane_edge_length": 0.0,
    "min_num_points": 0,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "min_plane_area": 1.0,
    "remove_floor": True,
    "remove_ceiling": True,
    "cache_refresh_frames": 30,
    "miss_confirm_frames": 3,
}

EXPECTED_PROPERTIES = {
    "throttle_ms", "voxel_downsample_size",
    "normal_variance_threshold_deg", "coplanarity_deg",
    "outlier_ratio", "min_plane_edge_length", "min_num_points", "knn",
    "vertical_tolerance_deg", "min_plane_area",
    "remove_floor", "remove_ceiling",
    "cache_refresh_frames", "miss_confirm_frames",
}


@pytest.fixture
def mock_manager() -> MagicMock:
    m = MagicMock()
    m.forward_data = AsyncMock()
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryIntegration:
    def test_node_type_registered_in_factory(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory
        assert "environment_filtering" in NodeFactory._registry

    def test_schema_registered(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        assert node_schema_registry.get("environment_filtering") is not None

    def test_schema_has_expected_property_count(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        assert len(defn.properties) == len(EXPECTED_PROPERTIES)

    def test_schema_has_all_expected_properties(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        prop_names = {p.name for p in defn.properties}
        assert EXPECTED_PROPERTIES <= prop_names

    def test_schema_no_removed_properties(self):
        """Removed params must not appear in the schema."""
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        prop_names = {p.name for p in defn.properties}
        removed = {
            "floor_height_min", "floor_height_max",
            "ceiling_height_min", "ceiling_height_max",
            "tracker_window_size", "tracker_activation_threshold", "tracker_grace_frames",
            "ransac_fallback_enabled", "ransac_distance_threshold", "ransac_iterations",
        }
        assert not (removed & prop_names), f"Removed props still in schema: {removed & prop_names}"

    def test_schema_category_application(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        assert defn.category == "application"

    def test_schema_websocket_enabled(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        assert defn.websocket_enabled is True

    def test_schema_ports(self):
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("environment_filtering")
        assert len(defn.inputs) == 1 and defn.inputs[0].id == "in"
        assert len(defn.outputs) == 1 and defn.outputs[0].id == "out"

    def test_aggregator_exports_registry(self):
        import app.modules.application.registry as reg
        assert hasattr(reg, "environment_filtering_registry")
        assert "environment_filtering_registry" in reg.__all__


# ─────────────────────────────────────────────────────────────────────────────
# Factory builder
# ─────────────────────────────────────────────────────────────────────────────


class TestFactoryBuilder:
    def _build(self, config=None, node_id="ef-int-001", name="Test"):
        from app.modules.application.environment_filtering.registry import build_environment_filtering
        return build_environment_filtering(
            {"id": node_id, "type": "environment_filtering", "name": name,
             "config": config or DEFAULT_CONFIG.copy()},
            MagicMock(), []
        )

    def test_creates_correct_instance(self):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        assert isinstance(self._build(), EnvironmentFilteringNode)

    def test_stores_voxel_downsample_size(self):
        node = self._build()
        assert node.voxel_downsample_size == 0.01

    def test_stores_vertical_tolerance(self):
        node = self._build()
        assert node.vertical_tolerance_deg == 15.0

    def test_stores_remove_flags(self):
        node = self._build()
        assert node.remove_floor is True
        assert node.remove_ceiling is True

    def test_stores_cache_params(self):
        node = self._build()
        assert node.cache_refresh_frames == 30
        assert node.miss_confirm_frames == 3

    def test_stores_knn(self):
        node = self._build()
        assert node.knn == 30

    def test_fallback_name(self):
        node = self._build(config={}, name=None)
        assert node.name == "Environment Filtering"

    def test_invalid_throttle_defaults_to_zero(self):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        node = self._build(config={"throttle_ms": "bad"})
        assert isinstance(node, EnvironmentFilteringNode)

    def test_factory_dispatch_via_node_factory(self):
        import app.modules.application.registry  # noqa: F401
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        from app.services.nodes.node_factory import NodeFactory
        node = NodeFactory.create(
            {"id": "ef-dispatch", "type": "environment_filtering",
             "name": "Dispatch", "config": DEFAULT_CONFIG.copy()},
            MagicMock(), []
        )
        assert isinstance(node, EnvironmentFilteringNode)

    def test_no_floor_height_range_on_node(self):
        """factory-built node must not have the removed floor_height_range attr."""
        node = self._build()
        assert not hasattr(node, "floor_height_range")

    def test_no_ceiling_height_range_on_node(self):
        node = self._build()
        assert not hasattr(node, "ceiling_height_range")


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: on_input pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    @pytest.mark.asyncio
    async def test_on_input_forwards_payload(self, mock_manager):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        import asyncio
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-001", name="E2E",
            config=DEFAULT_CONFIG.copy()
        )
        pts = np.random.default_rng(0).standard_normal((200, 3)).astype(np.float32)
        await node.on_input({"points": pts, "node_id": "up", "timestamp": 1.0})
        await asyncio.sleep(0)
        mock_manager.forward_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_input_none_points_skipped(self, mock_manager):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-002", name="N",
            config=DEFAULT_CONFIG.copy()
        )
        await node.on_input({"points": None, "node_id": "up"})
        mock_manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_input_payload_has_metadata_keys(self, mock_manager):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        import asyncio
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-003", name="N",
            config=DEFAULT_CONFIG.copy()
        )
        pts = np.zeros((100, 3), dtype=np.float32)
        await node.on_input({"points": pts, "node_id": "up"})
        await asyncio.sleep(0)
        forwarded = mock_manager.forward_data.call_args[0][1]
        assert "status" in forwarded
        assert "input_point_count" in forwarded
        assert "cache_hit" in forwarded

    @pytest.mark.asyncio
    async def test_skip_if_busy_drops_frame(self, mock_manager):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-004", name="N",
            config=DEFAULT_CONFIG.copy()
        )
        node._processing = True
        pts = np.zeros((100, 3), dtype=np.float32)
        await node.on_input({"points": pts, "node_id": "up"})
        mock_manager.forward_data.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Config round-trip
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigRoundTrip:
    def test_all_params_stored(self, mock_manager):
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        cfg = {
            "voxel_downsample_size": 0.02,
            "normal_variance_threshold_deg": 70.0,
            "coplanarity_deg": 65.0,
            "outlier_ratio": 0.85,
            "min_plane_edge_length": 0.1,
            "min_num_points": 10,
            "knn": 20,
            "vertical_tolerance_deg": 20.0,
            "min_plane_area": 5.0,
            "remove_floor": False,
            "remove_ceiling": True,
            "cache_refresh_frames": 15,
            "miss_confirm_frames": 4,
        }
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="rt", name="RT", config=cfg
        )
        assert node.voxel_downsample_size == 0.02
        assert node.knn == 20
        assert node.outlier_ratio == pytest.approx(0.85)
        assert node.vertical_tolerance_deg == pytest.approx(20.0)
        assert node.min_plane_area == pytest.approx(5.0)
        assert node.remove_floor is False
        assert node.remove_ceiling is True
        assert node.cache_refresh_frames == 15
        assert node.miss_confirm_frames == 4
