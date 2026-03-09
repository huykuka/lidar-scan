"""
Test suite for ML Nodes (SemanticSegmentationNode, ObjectDetectionNode)

Tests node initialization, data processing, inference integration, and error handling.
"""

import pytest
import numpy as np
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Skip entire module if torch not available
pytest.importorskip("torch")

from app.modules.ml.segmentation_node import SemanticSegmentationNode
from app.modules.ml.detection_node import ObjectDetectionNode
from app.modules.ml.model_registry import MLModelRegistry, ModelStatus, LoadedModel


class TestSemanticSegmentationNode:
    """Test cases for SemanticSegmentationNode"""

    def setup_method(self):
        """Reset singleton and create test node"""
        MLModelRegistry._instance = None
        
        self.mock_manager = Mock()
        self.mock_manager.forward_data = AsyncMock()
        
        self.node = SemanticSegmentationNode(
            manager=self.mock_manager,
            node_id="seg_test_node",
            op_type="ml_semantic_segmentation", 
            config={
                "model_name": "RandLANet",
                "dataset_name": "SemanticKITTI",
                "device": "cpu",
                "throttle_ms": 200
            },
            name="Test Segmentation Node"
        )
        
    def test_node_initialization(self):
        """Test node initialization and configuration"""
        assert self.node.id == "seg_test_node"
        assert self.node.name == "Test Segmentation Node"
        assert self.node.op_type == "ml_semantic_segmentation"
        assert self.node.config["model_name"] == "RandLANet"
        assert self.node.config["dataset_name"] == "SemanticKITTI"
        assert self.node._initialization_pending is True
        
    def test_get_status(self):
        """Test node status reporting"""
        status = self.node.get_status()
        
        assert status["id"] == "seg_test_node"
        assert status["name"] == "Test Segmentation Node"
        assert status["type"] == "ml"
        assert status["op_type"] == "ml_semantic_segmentation"
        assert status["model_status"] == "not_loaded"
        assert status["inference_latency_ms"] == 0.0
        
    @pytest.mark.asyncio
    async def test_initialize_with_model_loading(self):
        """Test node initialization with model loading"""
        # Mock registry and model
        mock_registry = Mock()
        mock_model = LoadedModel(
            model_key="randlanet__semantickitti",
            model_name="RandLANet", 
            dataset_name="SemanticKITTI",
            device="cpu",
            status=ModelStatus.READY
        )
        mock_registry.get_or_load.return_value = mock_model
        
        with patch.object(MLModelRegistry, 'get_instance', return_value=mock_registry):
            await self.node.initialize()
            
        assert self.node.model_registry is mock_registry
        assert self.node.loaded_model is mock_model
        mock_registry.get_or_load.assert_called_once_with("RandLANet", "SemanticKITTI", "cpu")
        
    @pytest.mark.asyncio
    async def test_process_ml_inference_success(self):
        """Test successful ML inference processing"""
        # Setup mock model and registry
        mock_pipeline = Mock()
        mock_model = LoadedModel(
            model_key="test_model",
            model_name="RandLANet",
            dataset_name="SemanticKITTI", 
            device="cpu",
            status=ModelStatus.READY,
            pipeline=mock_pipeline
        )
        
        mock_registry = Mock()
        mock_registry.run_inference.return_value = {
            "predict_labels": np.array([0, 1, 2, 0, 1], dtype=np.int32),
            "predict_scores": np.random.rand(5, 19).astype(np.float32)
        }
        
        self.node.model_registry = mock_registry
        self.node.loaded_model = mock_model
        
        # Create test input (N=5, 14 columns)
        test_points = np.random.rand(5, 14).astype(np.float32) 
        test_data = {"points": test_points}
        
        result = await self.node.process_ml_inference(test_data)
        
        # Verify output structure
        assert "points" in result
        assert "ml_labels" in result
        assert "ml_scores" in result
        assert "ml_num_classes" in result
        
        # Verify augmented point cloud (should be 15 columns now)
        augmented_points = result["points"]
        assert augmented_points.shape == (5, 15)
        
        # Verify labels are in column 14
        np.testing.assert_array_equal(augmented_points[:, 14], [0, 1, 2, 0, 1])
        
    @pytest.mark.asyncio
    async def test_process_ml_inference_no_model(self):
        """Test inference with no loaded model (pass-through)"""
        test_points = np.random.rand(10, 14).astype(np.float32)
        test_data = {"points": test_points}
        
        result = await self.node.process_ml_inference(test_data)
        
        # Should return original data unchanged
        assert result is test_data
        
    @pytest.mark.asyncio
    async def test_process_ml_inference_missing_points(self):
        """Test inference with missing points data"""
        test_data = {"metadata": "some_value"}  # No points key
        
        result = await self.node.process_ml_inference(test_data)
        
        # Should return original data unchanged  
        assert result is test_data
        
    @pytest.mark.asyncio
    async def test_on_input_with_initialization(self):
        """Test on_input with lazy initialization"""
        test_points = np.random.rand(100, 14).astype(np.float32)
        payload = {"points": test_points, "timestamp": 12345.0}
        
        with patch.object(self.node, 'initialize') as mock_init:
            with patch.object(self.node, 'process_data', return_value=payload) as mock_process:
                await self.node.on_input(payload)
                
                mock_init.assert_called_once()
                mock_process.assert_called_once_with(payload)
                self.mock_manager.forward_data.assert_called_once()
                

