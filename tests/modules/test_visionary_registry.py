"""Tests for visionary_sensor node registry and schema"""
import pytest
from app.modules.visionary.registry import VISIONARY_MODELS


class TestVisionaryRegistrySchema:
    """Test node definition schema for visionary_sensor node"""

    def test_visionary_definition_exists(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        assert visionary_def is not None
        assert visionary_def.display_name == "Visionary 3D Camera"

    def test_camera_model_property_is_select(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")
        assert cam_prop.type == "select"
        assert cam_prop.required is True

    def test_camera_model_has_correct_option_count(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")
        assert len(cam_prop.options) == len(VISIONARY_MODELS)

    def test_camera_model_options_match_models(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")

        model_ids = {m["model_id"] for m in VISIONARY_MODELS}
        option_values = {opt["value"] for opt in cam_prop.options}
        assert option_values == model_ids

    def test_camera_model_options_contain_full_metadata(self):
        """Each option carries full camera model metadata"""
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")

        required_keys = {
            "label", "value", "is_stereo", "acquisition_method",
            "default_hostname", "cola_protocol", "default_control_port",
            "default_streaming_port", "thumbnail_url", "icon_name",
            "icon_color", "disabled",
        }

        for opt in cam_prop.options:
            for key in required_keys:
                assert key in opt, f"Option {opt['value']} missing key '{key}'"

    def test_camera_model_options_metadata_matches_models(self):
        """Option metadata matches the corresponding model data"""
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")

        models_by_id = {m["model_id"]: m for m in VISIONARY_MODELS}
        for opt in cam_prop.options:
            model = models_by_id[opt["value"]]
            assert opt["label"] == model["display_name"]
            assert opt["is_stereo"] == model["is_stereo"]
            assert opt["acquisition_method"] == model["acquisition_method"]
            assert opt["default_hostname"] == model["default_hostname"]
            assert opt["cola_protocol"] == model["cola_protocol"]
            assert opt["default_control_port"] == model["default_control_port"]
            assert opt["default_streaming_port"] == model["default_streaming_port"]
            assert opt["disabled"] == model.get("disabled", False)

    def test_camera_model_default_is_visionary_t_mini_cx(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")
        assert cam_prop.default == "visionary_t_mini_cx"

    def test_sdk_models_have_sdk_depends_on_for_streaming_port(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        port_prop = next(p for p in visionary_def.properties if p.name == "streaming_port")
        assert port_prop.depends_on is not None
        assert "camera_model" in port_prop.depends_on
        sdk_models = [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "sdk"]
        for model_id in sdk_models:
            assert model_id in port_prop.depends_on["camera_model"]

    def test_harvester_models_have_cti_path_depends_on(self):
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cti_prop = next(p for p in visionary_def.properties if p.name == "cti_path")
        assert cti_prop.depends_on is not None
        assert "camera_model" in cti_prop.depends_on
        harvester_models = [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "harvester"]
        for model_id in harvester_models:
            assert model_id in cti_prop.depends_on["camera_model"]

    def test_all_thumbnail_urls_follow_convention(self):
        """All thumbnail URLs should point to /api/v1/assets/visionary/"""
        from app.services.nodes.schema import node_schema_registry
        visionary_def = node_schema_registry.get("visionary_sensor")
        cam_prop = next(p for p in visionary_def.properties if p.name == "camera_model")

        for opt in cam_prop.options:
            url = opt.get("thumbnail_url")
            if url:
                assert url.startswith("/api/v1/assets/visionary/"), (
                    f"Option {opt['value']} thumbnail_url '{url}' doesn't follow convention"
                )


class TestVisionaryBuildFunction:
    """Test the build_visionary_sensor factory function"""

    def test_build_with_valid_cx_model(self):
        """Verify building a sensor with a valid CX model"""
        from unittest.mock import MagicMock
        from app.modules.visionary.registry import build_visionary_sensor

        mock_context = MagicMock()
        mock_context._topic_registry.register.return_value = "test-topic"

        node = {
            "id": "test-node-123",
            "name": "Test Camera",
            "config": {"camera_model": "visionary_t_mini_cx"},
        }

        sensor = build_visionary_sensor(node, mock_context, [])
        assert sensor is not None

    def test_build_with_unknown_model_raises(self):
        from unittest.mock import MagicMock
        from app.modules.visionary.registry import build_visionary_sensor

        mock_context = MagicMock()
        node = {
            "id": "test-node-456",
            "config": {"camera_model": "nonexistent_model"},
        }

        with pytest.raises(ValueError, match="Unknown camera_model"):
            build_visionary_sensor(node, mock_context, [])
