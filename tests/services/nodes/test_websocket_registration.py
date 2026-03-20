"""
Tests for WebSocket topic registration logic based on websocket_enabled flag.

This test suite validates that:
1. Nodes with websocket_enabled=True ARE registered for WebSocket streaming
2. Nodes with websocket_enabled=False are NOT registered for WebSocket streaming
3. The visible flag still controls registration for streaming-enabled nodes
4. Non-streaming nodes never appear in WebSocket topic lists regardless of visibility
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from app.services.nodes.managers.config import ConfigLoader
from app.services.nodes.schema import NodeDefinition, node_schema_registry


class TestWebSocketRegistrationLogic:
    """Test suite for WebSocket topic registration based on websocket_enabled flag"""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a mock NodeManager instance"""
        manager = Mock()
        manager.nodes = {}
        manager.node_runtime_status = {}
        manager.downstream_map = {}
        manager._throttle_config = {}
        manager._last_process_time = {}
        manager._throttled_count = {}
        return manager
    
    @pytest.fixture
    def config_loader(self, mock_manager):
        """Create ConfigLoader instance with mock NodeManager"""
        return ConfigLoader(mock_manager)
    
    @pytest.fixture(autouse=True)
    def setup_node_definitions(self):
        """Register test node definitions before each test"""
        # Clear existing definitions
        node_schema_registry._definitions.clear()
        
        # Register streaming node type
        node_schema_registry.register(NodeDefinition(
            type="test_streaming",
            display_name="Test Streaming Node",
            category="sensor",
            websocket_enabled=True
        ))
        
        # Register non-streaming node type
        node_schema_registry.register(NodeDefinition(
            type="test_non_streaming",
            display_name="Test Non-Streaming Node",
            category="calibration",
            websocket_enabled=False
        ))
        
        yield
        
        # Cleanup after test
        node_schema_registry._definitions.clear()
    
    @patch('app.services.nodes.managers.config.manager')
    @patch('app.services.nodes.managers.config.NodeFactory')
    def test_streaming_node_visible_registers_websocket_topic(
        self, mock_node_factory, mock_ws_manager, config_loader
    ):
        """Test: Streaming node with visible=True SHOULD register WebSocket topic"""
        # Arrange
        node_data = {
            "id": "node123",
            "type": "test_streaming",
            "category": "sensor",
            "visible": True,
            "config": {}
        }
        
        mock_node_instance = Mock()
        mock_node_instance.name = "Test Streaming Node"  # Add name attribute for slugify
        mock_node_factory.create.return_value = mock_node_instance
        mock_ws_manager.register_topic = MagicMock()
        
        # Act
        config_loader._create_node(node_data, "sensor", [])
        
        # Assert
        # WebSocket topic should be registered
        mock_ws_manager.register_topic.assert_called_once()
        called_topic = mock_ws_manager.register_topic.call_args[0][0]
        assert called_topic.startswith("test_streaming_node")
        assert called_topic.endswith("node123"[:8])
        
        # Node instance should have _ws_topic attribute
        assert hasattr(mock_node_instance, '_ws_topic')
        assert mock_node_instance._ws_topic == called_topic
    
    @patch('app.services.nodes.managers.config.manager')
    @patch('app.services.nodes.managers.config.NodeFactory')
    def test_streaming_node_invisible_skips_websocket_registration(
        self, mock_node_factory, mock_ws_manager, config_loader
    ):
        """Test: Streaming node with visible=False should NOT register WebSocket topic"""
        # Arrange
        node_data = {
            "id": "node456",
            "type": "test_streaming",
            "category": "sensor",
            "visible": False,
            "config": {}
        }
        
        mock_node_instance = Mock()
        mock_node_instance.name = "Test Streaming Node"  # Add name attribute for slugify
        mock_node_factory.create.return_value = mock_node_instance
        mock_ws_manager.register_topic = MagicMock()
        
        # Act
        config_loader._create_node(node_data, "sensor", [])
        
        # Assert
        # WebSocket topic should NOT be registered
        mock_ws_manager.register_topic.assert_not_called()
        
        # Node instance should have _ws_topic set to None
        assert hasattr(mock_node_instance, '_ws_topic')
        assert mock_node_instance._ws_topic is None
    
    @patch('app.services.nodes.managers.config.manager')
    @patch('app.services.nodes.managers.config.NodeFactory')
    def test_non_streaming_node_visible_skips_websocket_registration(
        self, mock_node_factory, mock_ws_manager, config_loader
    ):
        """Test: Non-streaming node with visible=True should NOT register WebSocket topic"""
        # Arrange
        node_data = {
            "id": "node789",
            "type": "test_non_streaming",
            "category": "calibration",
            "visible": True,  # visible=True but websocket_enabled=False
            "config": {}
        }
        
        mock_node_instance = Mock()
        mock_node_instance.name = "Test Non-Streaming Node"  # Add name attribute for slugify
        mock_node_factory.create.return_value = mock_node_instance
        mock_ws_manager.register_topic = MagicMock()
        
        # Act
        config_loader._create_node(node_data, "calibration", [])
        
        # Assert
        # WebSocket topic should NOT be registered (websocket_enabled=False overrides visible=True)
        mock_ws_manager.register_topic.assert_not_called()
        
        # Node instance should have _ws_topic set to None
        assert hasattr(mock_node_instance, '_ws_topic')
        assert mock_node_instance._ws_topic is None
    
    @patch('app.services.nodes.managers.config.manager')
    @patch('app.services.nodes.managers.config.NodeFactory')
    def test_non_streaming_node_invisible_skips_websocket_registration(
        self, mock_node_factory, mock_ws_manager, config_loader
    ):
        """Test: Non-streaming node with visible=False should NOT register WebSocket topic"""
        # Arrange
        node_data = {
            "id": "node000",
            "type": "test_non_streaming",
            "category": "calibration",
            "visible": False,  # Both invisible and non-streaming
            "config": {}
        }
        
        mock_node_instance = Mock()
        mock_node_instance.name = "Test Non-Streaming Node"  # Add name attribute for slugify
        mock_node_factory.create.return_value = mock_node_instance
        mock_ws_manager.register_topic = MagicMock()
        
        # Act
        config_loader._create_node(node_data, "calibration", [])
        
        # Assert
        # WebSocket topic should NOT be registered
        mock_ws_manager.register_topic.assert_not_called()
        
        # Node instance should have _ws_topic set to None
        assert hasattr(mock_node_instance, '_ws_topic')
        assert mock_node_instance._ws_topic is None
    
    @patch('app.services.nodes.managers.config.manager')
    @patch('app.services.nodes.managers.config.NodeFactory')
    def test_missing_websocket_enabled_defaults_to_true(
        self, mock_node_factory, mock_ws_manager, config_loader
    ):
        """Test: Node definition without websocket_enabled defaults to True (backward compat)"""
        # Arrange: Register a node definition WITHOUT explicit websocket_enabled
        node_schema_registry.register(NodeDefinition(
            type="test_legacy",
            display_name="Test Legacy Node",
            category="operation"
            # websocket_enabled not explicitly set - should default to True
        ))
        
        node_data = {
            "id": "node_legacy",
            "type": "test_legacy",
            "category": "operation",
            "visible": True,
            "config": {}
        }
        
        mock_node_instance = Mock()
        mock_node_instance.name = "Test Legacy Node"  # Add name attribute for slugify
        mock_node_factory.create.return_value = mock_node_instance
        mock_ws_manager.register_topic = MagicMock()
        
        # Act
        config_loader._create_node(node_data, "operation", [])
        
        # Assert
        # WebSocket topic SHOULD be registered (default behavior)
        mock_ws_manager.register_topic.assert_called_once()
        assert hasattr(mock_node_instance, '_ws_topic')
        assert mock_node_instance._ws_topic is not None


