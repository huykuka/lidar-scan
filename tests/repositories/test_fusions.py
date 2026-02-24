"""Tests for FusionRepository (ORM)."""

import pytest

from app.repositories import FusionRepository
from app.db.migrate import ensure_schema
from app.db.session import init_engine


@pytest.fixture
def fusion_repo(tmp_path, monkeypatch):
    """Creates a FusionRepository with a temporary SQLite DB."""

    db_file = tmp_path / "test_repo_fusions.db"
    database_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    engine = init_engine(database_url)
    ensure_schema(engine)

    yield FusionRepository()


class TestFusionRepository:
    """Test suite for FusionRepository"""
    
    def test_list_empty(self, fusion_repo):
        """Test list returns empty array on fresh database"""
        result = fusion_repo.list()
        assert result == []
    
    def test_upsert_creates_new_fusion(self, fusion_repo):
        """Test upsert creates a new fusion configuration"""
        config = {
            "name": "Main Fusion",
            "topic": "fused_points",
            "sensor_ids": ["sensor1", "sensor2"],
            "pipeline_name": "downsample"
        }
        
        fusion_id = fusion_repo.upsert(config)
        
        assert fusion_id is not None
        assert len(fusion_id) == 32  # UUID hex format
        
        # Verify it was saved
        fusions = fusion_repo.list()
        assert len(fusions) == 1
        assert fusions[0]["name"] == "Main Fusion"
        assert fusions[0]["id"] == fusion_id
        assert fusions[0]["sensor_ids"] == ["sensor1", "sensor2"]
    
    def test_upsert_serializes_sensor_ids_array(self, fusion_repo):
        """Test upsert serializes sensor_ids as JSON"""
        config = {
            "name": "Test Fusion",
            "topic": "test_topic",
            "sensor_ids": ["id1", "id2", "id3"]
        }
        
        fusion_repo.upsert(config)
        fusions = fusion_repo.list()
        
        assert fusions[0]["sensor_ids"] == ["id1", "id2", "id3"]
        assert isinstance(fusions[0]["sensor_ids"], list)
    
    def test_upsert_empty_sensor_ids(self, fusion_repo):
        """Test upsert handles empty sensor_ids array"""
        config = {
            "name": "Empty Fusion",
            "topic": "test",
            "sensor_ids": []
        }
        
        fusion_repo.upsert(config)
        fusions = fusion_repo.list()
        
        assert fusions[0]["sensor_ids"] == []
    
    def test_upsert_updates_existing(self, fusion_repo):
        """Test upsert updates existing fusion by ID"""
        config = {
            "name": "Original",
            "topic": "topic1",
            "sensor_ids": ["s1"]
        }
        
        fusion_id = fusion_repo.upsert(config)
        
        # Update it
        config["id"] = fusion_id
        config["name"] = "Updated"
        config["sensor_ids"] = ["s1", "s2", "s3"]
        config["pipeline_name"] = "reflector"
        
        updated_id = fusion_repo.upsert(config)
        
        assert updated_id == fusion_id
        
        fusions = fusion_repo.list()
        assert len(fusions) == 1
        assert fusions[0]["name"] == "Updated"
        assert fusions[0]["sensor_ids"] == ["s1", "s2", "s3"]
        assert fusions[0]["pipeline_name"] == "reflector"
    
    def test_upsert_preserves_enabled_on_update(self, fusion_repo):
        """Test upsert preserves enabled flag when not provided"""
        config = {
            "name": "Test Fusion",
            "topic": "test",
            "sensor_ids": ["s1"],
            "enabled": False
        }
        
        fusion_id = fusion_repo.upsert(config)
        
        # Update without specifying enabled
        update_config = {
            "id": fusion_id,
            "name": "Updated",
            "topic": "test",
            "sensor_ids": ["s1", "s2"]
        }
        fusion_repo.upsert(update_config)
        
        fusions = fusion_repo.list()
        assert fusions[0]["enabled"] is False
    
    def test_list_converts_enabled_to_bool(self, fusion_repo):
        """Test list converts enabled integer to boolean"""
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"],
            "enabled": True
        }
        
        fusion_repo.upsert(config)
        fusions = fusion_repo.list()
        
        assert fusions[0]["enabled"] is True
        assert isinstance(fusions[0]["enabled"], bool)
    
    def test_set_enabled_true(self, fusion_repo):
        """Test set_enabled enables a fusion"""
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"],
            "enabled": False
        }
        
        fusion_id = fusion_repo.upsert(config)
        fusion_repo.set_enabled(fusion_id, True)
        
        fusions = fusion_repo.list()
        assert fusions[0]["enabled"] is True
    
    def test_set_enabled_false(self, fusion_repo):
        """Test set_enabled disables a fusion"""
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"],
            "enabled": True
        }
        
        fusion_id = fusion_repo.upsert(config)
        fusion_repo.set_enabled(fusion_id, False)
        
        fusions = fusion_repo.list()
        assert fusions[0]["enabled"] is False
    
    def test_delete(self, fusion_repo):
        """Test delete removes a fusion"""
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"]
        }
        
        fusion_id = fusion_repo.upsert(config)
        fusion_repo.delete(fusion_id)
        
        fusions = fusion_repo.list()
        assert len(fusions) == 0
    
    def test_delete_nonexistent(self, fusion_repo):
        """Test delete handles nonexistent ID gracefully"""
        # Should not raise
        fusion_repo.delete("nonexistent_id")
    
    def test_list_multiple_fusions(self, fusion_repo):
        """Test list returns all fusions"""
        configs = [
            {"name": "Fusion1", "topic": "topic1", "sensor_ids": ["s1", "s2"]},
            {"name": "Fusion2", "topic": "topic2", "sensor_ids": ["s3"]},
            {"name": "Fusion3", "topic": "topic3", "sensor_ids": ["s1", "s3", "s4"]},
        ]
        
        for config in configs:
            fusion_repo.upsert(config)
        
        fusions = fusion_repo.list()
        assert len(fusions) == 3
        names = {fusion["name"] for fusion in fusions}
        assert names == {"Fusion1", "Fusion2", "Fusion3"}
    
    def test_upsert_without_pipeline(self, fusion_repo):
        """Test upsert with no pipeline_name"""
        config = {
            "name": "Simple Fusion",
            "topic": "fused",
            "sensor_ids": ["s1", "s2"]
        }
        
        fusion_repo.upsert(config)
        fusions = fusion_repo.list()
        
        # pipeline_name can be None or empty
        assert fusions[0]["pipeline_name"] is None or fusions[0]["pipeline_name"] == ""