class TestObjectDetectionNode:
    """Test cases for ObjectDetectionNode"""

    def setup_method(self):
        """Reset singleton and create test node"""
        MLModelRegistry._instance = None
        
        self.mock_manager = Mock()
        self.mock_manager.forward_data = AsyncMock()
        
        self.node = ObjectDetectionNode(
            manager=self.mock_manager,
            node_id="det_test_node", 
            op_type="ml_object_detection",
            config={
                "model_name": "PointPillars",
                "dataset_name": "KITTI",
                "device": "cpu",
                "confidence_threshold": 0.7
            },
            name="Test Detection Node"
        )
        
    def test_node_initialization(self):
        """Test node initialization and configuration"""
        assert self.node.id == "det_test_node"
        assert self.node.name == "Test Detection Node"
        assert self.node.op_type == "ml_object_detection"
        assert self.node.config["model_name"] == "PointPillars"
        assert self.node.config["confidence_threshold"] == 0.7
        
    @pytest.mark.asyncio
    async def test_process_ml_inference_success(self):
        """Test successful object detection processing"""
        # Setup mock model and registry
        mock_model = LoadedModel(
            model_key="pointpillars_kitti",
            model_name="PointPillars",
            dataset_name="KITTI",
            device="cpu", 
            status=ModelStatus.READY
        )
        
        mock_registry = Mock()
        mock_registry.run_inference.return_value = {
            "predict_boxes": [
                {
                    "center": [2.0, 1.0, 0.0],
                    "size": [4.5, 2.0, 1.8],
                    "yaw": 0.2,
                    "label_class": "car", 
                    "confidence": 0.85
                },
                {
                    "center": [-1.0, 3.0, 0.0], 
                    "size": [0.8, 0.8, 1.8],
                    "yaw": -0.1,
                    "label_class": "pedestrian",
                    "confidence": 0.6  # Below threshold
                },
                {
                    "center": [5.0, -2.0, 0.0],
                    "size": [2.0, 0.8, 1.2], 
                    "yaw": 1.0,
                    "label_class": "cyclist",
                    "confidence": 0.75
                }
            ]
        }
        
        self.node.model_registry = mock_registry
        self.node.loaded_model = mock_model
        
        # Create test input (N=1000, 14 columns)
        test_points = np.random.rand(1000, 14).astype(np.float32)
        test_data = {"points": test_points}
        
        result = await self.node.process_ml_inference(test_data)
        
        # Verify output structure
        assert "points" in result
        assert "bounding_boxes" in result
        
        # Original points should be unchanged
        np.testing.assert_array_equal(result["points"], test_points)
        
        # Should have 2 boxes after confidence filtering (>= 0.7)
        boxes = result["bounding_boxes"]
        assert len(boxes) == 2
        
        # Verify box structure
        car_box = boxes[0]
        assert car_box["label"] == "car"
        assert car_box["confidence"] == 0.85
        assert car_box["center"] == [2.0, 1.0, 0.0]
        assert car_box["color"] == [255, 80, 80]  # Car color
        
    def test_class_mapping_methods(self):
        """Test class index and color mapping"""
        # Test class index mapping
        assert self.node._get_class_index("car") == 0
        assert self.node._get_class_index("pedestrian") == 1
        assert self.node._get_class_index("cyclist") == 2
        assert self.node._get_class_index("unknown") == 0  # Default
        
        # Test color mapping
        assert self.node._get_class_color("car") == [255, 80, 80]
        assert self.node._get_class_color("pedestrian") == [80, 255, 80]  
        assert self.node._get_class_color("cyclist") == [80, 80, 255]
        assert self.node._get_class_color("unknown") == [128, 128, 128]  # Default


