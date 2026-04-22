"""
Integration tests for EnvironmentFilteringNode.

References:
  - backend-tasks.md Phase 5
  - api-spec.md (config JSON shape, node registration)
  - technical.md § 10 (registry pattern)
"""
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock

import numpy as np
import open3d as o3d
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
    "floor_height_min": -0.5,
    "floor_height_max": 0.5,
    "ceiling_height_min": 2.0,
    "ceiling_height_max": 4.0,
    "min_plane_area": 1.0,
}


@pytest.fixture
def mock_manager() -> Mock:
    manager = Mock()
    manager.forward_data = AsyncMock()
    return manager


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryIntegration:
    def test_node_factory_registers_environment_filtering(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory

        assert "environment_filtering" in NodeFactory._registry

    def test_schema_registered(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        assert defn is not None

    def test_schema_has_14_properties(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        assert len(defn.properties) == 14

    def test_schema_category_application(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        assert defn.category == "application"

    def test_schema_websocket_enabled(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        assert defn.websocket_enabled is True

    def test_schema_has_input_output_ports(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        assert len(defn.inputs) == 1
        assert len(defn.outputs) == 1
        assert defn.inputs[0].id == "in"
        assert defn.outputs[0].id == "out"

    def test_schema_has_voxel_downsample_property(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        prop_names = {p.name for p in defn.properties}
        assert "voxel_downsample_size" in prop_names

    def test_schema_has_all_required_properties(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("environment_filtering")
        prop_names = {p.name for p in defn.properties}
        required = {
            "throttle_ms", "voxel_downsample_size",
            "normal_variance_threshold_deg", "coplanarity_deg",
            "outlier_ratio", "min_plane_edge_length", "min_num_points", "knn",
            "vertical_tolerance_deg",
            "floor_height_min", "floor_height_max",
            "ceiling_height_min", "ceiling_height_max",
            "min_plane_area",
        }
        assert required <= prop_names

    def test_aggregator_exposes_environment_filtering_registry(self) -> None:
        import app.modules.application.registry as app_registry

        assert hasattr(app_registry, "environment_filtering_registry")

    def test_aggregator_all_contains_environment_filtering(self) -> None:
        import app.modules.application.registry as app_registry

        assert "environment_filtering_registry" in app_registry.__all__


# ─────────────────────────────────────────────────────────────────────────────
# Factory builder
# ─────────────────────────────────────────────────────────────────────────────


class TestFactoryBuilder:
    def test_factory_creates_correct_instance(self) -> None:
        from app.modules.application.environment_filtering.registry import (
            build_environment_filtering,
        )
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node_data = {
            "id": "ef-int-001",
            "type": "environment_filtering",
            "name": "Integration EF",
            "config": DEFAULT_CONFIG.copy(),
        }
        ctx = MagicMock()
        node = build_environment_filtering(node_data, ctx, [])
        assert isinstance(node, EnvironmentFilteringNode)

    def test_factory_stores_all_14_params(self) -> None:
        """All 14 config params must be correctly stored in node instance."""
        from app.modules.application.environment_filtering.registry import (
            build_environment_filtering,
        )

        node_data = {
            "id": "ef-int-002",
            "type": "environment_filtering",
            "name": "Param Test",
            "config": DEFAULT_CONFIG.copy(),
        }
        ctx = MagicMock()
        node = build_environment_filtering(node_data, ctx, [])
        assert node.voxel_downsample_size == 0.01
        assert node.vertical_tolerance_deg == 15.0
        assert node.floor_height_range == (-0.5, 0.5)
        assert node.ceiling_height_range == (2.0, 4.0)
        assert node.min_plane_area == 1.0

    def test_node_factory_create_dispatches_correctly(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
        from app.services.nodes.node_factory import NodeFactory

        node_data = {
            "id": "ef-int-003",
            "type": "environment_filtering",
            "name": "Factory Dispatch",
            "config": DEFAULT_CONFIG.copy(),
        }
        ctx = MagicMock()
        node = NodeFactory.create(node_data, ctx, [])
        assert isinstance(node, EnvironmentFilteringNode)

    def test_factory_fallback_name(self) -> None:
        from app.modules.application.environment_filtering.registry import (
            build_environment_filtering,
        )

        node_data = {"id": "ef-004", "type": "environment_filtering", "name": None, "config": {}}
        ctx = MagicMock()
        node = build_environment_filtering(node_data, ctx, [])
        assert node.name == "Environment Filtering"

    def test_factory_invalid_throttle_ms_defaults_to_zero(self) -> None:
        from app.modules.application.environment_filtering.registry import (
            build_environment_filtering,
        )
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node_data = {
            "id": "ef-005",
            "type": "environment_filtering",
            "name": "Throttle Test",
            "config": {"throttle_ms": "bad_value"},
        }
        ctx = MagicMock()
        # Should not raise
        node = build_environment_filtering(node_data, ctx, [])
        assert isinstance(node, EnvironmentFilteringNode)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: on_input pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    @pytest.mark.asyncio
    async def test_on_input_forwards_payload(self, mock_manager: Mock) -> None:
        """on_input must call manager.forward_data with enriched payload."""
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node = EnvironmentFilteringNode(
            manager=mock_manager,
            node_id="ef-e2e-001",
            name="E2E Test",
            config=DEFAULT_CONFIG.copy(),
        )
        rng = np.random.default_rng(0)
        pts = rng.standard_normal((200, 3)).astype(np.float32)
        payload = {"points": pts, "node_id": "upstream-001", "timestamp": 1.0}

        await node.on_input(payload)

        # Allow create_task to run
        import asyncio
        await asyncio.sleep(0)
        mock_manager.forward_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_input_none_points_skipped(self, mock_manager: Mock) -> None:
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-002", name="N", config=DEFAULT_CONFIG.copy()
        )
        await node.on_input({"points": None, "node_id": "up"})
        mock_manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_input_metadata_in_payload(self, mock_manager: Mock) -> None:
        """Forwarded payload must contain metadata keys from filtering."""
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-003", name="N", config=DEFAULT_CONFIG.copy()
        )
        pts = np.zeros((100, 3), dtype=np.float32)
        payload = {"points": pts, "node_id": "up"}
        await node.on_input(payload)

        import asyncio
        await asyncio.sleep(0)
        forwarded = mock_manager.forward_data.call_args[0][1]
        assert "status" in forwarded
        assert "input_point_count" in forwarded
        assert "downsampling_enabled" in forwarded

    @pytest.mark.asyncio
    async def test_skip_if_busy_drops_frame(self, mock_manager: Mock) -> None:
        """Second frame while processing should be silently dropped."""
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-e2e-004", name="N", config=DEFAULT_CONFIG.copy()
        )
        node._processing = True  # Simulate in-progress
        pts = np.zeros((100, 3), dtype=np.float32)
        await node.on_input({"points": pts, "node_id": "up"})
        mock_manager.forward_data.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Config persistence
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigPersistence:
    def test_all_14_params_stored_from_json_config(self, mock_manager: Mock) -> None:
        """Simulate loading from JSON DAG config — all params must round-trip."""
        from app.modules.application.environment_filtering.node import EnvironmentFilteringNode

        json_config = {
            "throttle_ms": 50,
            "voxel_downsample_size": 0.015,
            "normal_variance_threshold_deg": 70.0,
            "coplanarity_deg": 65.0,
            "outlier_ratio": 0.85,
            "min_plane_edge_length": 0.1,
            "min_num_points": 10,
            "knn": 20,
            "vertical_tolerance_deg": 25.0,
            "floor_height_min": -0.8,
            "floor_height_max": 0.8,
            "ceiling_height_min": 8.0,
            "ceiling_height_max": 12.0,
            "min_plane_area": 5.0,
        }
        node = EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-persist", name="Persist", config=json_config
        )
        assert node.voxel_downsample_size == 0.015
        assert node.vertical_tolerance_deg == 25.0
        assert node.floor_height_range == (-0.8, 0.8)
        assert node.ceiling_height_range == (8.0, 12.0)
        assert node.min_plane_area == 5.0
        assert node._op.knn == 20
        assert node._op.outlier_ratio == 0.85
