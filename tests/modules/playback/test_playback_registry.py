"""
Tests for PlaybackNode registry — NodeDefinition schema + factory builder.

Covers:
  - NodeDefinition registered with correct type, category, websocket_enabled
  - PropertySchema: recording_id, playback_speed (select with 4 options), loopable, throttle_ms
  - Factory builder raises ValueError for invalid playback_speed → HTTP 400 path
  - Factory builder raises ValueError when recording_id not found
  - Factory builder instantiates PlaybackNode with correct fields
  - discover_modules() loads the playback registry
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# NodeDefinition schema
# ---------------------------------------------------------------------------

class TestPlaybackNodeDefinition:
    """Verify the registered NodeDefinition for 'playback'."""

    def _get_def(self):
        import app.modules.playback.registry  # trigger side-effect registration
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("playback")
        assert defn is not None, "playback NodeDefinition must be registered"
        return defn

    def test_type_is_playback(self):
        assert self._get_def().type == "playback"

    def test_category_is_sensor(self):
        assert self._get_def().category == "sensor"

    def test_websocket_enabled_true(self):
        assert self._get_def().websocket_enabled is True

    def test_has_recording_id_property(self):
        defn = self._get_def()
        names = [p.name for p in defn.properties]
        assert "recording_id" in names

    def test_recording_id_is_required(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "recording_id")
        assert prop.required is True

    def test_has_playback_speed_property(self):
        defn = self._get_def()
        names = [p.name for p in defn.properties]
        assert "playback_speed" in names

    def test_playback_speed_has_four_options(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "playback_speed")
        assert len(prop.options) == 4

    def test_playback_speed_options_values(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "playback_speed")
        values = {opt["value"] for opt in prop.options}
        assert values == {0.1, 0.25, 0.5, 1.0}

    def test_playback_speed_default_is_1_0(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "playback_speed")
        assert prop.default == 1.0

    def test_has_loopable_property(self):
        defn = self._get_def()
        names = [p.name for p in defn.properties]
        assert "loopable" in names

    def test_loopable_is_boolean_type(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "loopable")
        assert prop.type == "boolean"

    def test_loopable_default_false(self):
        defn = self._get_def()
        prop = next(p for p in defn.properties if p.name == "loopable")
        assert prop.default is False

    def test_has_throttle_ms_property(self):
        defn = self._get_def()
        names = [p.name for p in defn.properties]
        assert "throttle_ms" in names

    def test_has_output_port(self):
        defn = self._get_def()
        assert len(defn.outputs) > 0
        assert defn.outputs[0].id == "out"


# ---------------------------------------------------------------------------
# Factory builder
# ---------------------------------------------------------------------------

class TestPlaybackFactoryBuilder:
    """build_playback() factory validates config and instantiates PlaybackNode."""

    def _make_node_data(self, recording_id="rec-uuid", playback_speed=1.0, loopable=False):
        return {
            "id": "playback-node-001",
            "name": "Test Playback",
            "type": "playback",
            "config": {
                "recording_id": recording_id,
                "playback_speed": playback_speed,
                "loopable": loopable,
                "throttle_ms": 0,
            },
        }

    def _make_service_context(self):
        ctx = MagicMock()
        return ctx

    def _fake_recording(self, file_path: str = "/tmp/rec"):
        return {
            "id": "rec-uuid",
            "file_path": file_path,
            "frame_count": 10,
            "duration_seconds": 10.0,
            "name": "Test Recording",
        }

    def test_valid_config_builds_playback_node(self, tmp_path):
        """Factory creates a PlaybackNode with correct attributes."""
        import app.modules.playback.registry  # ensure registered
        from app.services.nodes.node_factory import NodeFactory
        from app.modules.playback.node import PlaybackNode

        node_data = self._make_node_data()

        with patch("app.modules.playback.registry.SessionLocal") as mock_ses, \
             patch("app.modules.playback.registry.RecordingRepository") as mock_repo_cls:
            mock_db = MagicMock()
            mock_ses.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ses.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = self._fake_recording()
            mock_repo_cls.return_value = mock_repo

            node = NodeFactory.create(node_data, self._make_service_context(), [])

        assert isinstance(node, PlaybackNode)
        assert node.id == "playback-node-001"
        assert node._recording_id == "rec-uuid"
        assert node._playback_speed == 1.0
        assert node._loopable is False

    def test_invalid_speed_raises_value_error(self):
        """Factory raises ValueError for speed not in VALID_SPEEDS."""
        import app.modules.playback.registry
        from app.services.nodes.node_factory import NodeFactory

        node_data = self._make_node_data(playback_speed=0.75)

        with patch("app.modules.playback.registry.SessionLocal") as mock_ses, \
             patch("app.modules.playback.registry.RecordingRepository") as mock_repo_cls:
            mock_db = MagicMock()
            mock_ses.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ses.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = self._fake_recording()
            mock_repo_cls.return_value = mock_repo

            with pytest.raises(ValueError, match="playback_speed"):
                NodeFactory.create(node_data, self._make_service_context(), [])

    def test_missing_recording_raises_value_error(self):
        """Factory raises ValueError if recording_id not found in DB."""
        import app.modules.playback.registry
        from app.services.nodes.node_factory import NodeFactory

        node_data = self._make_node_data(recording_id="nonexistent")

        with patch("app.modules.playback.registry.SessionLocal") as mock_ses, \
             patch("app.modules.playback.registry.RecordingRepository") as mock_repo_cls:
            mock_db = MagicMock()
            mock_ses.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ses.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None  # not found
            mock_repo_cls.return_value = mock_repo

            with pytest.raises(ValueError, match="recording_id"):
                NodeFactory.create(node_data, self._make_service_context(), [])

    def test_default_speed_is_1_0_when_omitted(self):
        """If playback_speed not in config, defaults to 1.0."""
        import app.modules.playback.registry
        from app.services.nodes.node_factory import NodeFactory
        from app.modules.playback.node import PlaybackNode

        node_data = {
            "id": "playback-node-002",
            "name": "Test",
            "type": "playback",
            "config": {
                "recording_id": "rec-uuid",
                # No playback_speed
            },
        }

        with patch("app.modules.playback.registry.SessionLocal") as mock_ses, \
             patch("app.modules.playback.registry.RecordingRepository") as mock_repo_cls:
            mock_db = MagicMock()
            mock_ses.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ses.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = self._fake_recording()
            mock_repo_cls.return_value = mock_repo

            node = NodeFactory.create(node_data, self._make_service_context(), [])

        assert isinstance(node, PlaybackNode)
        assert node._playback_speed == 1.0

    def test_loopable_passed_correctly(self):
        """Factory passes loopable=True correctly to PlaybackNode."""
        import app.modules.playback.registry
        from app.services.nodes.node_factory import NodeFactory

        node_data = self._make_node_data(loopable=True)

        with patch("app.modules.playback.registry.SessionLocal") as mock_ses, \
             patch("app.modules.playback.registry.RecordingRepository") as mock_repo_cls:
            mock_db = MagicMock()
            mock_ses.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ses.return_value.__exit__ = MagicMock(return_value=False)

            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = self._fake_recording()
            mock_repo_cls.return_value = mock_repo

            node = NodeFactory.create(node_data, self._make_service_context(), [])

        assert node._loopable is True


# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------

class TestPlaybackModuleDiscovery:
    """discover_modules() must load the playback registry."""

    def test_discover_modules_loads_playback(self):
        from app.modules import discover_modules
        from app.services.nodes.schema import node_schema_registry

        discover_modules()

        defn = node_schema_registry.get("playback")
        assert defn is not None, "playback must be registered after discover_modules()"

    def test_playback_in_node_factory_after_discovery(self):
        from app.modules import discover_modules
        from app.services.nodes.node_factory import NodeFactory

        discover_modules()

        assert "playback" in NodeFactory._registry, \
            "playback factory must be registered after discover_modules()"
