"""
Test suite for ML API endpoints

Tests REST API functionality, model management, and error handling.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import json

# Skip entire module if torch not available  
pytest.importorskip("torch")

from app.main import app
from app.modules.ml.model_registry import MLModelRegistry, ModelStatus, LoadedModel
from app.api.v1.ml.schemas import MLModelInfo, MLModelStatus


class TestMLAPI:
    """Test cases for ML REST API endpoints"""

    def setup_method(self):
        """Setup test client and reset registry"""
        self.client = TestClient(app)
        MLModelRegistry._instance = None
        
    def test_get_models_torch_unavailable(self):
        """Test /models endpoint when torch is unavailable"""
        with patch('app.api.v1.ml.ML_AVAILABLE', False):
            response = self.client.get("/api/v1/ml/models")
            
        assert response.status_code == 503
        assert "PyTorch" in response.json()["detail"]
        
    def test_get_models_success(self):
        """Test successful /models endpoint response"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "not_loaded"}
                mock_get_instance.return_value = mock_registry
                
                response = self.client.get("/api/v1/ml/models")
                
        assert response.status_code == 200
        models = response.json()
        assert len(models) == 4  # 4 predefined models
        
        # Check first model structure
        model = models[0]
        assert model["model_key"] == "randlanet_semantickitti"
        assert model["model_name"] == "RandLANet"
        assert model["task"] == "semantic_segmentation"
        assert model["num_classes"] == 19
        
    def test_get_model_status_not_found(self):
        """Test model status for non-existent model"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            response = self.client.get("/api/v1/ml/models/nonexistent/status")
            
        assert response.status_code == 404
        assert "not found in catalog" in response.json()["detail"]
        
    def test_get_model_status_success(self):
        """Test successful model status retrieval"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {
                    "status": "ready",
                    "device": "cpu",
                    "loaded_at": 1234567890.0,
                    "inference_count": 5,
                    "avg_inference_ms": 125.5,
                    "last_error": None
                }
                mock_get_instance.return_value = mock_registry
                
                response = self.client.get("/api/v1/ml/models/randlanet_semantickitti/status")
                
        assert response.status_code == 200
        status = response.json()
        assert status["model_key"] == "randlanet_semantickitti"
        assert status["status"] == "ready"
        assert status["device"] == "cpu"
        assert status["inference_count"] == 5
        assert status["avg_inference_ms"] == 125.5
        
    def test_load_model_success(self):
        """Test successful model loading initiation"""
        load_request = {"device": "cuda:0"}
        
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "not_loaded"}
                mock_registry.get_or_load.return_value = Mock()  # Async mock
                mock_get_instance.return_value = mock_registry
                
                response = self.client.post(
                    "/api/v1/ml/models/randlanet_semantickitti/load",
                    json=load_request
                )
                
        assert response.status_code == 202
        result = response.json()
        assert "loading initiated" in result["message"]
        assert result["device"] == "cuda:0"
        
    def test_load_model_already_loaded(self):
        """Test loading model that's already loaded"""
        load_request = {"device": "cpu"}
        
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "ready"}
                mock_get_instance.return_value = mock_registry
                
                response = self.client.post(
                    "/api/v1/ml/models/randlanet_semantickitti/load",
                    json=load_request
                )
                
        assert response.status_code == 409
        assert "already loaded" in response.json()["detail"]
        
    def test_load_model_invalid_key(self):
        """Test loading non-existent model"""
        load_request = {"device": "cpu"}
        
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            response = self.client.post(
                "/api/v1/ml/models/invalid_model/load",
                json=load_request
            )
            
        assert response.status_code == 404
        assert "not found in catalog" in response.json()["detail"]
        
    def test_unload_model_success(self):
        """Test successful model unloading"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "ready"}
                mock_registry.unload_model_sync.return_value = True
                mock_get_instance.return_value = mock_registry
                
                response = self.client.delete("/api/v1/ml/models/randlanet_semantickitti")
                
        assert response.status_code == 200
        result = response.json()
        assert "unloaded successfully" in result["message"]
        
    def test_unload_model_not_loaded(self):
        """Test unloading model that's not loaded"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "not_loaded"}
                mock_registry.unload_model_sync.return_value = False
                mock_get_instance.return_value = mock_registry
                
                response = self.client.delete("/api/v1/ml/models/randlanet_semantickitti")
                
        assert response.status_code == 404
        assert "not currently loaded" in response.json()["detail"]


