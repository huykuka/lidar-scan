"""
Test suite for ML Model Registry

Tests singleton behavior, async model loading, LRU eviction, and inference execution.
"""

import pytest
import numpy as np
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Skip entire module if torch not available
pytest.importorskip("torch")

from app.modules.ml.model_registry import MLModelRegistry, ModelStatus, LoadedModel


class TestMLModelRegistry:
    """Test cases for MLModelRegistry singleton"""

    def setup_method(self):
        """Reset singleton for each test"""
        MLModelRegistry._instance = None
        
    def test_singleton_pattern(self):
        """Test that MLModelRegistry follows singleton pattern"""
        registry1 = MLModelRegistry.get_instance()
        registry2 = MLModelRegistry.get_instance()
        
        assert registry1 is registry2
        assert isinstance(registry1, MLModelRegistry)
        
    def test_make_model_key(self):
        """Test model key generation"""
        registry = MLModelRegistry.get_instance()
        key = registry._make_model_key("RandLANet", "SemanticKITTI")
        assert key == "randlanet__semantickitti"
        
    @pytest.mark.asyncio
    async def test_model_loading_flow(self):
        """Test complete model loading workflow"""
        registry = MLModelRegistry.get_instance()
        
        with patch.object(registry, '_load_model_async') as mock_load:
            model = await registry.get_or_load("RandLANet", "SemanticKITTI", "cpu")
            
            assert model.model_name == "RandLANet"
            assert model.dataset_name == "SemanticKITTI"
            assert model.device == "cpu"
            assert model.status == ModelStatus.DOWNLOADING
            mock_load.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_model_caching(self):
        """Test that loaded models are cached"""
        registry = MLModelRegistry.get_instance()
        
        # Mock a ready model
        mock_model = LoadedModel(
            model_key="randlanet__semantickitti",
            model_name="RandLANet",
            dataset_name="SemanticKITTI", 
            device="cpu",
            status=ModelStatus.READY
        )
        registry.models["randlanet__semantickitti"] = mock_model
        
        model = await registry.get_or_load("RandLANet", "SemanticKITTI", "cpu")
        assert model is mock_model
        
    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when at capacity"""
        registry = MLModelRegistry.get_instance()
        registry.MAX_LOADED_MODELS = 1
        
        # Add first model
        model1 = LoadedModel(
            model_key="model1",
            model_name="Model1",
            dataset_name="Dataset1",
            device="cpu", 
            status=ModelStatus.READY
        )
        registry.models["model1"] = model1
        registry._update_access_order("model1")
        
        with patch.object(registry, '_unload_model') as mock_unload:
            with patch.object(registry, '_load_model_async'):
                # Add second model should trigger eviction
                await registry.get_or_load("Model2", "Dataset2", "cpu")
                mock_unload.assert_called_once_with("model1")
                
    def test_model_status_reporting(self):
        """Test model status reporting"""
        registry = MLModelRegistry.get_instance()
        
        # Test not loaded
        status = registry.get_model_status("nonexistent")
        assert status["status"] == "not_loaded"
        
        # Test loaded model
        mock_model = LoadedModel(
            model_key="test_model",
            model_name="TestModel", 
            dataset_name="TestDataset",
            device="cpu",
            status=ModelStatus.READY,
            inference_count=10,
            total_inference_ms=1000.0
        )
        registry.models["test_model"] = mock_model
        
        status = registry.get_model_status("test_model")
        assert status["status"] == "ready"
        assert status["device"] == "cpu"
        assert status["inference_count"] == 10
        assert status["avg_inference_ms"] == 100.0
        
    @pytest.mark.asyncio  
    async def test_inference_execution(self):
        """Test inference execution with metrics tracking"""
        registry = MLModelRegistry.get_instance()
        
        # Mock pipeline with inference method
        mock_pipeline = Mock()
        mock_pipeline.run_inference.return_value = {
            "predict_labels": np.array([1, 2, 3])
        }
        
        mock_model = LoadedModel(
            model_key="test_model",
            model_name="TestModel",
            dataset_name="TestDataset", 
            device="cpu",
            status=ModelStatus.READY,
            pipeline=mock_pipeline
        )
        registry.models["test_model"] = mock_model
        
        input_data = {"point": np.random.rand(100, 3)}
        result = await registry.run_inference("test_model", input_data)
        
        assert "predict_labels" in result
        assert mock_model.inference_count == 1
        assert mock_model.total_inference_ms > 0
        
    @pytest.mark.asyncio
    async def test_inference_error_handling(self):
        """Test inference error handling"""
        registry = MLModelRegistry.get_instance()
        
        # Test model not loaded
        with pytest.raises(ValueError, match="not loaded"):
            await registry.run_inference("nonexistent", {})
            
        # Test model not ready
        mock_model = LoadedModel(
            model_key="loading_model", 
            model_name="LoadingModel",
            dataset_name="TestDataset",
            device="cpu",
            status=ModelStatus.LOADING
        )
        registry.models["loading_model"] = mock_model
        
        with pytest.raises(RuntimeError, match="not ready"):
            await registry.run_inference("loading_model", {})
            
    def test_synchronous_unload(self):
        """Test synchronous model unloading"""
        registry = MLModelRegistry.get_instance()
        
        # Test unload nonexistent model
        result = registry.unload_model_sync("nonexistent")
        assert result is False
        
        # Test unload existing model
        mock_model = LoadedModel(
            model_key="test_model",
            model_name="TestModel",
            dataset_name="TestDataset", 
            device="cpu",
            status=ModelStatus.READY
        )
        registry.models["test_model"] = mock_model
        registry.access_order = ["test_model"]
        
        result = registry.unload_model_sync("test_model")
        assert result is True
        assert "test_model" not in registry.models
        assert "test_model" not in registry.access_order


class TestLoadedModel:
    """Test cases for LoadedModel dataclass"""
    
    def test_loaded_model_creation(self):
        """Test LoadedModel instantiation"""
        model = LoadedModel(
            model_key="test_key",
            model_name="TestModel", 
            dataset_name="TestDataset",
            device="cpu",
            status=ModelStatus.NOT_LOADED
        )
        
        assert model.model_key == "test_key"
        assert model.model_name == "TestModel"
        assert model.dataset_name == "TestDataset" 
        assert model.device == "cpu"
        assert model.status == ModelStatus.NOT_LOADED
        assert model.inference_count == 0
        assert model.total_inference_ms == 0.0


@pytest.mark.integration
class TestMLRegistryIntegration:
    """Integration tests for ML registry with mock dependencies"""
    
    def setup_method(self):
        """Reset singleton for each test"""
        MLModelRegistry._instance = None
        
    @pytest.mark.asyncio
    async def test_full_loading_cycle(self):
        """Test complete model loading and inference cycle"""
        registry = MLModelRegistry.get_instance()
        
        # Mock the loading pipeline
        with patch.object(registry, '_download_weights', return_value=None):
            with patch.object(registry, '_load_pipeline') as mock_load_pipeline:
                mock_pipeline = Mock()
                mock_pipeline.run_inference.return_value = {"predict_labels": np.array([0, 1, 0])}
                mock_load_pipeline.return_value = mock_pipeline
                
                # Start loading
                model = await registry.get_or_load("RandLANet", "SemanticKITTI", "cpu")
                
                # Simulate loading completion
                await registry._load_model_async(model)
                
                # Test inference
                input_data = {"point": np.random.rand(100, 3)}
                result = await registry.run_inference(model.model_key, input_data)
                
                assert model.status == ModelStatus.READY
                assert "predict_labels" in result
                assert model.inference_count == 1