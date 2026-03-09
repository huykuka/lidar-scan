"""
Test configuration and runner for ML module tests

Provides test setup, fixtures, and utilities for ML testing.
"""

import pytest
import numpy as np
from typing import Dict, Any
from unittest.mock import Mock

# Test configuration
pytest_plugins = ['pytest_asyncio']


@pytest.fixture
def mock_point_cloud():
    """Fixture providing mock point cloud data (N=100, 14 columns)"""
    np.random.seed(42)  # Reproducible test data
    return np.random.rand(100, 14).astype(np.float32)


@pytest.fixture  
def mock_small_point_cloud():
    """Fixture providing small mock point cloud for fast tests (N=10)"""
    np.random.seed(42)
    return np.random.rand(10, 14).astype(np.float32)


@pytest.fixture
def mock_manager():
    """Fixture providing mock node manager"""
    manager = Mock()
    manager.forward_data = Mock()
    return manager


@pytest.fixture
def segmentation_config():
    """Fixture providing segmentation node configuration"""
    return {
        "model_name": "RandLANet",
        "dataset_name": "SemanticKITTI", 
        "device": "cpu",
        "throttle_ms": 200,
        "num_points": 45056
    }


@pytest.fixture
def detection_config():
    """Fixture providing detection node configuration"""  
    return {
        "model_name": "PointPillars",
        "dataset_name": "KITTI",
        "device": "cpu", 
        "throttle_ms": 500,
        "confidence_threshold": 0.5
    }


@pytest.fixture
def mock_segmentation_result():
    """Fixture providing mock segmentation inference result"""
    return {
        "predict_labels": np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=np.int32),
        "predict_scores": np.random.rand(10, 19).astype(np.float32)
    }


@pytest.fixture
def mock_detection_result():
    """Fixture providing mock detection inference result"""
    return {
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
                "confidence": 0.3  # Low confidence
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


class MLTestUtils:
    """Utility functions for ML testing"""
    
    @staticmethod
    def create_mock_payload(points: np.ndarray, **kwargs) -> Dict[str, Any]:
        """Create test payload with point cloud data"""
        payload = {
            "points": points,
            "timestamp": 1234567890.0,
            "node_id": "test_node",
            **kwargs
        }
        return payload
        
    @staticmethod
    def assert_augmented_points(
        original: np.ndarray,
        augmented: np.ndarray, 
        expected_labels: np.ndarray
    ) -> None:
        """Assert that point cloud is properly augmented with labels"""
        # Check shape
        assert augmented.shape == (original.shape[0], original.shape[1] + 1)
        
        # Check original data unchanged
        np.testing.assert_array_equal(augmented[:, :-1], original)
        
        # Check labels in last column
        np.testing.assert_array_equal(augmented[:, -1], expected_labels.astype(np.float32))
        
    @staticmethod
    def assert_detection_boxes(
        boxes: list,
        min_confidence: float = 0.0,
        expected_classes: list = None
    ) -> None:
        """Assert detection boxes meet expected criteria"""
        for box in boxes:
            # Check required fields
            required_fields = ["id", "label", "confidence", "center", "size", "yaw", "color"]
            for field in required_fields:
                assert field in box, f"Missing field: {field}"
                
            # Check confidence threshold
            assert box["confidence"] >= min_confidence
            
            # Check data types
            assert isinstance(box["center"], list) and len(box["center"]) == 3
            assert isinstance(box["size"], list) and len(box["size"]) == 3
            assert isinstance(box["yaw"], (int, float))
            assert isinstance(box["color"], list) and len(box["color"]) == 3
            
            # Check class filtering
            if expected_classes:
                assert box["label"] in expected_classes


# Test markers for different test categories
pytestmark = [
    pytest.mark.ml,  # Mark all tests in this module as ML tests
]


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "ml: mark test as ML functionality test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test" 
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle torch dependency"""
    for item in items:
        # Skip ML tests if torch not available
        if "ml" in item.keywords:
            try:
                import torch
            except ImportError:
                item.add_marker(pytest.mark.skip(reason="PyTorch not available"))


if __name__ == "__main__":
    """Run tests when executed directly"""
    pytest.main([
        "tests/ml/",
        "-v",
        "--tb=short", 
        "-x",  # Stop on first failure
        "--durations=10"  # Show 10 slowest tests
    ])