class TestMLNodeBase:
    """Test cases for MLNode base functionality"""
    
    def setup_method(self):
        """Create concrete node for base class testing"""
        self.mock_manager = Mock()
        self.node = SemanticSegmentationNode(
            manager=self.mock_manager,
            node_id="base_test",
            op_type="ml_semantic_segmentation",
            config={},
            name="Base Test Node"
        )
        
    @pytest.mark.asyncio
    async def test_warm_up_pass_through(self):
        """Test warm-up pass-through when model not ready"""
        # No loaded model
        test_data = {"points": np.random.rand(10, 14)}
        
        result = await self.node.process_data(test_data)
        assert result is test_data
        
        # Model in loading state
        mock_model = LoadedModel(
            model_key="test",
            model_name="Test", 
            dataset_name="Test",
            device="cpu",
            status=ModelStatus.LOADING
        )
        self.node.loaded_model = mock_model
        
        result = await self.node.process_data(test_data)
        assert result is test_data
        
    def test_status_with_loaded_model(self):
        """Test status reporting with loaded model"""
        mock_model = LoadedModel(
            model_key="test_model",
            model_name="TestModel",
            dataset_name="TestDataset", 
            device="cuda:0",
            status=ModelStatus.READY
        )
        self.node.loaded_model = mock_model
        self.node.last_inference_ms = 45.2
        
        status = self.node.get_status()
        
        assert status["model_name"] == "TestModel/TestDataset"
        assert status["model_device"] == "cuda:0" 
        assert status["model_status"] == "ready"
        assert status["inference_latency_ms"] == 45.2


@pytest.mark.integration 
class TestMLNodesIntegration:
    """Integration tests for ML nodes with registry"""
    
    def setup_method(self):
        """Reset state for integration tests"""
        MLModelRegistry._instance = None
        
    @pytest.mark.asyncio
    async def test_segmentation_full_pipeline(self):
        """Test complete segmentation pipeline with mock registry"""
        mock_manager = Mock()
        mock_manager.forward_data = AsyncMock()
        
        node = SemanticSegmentationNode(
            manager=mock_manager,
            node_id="integration_seg",
            op_type="ml_semantic_segmentation",
            config={
                "model_name": "RandLANet",
                "dataset_name": "SemanticKITTI",
                "device": "cpu"
            }
        )
        
        # Mock successful model loading and inference
        with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
            mock_registry = Mock()
            mock_registry.get_or_load.return_value = LoadedModel(
                model_key="test",
                model_name="RandLANet", 
                dataset_name="SemanticKITTI",
                device="cpu",
                status=ModelStatus.READY
            )
            mock_registry.run_inference.return_value = {
                "predict_labels": np.array([1, 2, 0]),
                "predict_scores": np.random.rand(3, 19)
            }
            mock_get_instance.return_value = mock_registry
            
            # Process input
            input_payload = {"points": np.random.rand(3, 14)}
            await node.on_input(input_payload)
            
            # Verify model loading and forwarding
            mock_registry.get_or_load.assert_called_once()
            mock_manager.forward_data.assert_called_once()
            
            # Check forwarded data structure
            call_args = mock_manager.forward_data.call_args[0]
            forwarded_data = call_args[1]
            assert "points" in forwarded_data
            assert "ml_labels" in forwarded_data
            assert forwarded_data["points"].shape[1] == 15  # Augmented