class TestRealNodeDefinitions:
    """Integration tests validating real node definitions have correct websocket_enabled values"""
    
    @pytest.fixture(autouse=True)
    def import_all_registries(self):
        """Import all node registry modules to populate node_schema_registry"""
        # Import all registry modules to trigger @register decorators
        import app.modules.lidar.registry
        import app.modules.fusion.registry
        import app.modules.calibration.registry
        import app.modules.pipeline.registry
        import app.modules.flow_control.if_condition.registry
        yield
    
    def test_sensor_nodes_have_websocket_enabled_true(self):
        """Test: All sensor nodes should have websocket_enabled=True"""
        definition = node_schema_registry.get("sensor")
        assert definition is not None, "Sensor node definition not found"
        assert definition.websocket_enabled is True, \
            "Sensor node should have websocket_enabled=True"
    
    def test_fusion_nodes_have_websocket_enabled_true(self):
        """Test: All fusion nodes should have websocket_enabled=True"""
        definition = node_schema_registry.get("fusion")
        assert definition is not None, "Fusion node definition not found"
        assert definition.websocket_enabled is True, \
            "Fusion node should have websocket_enabled=True"
    
    def test_calibration_nodes_have_websocket_enabled_false(self):
        """Test: Calibration nodes should have websocket_enabled=False"""
        definition = node_schema_registry.get("calibration")
        assert definition is not None, "Calibration node definition not found"
        assert definition.websocket_enabled is False, \
            "Calibration node should have websocket_enabled=False"
    
    def test_flow_control_nodes_have_websocket_enabled_false(self):
        """Test: Flow control nodes should have websocket_enabled=False"""
        definition = node_schema_registry.get("if_condition")
        assert definition is not None, "If_condition node definition not found"
        assert definition.websocket_enabled is False, \
            "If_condition node should have websocket_enabled=False"
    
    def test_pipeline_operation_nodes_have_websocket_enabled_true(self):
        """Test: Pipeline operation nodes should have websocket_enabled=True"""
        operation_types = [
            "crop", "downsample", "outlier_removal", "radius_outlier_removal",
            "plane_segmentation", "clustering", "boundary_detection", 
            "filter_by_key", "debug_save"
        ]
        
        for node_type in operation_types:
            definition = node_schema_registry.get(node_type)
            assert definition is not None, f"{node_type} definition not found"
            assert definition.websocket_enabled is True, \
                f"{node_type} should have websocket_enabled=True"