class TestMLSchemas:
    """Test cases for ML API Pydantic schemas"""
    
    def test_ml_model_info_schema(self):
        """Test MLModelInfo schema validation"""
        model_data = {
            "model_key": "test_model",
            "model_name": "TestModel",
            "dataset_name": "TestDataset",
            "task": "semantic_segmentation",
            "num_classes": 10,
            "class_names": ["class1", "class2"],
            "color_map": [[255, 0, 0], [0, 255, 0]], 
            "weight_url": "http://example.com/weights.pth",
            "weight_filename": "weights.pth",
            "weight_size_mb": 50.0,
            "config_file": "config.yml",
            "status": "ready"
        }
        
        model_info = MLModelInfo(**model_data)
        assert model_info.model_key == "test_model"
        assert model_info.task == "semantic_segmentation"
        assert len(model_info.class_names) == 2
        
    def test_ml_model_status_schema(self):
        """Test MLModelStatus schema validation"""
        status_data = {
            "model_key": "test_model",
            "status": "ready",
            "device": "cuda:0",
            "loaded_at": 1234567890.0,
            "weight_cached": True,
            "download_progress_pct": 100.0,
            "inference_count": 25,
            "avg_inference_ms": 45.2,
            "last_error": None
        }
        
        model_status = MLModelStatus(**status_data)
        assert model_status.model_key == "test_model"
        assert model_status.status == "ready"
        assert model_status.device == "cuda:0"
        assert model_status.inference_count == 25
        
    def test_ml_load_request_schema(self):
        """Test MLLoadRequest schema validation"""
        request_data = {"device": "cpu"}
        load_request = MLModelStatus(**request_data)
        assert load_request.device == "cpu"
        
        # Test with GPU device
        gpu_data = {"device": "cuda:1"}
        gpu_request = MLModelStatus(**gpu_data) 
        assert gpu_request.device == "cuda:1"


@pytest.mark.integration
class TestMLAPIIntegration:
    """Integration tests for ML API with real registry"""
    
    def setup_method(self):
        """Setup test client and registry"""
        self.client = TestClient(app)
        MLModelRegistry._instance = None
        
    @pytest.mark.asyncio
    async def test_full_model_lifecycle(self):
        """Test complete model load -> status -> unload cycle"""
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            
            # 1. Get initial models list
            response = self.client.get("/api/v1/ml/models")
            assert response.status_code == 200
            models = response.json()
            model_key = models[0]["model_key"]
            
            # 2. Check initial status (not loaded)
            response = self.client.get(f"/api/v1/ml/models/{model_key}/status")
            assert response.status_code == 200
            status = response.json()
            assert status["status"] == "not_loaded"
            
            # 3. Initiate loading with mock registry
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "not_loaded"}
                mock_registry.get_or_load.return_value = Mock()
                mock_get_instance.return_value = mock_registry
                
                load_response = self.client.post(
                    f"/api/v1/ml/models/{model_key}/load",
                    json={"device": "cpu"}
                )
                assert load_response.status_code == 202
                
            # 4. Mock loaded state and check status
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {
                    "status": "ready",
                    "device": "cpu",
                    "loaded_at": 1234567890.0,
                    "inference_count": 0,
                    "avg_inference_ms": 0.0,
                    "last_error": None
                }
                mock_get_instance.return_value = mock_registry
                
                status_response = self.client.get(f"/api/v1/ml/models/{model_key}/status")
                assert status_response.status_code == 200
                status = status_response.json()
                assert status["status"] == "ready"
                
            # 5. Unload model
            with patch.object(MLModelRegistry, 'get_instance') as mock_get_instance:
                mock_registry = Mock()
                mock_registry.get_model_status.return_value = {"status": "ready"}
                mock_registry.unload_model_sync.return_value = True
                mock_get_instance.return_value = mock_registry
                
                unload_response = self.client.delete(f"/api/v1/ml/models/{model_key}")
                assert unload_response.status_code == 200
                
    def test_error_handling(self):
        """Test API error handling with various failure scenarios"""
        
        # Test 404 for invalid model key
        response = self.client.get("/api/v1/ml/models/invalid_key/status")
        assert response.status_code == 404
        
        # Test 503 when torch unavailable
        with patch('app.api.v1.ml.ML_AVAILABLE', False):
            response = self.client.get("/api/v1/ml/models")
            assert response.status_code == 503
            
        # Test 500 when registry fails
        with patch('app.api.v1.ml.ML_AVAILABLE', True):
            with patch.object(MLModelRegistry, 'get_instance', side_effect=Exception("Registry error")):
                response = self.client.get("/api/v1/ml/models")
                assert response.status_code == 500