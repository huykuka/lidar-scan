"""
ML module tests package

This package contains comprehensive tests for the ML functionality:
- test_model_registry.py: Tests for MLModelRegistry singleton and model management
- test_ml_nodes.py: Tests for ML DAG nodes (segmentation, detection)
- test_ml_api.py: Tests for REST API endpoints
- conftest.py: Test configuration, fixtures, and utilities

Run all ML tests:
    pytest tests/ml/ -v

Run specific test categories:
    pytest tests/ml/ -m "not slow" -v          # Skip slow tests
    pytest tests/ml/ -m integration -v         # Only integration tests
    pytest tests/ml/test_ml_api.py -v          # Only API tests

Requirements:
- PyTorch must be installed (pip install -r requirements-ml.txt)
- Tests are automatically skipped if torch is unavailable
"""

# Version info
__version__ = "1.0.0"
__test_modules__ = [
    "test_model_registry",
    "test_ml_nodes", 
    "test_ml_api"
]