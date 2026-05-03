"""Tests for the detection model store."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from app.modules.detection.model_store import ModelStore


@pytest.fixture
def store(tmp_path: Path) -> ModelStore:
    """Create a ModelStore backed by a temporary directory."""
    return ModelStore(models_dir=tmp_path)


class TestModelStoreBasic:
    def test_empty_store(self, store: ModelStore) -> None:
        assert store.list_models() == []
        assert store.get_checkpoint_options() == []

    def test_add_model(self, store: ModelStore) -> None:
        entry = store.add_model(
            filename="test_weights.pth",
            data=b"fake model weights",
            display_name="Test Model",
            model_type="pointpillars",
        )
        assert entry.id
        assert entry.display_name == "Test Model"
        assert entry.model_type == "pointpillars"
        assert entry.file_size == len(b"fake model weights")

    def test_list_models_returns_entries(self, store: ModelStore) -> None:
        store.add_model(filename="a.pth", data=b"aaa", display_name="Model A")
        store.add_model(filename="b.pth", data=b"bbb", display_name="Model B")
        models = store.list_models()
        assert len(models) == 2
        names = {m.display_name for m in models}
        assert names == {"Model A", "Model B"}

    def test_get_model(self, store: ModelStore) -> None:
        entry = store.add_model(filename="w.pth", data=b"data")
        result = store.get_model(entry.id)
        assert result is not None
        assert result.id == entry.id

    def test_get_model_not_found(self, store: ModelStore) -> None:
        assert store.get_model("nonexistent") is None

    def test_get_checkpoint_path(self, store: ModelStore) -> None:
        entry = store.add_model(filename="w.pth", data=b"data")
        path = store.get_checkpoint_path(entry.id)
        assert path is not None
        assert os.path.isfile(path)

    def test_get_checkpoint_path_not_found(self, store: ModelStore) -> None:
        assert store.get_checkpoint_path("missing") is None

    def test_delete_model(self, store: ModelStore) -> None:
        entry = store.add_model(filename="w.pth", data=b"data")
        file_path = store.get_checkpoint_path(entry.id)
        assert file_path is not None
        assert os.path.isfile(file_path)

        assert store.delete_model(entry.id) is True
        assert store.get_model(entry.id) is None
        assert not os.path.isfile(file_path)

    def test_delete_model_not_found(self, store: ModelStore) -> None:
        assert store.delete_model("missing") is False


class TestModelStoreValidation:
    def test_rejects_invalid_extension(self, store: ModelStore) -> None:
        with pytest.raises(ValueError, match="Unsupported file type"):
            store.add_model(filename="evil.exe", data=b"bad")

    def test_accepts_all_valid_extensions(self, store: ModelStore) -> None:
        for ext in (".pth", ".pt", ".onnx", ".bin"):
            entry = store.add_model(
                filename=f"model{ext}",
                data=b"data",
                display_name=f"Model {ext}",
            )
            assert entry.id


class TestModelStorePersistence:
    def test_manifest_persists(self, tmp_path: Path) -> None:
        store1 = ModelStore(models_dir=tmp_path)
        entry = store1.add_model(filename="w.pth", data=b"weights")

        # Create a new store reading the same directory
        store2 = ModelStore(models_dir=tmp_path)
        result = store2.get_model(entry.id)
        assert result is not None
        assert result.display_name == entry.display_name

    def test_checkpoint_options(self, store: ModelStore) -> None:
        store.add_model(filename="a.pth", data=b"a", display_name="Alpha")
        store.add_model(filename="b.pth", data=b"b", display_name="Beta")
        options = store.get_checkpoint_options()
        assert len(options) == 2
        labels = {o["label"] for o in options}
        assert labels == {"Alpha", "Beta"}
        assert all("value" in o for o in options)
