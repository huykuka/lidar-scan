"""Unit tests for the detection module base classes and model registry."""
import numpy as np
import pytest

from app.modules.detection.models.base import (
    Detection3D,
    DetectionModel,
    MODEL_REGISTRY,
    get_available_models,
    register_model,
)


class TestDetection3D:
    def test_default_values(self):
        det = Detection3D(
            center=[1.0, 2.0, 3.0],
            size=[4.0, 2.0, 1.5],
        )
        assert det.rotation == [0.0, 0.0, 0.0]
        assert det.label == "unknown"
        assert det.score == 0.0
        assert det.points_in_box == 0

    def test_to_dict(self):
        det = Detection3D(
            center=[1.0, 2.0, 3.0],
            size=[4.0, 2.0, 1.5],
            rotation=[0.0, 0.0, 0.5],
            label="Car",
            score=0.92345,
            points_in_box=150,
        )
        d = det.to_dict()
        assert d["center"] == [1.0, 2.0, 3.0]
        assert d["size"] == [4.0, 2.0, 1.5]
        assert d["rotation"] == [0.0, 0.0, 0.5]
        assert d["label"] == "Car"
        assert d["score"] == 0.9234  # rounded to 4 decimal places
        assert d["points_in_box"] == 150

    def test_to_dict_score_rounding(self):
        det = Detection3D(center=[0, 0, 0], size=[1, 1, 1], score=0.123456789)
        assert det.to_dict()["score"] == 0.1235  # round(0.123456789, 4)


class TestModelRegistry:
    def test_register_model_decorator(self):
        initial_count = len(MODEL_REGISTRY)

        @register_model("test_model_xyz", display_name="Test XYZ", description="A test model")
        class _TestModel(DetectionModel):
            def load(self, checkpoint_path, device="cpu"):
                pass

            def detect(self, points, **kwargs):
                return []

            @property
            def supported_classes(self):
                return ["test"]

        assert "test_model_xyz" in MODEL_REGISTRY
        entry = MODEL_REGISTRY["test_model_xyz"]
        assert entry.display_name == "Test XYZ"
        assert entry.description == "A test model"

        instance = entry.builder()
        assert isinstance(instance, DetectionModel)
        assert instance.supported_classes == ["test"]

        # Clean up
        del MODEL_REGISTRY["test_model_xyz"]

    def test_get_available_models_format(self):
        models = get_available_models()
        assert isinstance(models, list)
        for m in models:
            assert "label" in m
            assert "value" in m

    def test_is_loaded_default_false(self):
        class _Dummy(DetectionModel):
            def load(self, checkpoint_path, device="cpu"):
                pass

            def detect(self, points, **kwargs):
                return []

            @property
            def supported_classes(self):
                return []

        d = _Dummy()
        assert d.is_loaded is False
