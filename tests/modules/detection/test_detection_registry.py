"""Tests for detection module registry integration."""
import pytest


class TestDetectionRegistry:
    def test_schema_registered(self):
        """Ensure the object_detection_3d NodeDefinition is registered."""
        from app.modules.detection import registry  # noqa: F401 — triggers side-effects
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("object_detection_3d")
        assert defn is not None
        assert defn.display_name == "3D Object Detection"
        assert defn.category == "detection"

    def test_schema_has_model_property(self):
        from app.modules.detection import registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("object_detection_3d")
        model_prop = next((p for p in defn.properties if p.name == "model"), None)
        assert model_prop is not None
        assert model_prop.type == "select"
        assert any(opt["value"] == "pointpillars" for opt in model_prop.options)

    def test_schema_has_device_property(self):
        from app.modules.detection import registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("object_detection_3d")
        device_prop = next((p for p in defn.properties if p.name == "device"), None)
        assert device_prop is not None
        assert device_prop.type == "select"
        assert any(opt["value"] == "cpu" for opt in device_prop.options)
        assert any(opt["value"] == "cuda" for opt in device_prop.options)

    def test_factory_registered(self):
        """Ensure NodeFactory can build the detection node type."""
        from app.modules.detection import registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory

        assert "object_detection_3d" in NodeFactory._registry

    def test_schema_has_emit_shapes_property(self):
        from app.modules.detection import registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("object_detection_3d")
        prop = next((p for p in defn.properties if p.name == "emit_shapes"), None)
        assert prop is not None
        assert prop.type == "boolean"
        assert prop.default is True

    def test_schema_ports(self):
        from app.modules.detection import registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("object_detection_3d")
        assert len(defn.inputs) == 1
        assert defn.inputs[0].id == "in"
        assert len(defn.outputs) == 1
        assert defn.outputs[0].id == "out"
