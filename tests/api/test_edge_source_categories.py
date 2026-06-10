"""
Unit tests for _validate_edge_source_categories in the DAG service.

Covers:
  - Edge from allowed category passes
  - Edge from disallowed category raises HTTP 422
  - Edge to node with no restrictions passes
  - Unknown target/source nodes are skipped
  - OR semantics: source passes if ANY restricted port accepts it
  - Case-insensitive matching
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.dag.service import _validate_edge_source_categories
from app.api.v1.schemas.edges import EdgeRecord
from app.api.v1.schemas.nodes import NodeRecord
from app.services.nodes.schema import NodeDefinition, PortSchema, SchemaRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _node(node_id: str, name: str, node_type: str, category: str) -> NodeRecord:
    return NodeRecord(
        id=node_id,
        name=name,
        type=node_type,
        category=category,
        enabled=True,
        visible=True,
    )


def _edge(source: str, target: str, edge_id: str = "e1") -> EdgeRecord:
    return EdgeRecord(
        id=edge_id,
        source_node=source,
        source_port="out",
        target_node=target,
        target_port="in",
    )


def _registry_with(*defs: NodeDefinition) -> SchemaRegistry:
    reg = SchemaRegistry()
    for d in defs:
        reg.register(d)
    return reg


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateEdgeSourceCategories:
    """Tests for the _validate_edge_source_categories function."""

    def test_allowed_category_passes(self):
        """Application → result_storage should pass."""
        nodes = [
            _node("app-1", "Profiler", "vehicle_profiler", "application"),
            _node("rs-1", "Result Storage", "result_storage", "flow_control"),
        ]
        edges = [_edge("app-1", "rs-1")]
        target_def = NodeDefinition(
            type="result_storage",
            display_name="Result Storage",
            category="flow_control",
            inputs=[PortSchema(id="in", label="Input", allowed_source_categories=["application"])],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            _validate_edge_source_categories(nodes, edges)

    def test_disallowed_category_raises_422(self):
        """Sensor → result_storage should raise HTTP 422."""
        nodes = [
            _node("sensor-1", "LiDAR", "sensor", "sensor"),
            _node("rs-1", "Result Storage", "result_storage", "flow_control"),
        ]
        edges = [_edge("sensor-1", "rs-1")]
        target_def = NodeDefinition(
            type="result_storage",
            display_name="Result Storage",
            category="flow_control",
            inputs=[PortSchema(id="in", label="Input", allowed_source_categories=["application"])],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            with pytest.raises(HTTPException) as exc_info:
                _validate_edge_source_categories(nodes, edges)
            assert exc_info.value.status_code == 422
            assert "application" in exc_info.value.detail
            assert "sensor" in exc_info.value.detail

    def test_no_restrictions_passes(self):
        """Edge to a node with no allowed_source_categories is always ok."""
        nodes = [
            _node("sensor-1", "LiDAR", "sensor", "sensor"),
            _node("out-1", "Output", "output", "flow_control"),
        ]
        edges = [_edge("sensor-1", "out-1")]
        target_def = NodeDefinition(
            type="output",
            display_name="Output",
            category="flow_control",
            inputs=[PortSchema(id="in", label="Input")],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            _validate_edge_source_categories(nodes, edges)

    def test_unknown_target_skipped(self):
        """Edge pointing to a node not in the node list is silently skipped."""
        nodes = [_node("app-1", "Profiler", "vehicle_profiler", "application")]
        edges = [_edge("app-1", "missing-node")]
        reg = _registry_with()

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            _validate_edge_source_categories(nodes, edges)

    def test_unknown_source_skipped(self):
        """Edge from a node not in the node list is silently skipped."""
        nodes = [_node("rs-1", "Result Storage", "result_storage", "flow_control")]
        edges = [_edge("missing-source", "rs-1")]
        target_def = NodeDefinition(
            type="result_storage",
            display_name="Result Storage",
            category="flow_control",
            inputs=[PortSchema(id="in", label="Input", allowed_source_categories=["application"])],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            _validate_edge_source_categories(nodes, edges)

    def test_case_insensitive(self):
        """Category matching should be case-insensitive."""
        nodes = [
            _node("app-1", "Profiler", "vehicle_profiler", "Application"),
            _node("rs-1", "Result Storage", "result_storage", "flow_control"),
        ]
        edges = [_edge("app-1", "rs-1")]
        target_def = NodeDefinition(
            type="result_storage",
            display_name="Result Storage",
            category="flow_control",
            inputs=[PortSchema(id="in", label="Input", allowed_source_categories=["application"])],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            _validate_edge_source_categories(nodes, edges)

    def test_or_semantics_multi_port(self):
        """Source should pass if ANY restricted port allows its category (OR logic)."""
        nodes = [
            _node("sensor-1", "LiDAR", "sensor", "sensor"),
            _node("target-1", "MultiInput", "multi_input", "flow_control"),
        ]
        edges = [_edge("sensor-1", "target-1")]
        target_def = NodeDefinition(
            type="multi_input",
            display_name="Multi Input",
            category="flow_control",
            inputs=[
                PortSchema(id="in_app", label="App Input", allowed_source_categories=["application"]),
                PortSchema(id="in_sensor", label="Sensor Input", allowed_source_categories=["sensor"]),
            ],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            # sensor should pass because in_sensor port allows it (OR logic)
            _validate_edge_source_categories(nodes, edges)

    def test_or_semantics_all_ports_reject(self):
        """Source should fail if NO restricted port allows its category."""
        nodes = [
            _node("fusion-1", "Fusion", "fusion", "fusion"),
            _node("target-1", "MultiInput", "multi_input", "flow_control"),
        ]
        edges = [_edge("fusion-1", "target-1")]
        target_def = NodeDefinition(
            type="multi_input",
            display_name="Multi Input",
            category="flow_control",
            inputs=[
                PortSchema(id="in_app", label="App Input", allowed_source_categories=["application"]),
                PortSchema(id="in_sensor", label="Sensor Input", allowed_source_categories=["sensor"]),
            ],
            outputs=[],
        )
        reg = _registry_with(target_def)

        with patch("app.api.v1.dag.service.node_schema_registry", reg):
            with pytest.raises(HTTPException) as exc_info:
                _validate_edge_source_categories(nodes, edges)
            assert exc_info.value.status_code == 422
