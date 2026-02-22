"""Tests for ORM-based repositories."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.migrate import ensure_schema
from app.db.session import init_engine
from app.repositories.lidars_orm import LidarORMRepository
from app.repositories.fusions_orm import FusionORMRepository


@pytest.fixture
def test_engine(tmp_path):
    """Create a temporary test database"""
    db_file = tmp_path / "test_orm.db"
    engine = init_engine(f"sqlite:///{db_file}")
    ensure_schema(engine)
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test database session"""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSessionLocal()
    yield session
    session.close()


class TestLidarORMRepository:
    """Tests for LidarORMRepository"""
    
    def test_list_empty(self, test_session):
        """Test list returns empty on fresh database"""
        repo = LidarORMRepository(test_session)
        result = repo.list()
        assert result == []
    
    def test_upsert_creates_new(self, test_session):
        """Test upsert creates new lidar"""
        repo = LidarORMRepository(test_session)
        config = {
            "name": "Test Lidar",
            "launch_args": "test_args"
        }
        
        lidar_id = repo.upsert(config)
        
        assert lidar_id is not None
        lidars = repo.list()
        assert len(lidars) == 1
        assert lidars[0]["name"] == "Test Lidar"
    
    def test_upsert_updates_existing(self, test_session):
        """Test upsert updates existing lidar"""
        repo = LidarORMRepository(test_session)
        config = {"name": "Original", "launch_args": "args"}
        
        lidar_id = repo.upsert(config)
        config["id"] = lidar_id
        config["name"] = "Updated"
        
        updated_id = repo.upsert(config)
        
        assert updated_id == lidar_id
        lidars = repo.list()
        assert len(lidars) == 1
        assert lidars[0]["name"] == "Updated"
    
    def test_get_by_id(self, test_session):
        """Test get_by_id returns correct lidar"""
        repo = LidarORMRepository(test_session)
        config = {"name": "Test", "launch_args": "args"}
        
        lidar_id = repo.upsert(config)
        lidar = repo.get_by_id(lidar_id)
        
        assert lidar is not None
        assert lidar["id"] == lidar_id
        assert lidar["name"] == "Test"
    
    def test_get_by_id_nonexistent(self, test_session):
        """Test get_by_id returns None for nonexistent ID"""
        repo = LidarORMRepository(test_session)
        result = repo.get_by_id("nonexistent")
        assert result is None
    
    def test_set_enabled(self, test_session):
        """Test set_enabled updates enabled flag"""
        repo = LidarORMRepository(test_session)
        config = {"name": "Test", "launch_args": "args", "enabled": True}
        
        lidar_id = repo.upsert(config)
        repo.set_enabled(lidar_id, False)
        
        lidar = repo.get_by_id(lidar_id)
        assert lidar is not None
        assert lidar["enabled"] is False
    
    def test_delete(self, test_session):
        """Test delete removes lidar"""
        repo = LidarORMRepository(test_session)
        config = {"name": "Test", "launch_args": "args"}
        
        lidar_id = repo.upsert(config)
        repo.delete(lidar_id)
        
        lidars = repo.list()
        assert len(lidars) == 0
    
    def test_topic_prefix_generation(self, test_session):
        """Test automatic topic_prefix generation"""
        repo = LidarORMRepository(test_session)
        config = {"name": "Front Lidar #1", "launch_args": "args"}
        
        repo.upsert(config)
        lidars = repo.list()
        
        assert lidars[0]["topic_prefix"] == "Front_Lidar_1"
    
    def test_topic_prefix_collision_handling(self, test_session):
        """Test topic_prefix collision resolution"""
        repo = LidarORMRepository(test_session)
        
        config1 = {"name": "Sensor", "launch_args": "args1"}
        id1 = repo.upsert(config1)
        
        config2 = {"name": "Sensor", "launch_args": "args2"}
        id2 = repo.upsert(config2)
        
        lidars = repo.list()
        prefixes = {l["topic_prefix"] for l in lidars}
        
        assert len(prefixes) == 2  # Should have unique prefixes
    
    def test_pose_parameters(self, test_session):
        """Test pose parameters are stored correctly"""
        repo = LidarORMRepository(test_session)
        config = {
            "name": "Test",
            "launch_args": "args",
            "x": 1.5, "y": -2.0, "z": 0.8,
            "roll": 0.1, "pitch": -0.05, "yaw": 1.57
        }
        
        lidar_id = repo.upsert(config)
        lidar = repo.get_by_id(lidar_id)
        assert lidar is not None
        
        assert lidar["x"] == 1.5
        assert lidar["y"] == -2.0
        assert lidar["z"] == 0.8
        assert lidar["roll"] == 0.1
        assert lidar["pitch"] == -0.05
        assert lidar["yaw"] == 1.57


class TestFusionORMRepository:
    """Tests for FusionORMRepository"""
    
    def test_list_empty(self, test_session):
        """Test list returns empty on fresh database"""
        repo = FusionORMRepository(test_session)
        result = repo.list()
        assert result == []
    
    def test_upsert_creates_new(self, test_session):
        """Test upsert creates new fusion"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Test Fusion",
            "topic": "fused",
            "sensor_ids": ["s1", "s2"]
        }
        
        fusion_id = repo.upsert(config)
        
        assert fusion_id is not None
        fusions = repo.list()
        assert len(fusions) == 1
        assert fusions[0]["name"] == "Test Fusion"
        assert fusions[0]["sensor_ids"] == ["s1", "s2"]
    
    def test_upsert_updates_existing(self, test_session):
        """Test upsert updates existing fusion"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Original",
            "topic": "topic1",
            "sensor_ids": ["s1"]
        }
        
        fusion_id = repo.upsert(config)
        config["id"] = fusion_id
        config["name"] = "Updated"
        config["sensor_ids"] = ["s1", "s2", "s3"]
        
        updated_id = repo.upsert(config)
        
        assert updated_id == fusion_id
        fusions = repo.list()
        assert len(fusions) == 1
        assert fusions[0]["name"] == "Updated"
        assert fusions[0]["sensor_ids"] == ["s1", "s2", "s3"]
    
    def test_get_by_id(self, test_session):
        """Test get_by_id returns correct fusion"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"]
        }
        
        fusion_id = repo.upsert(config)
        fusion = repo.get_by_id(fusion_id)
        
        assert fusion is not None
        assert fusion["id"] == fusion_id
        assert fusion["name"] == "Test"
    
    def test_get_by_id_nonexistent(self, test_session):
        """Test get_by_id returns None for nonexistent ID"""
        repo = FusionORMRepository(test_session)
        result = repo.get_by_id("nonexistent")
        assert result is None
    
    def test_set_enabled(self, test_session):
        """Test set_enabled updates enabled flag"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"],
            "enabled": True
        }
        
        fusion_id = repo.upsert(config)
        repo.set_enabled(fusion_id, False)
        
        fusion = repo.get_by_id(fusion_id)
        assert fusion is not None
        assert fusion["enabled"] is False
    
    def test_delete(self, test_session):
        """Test delete removes fusion"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["s1"]
        }
        
        fusion_id = repo.upsert(config)
        repo.delete(fusion_id)
        
        fusions = repo.list()
        assert len(fusions) == 0
    
    def test_sensor_ids_serialization(self, test_session):
        """Test sensor_ids array is properly serialized/deserialized"""
        repo = FusionORMRepository(test_session)
        config = {
            "name": "Test",
            "topic": "test",
            "sensor_ids": ["id1", "id2", "id3"]
        }
        
        fusion_id = repo.upsert(config)
        fusion = repo.get_by_id(fusion_id)
        assert fusion is not None
        
        assert fusion["sensor_ids"] == ["id1", "id2", "id3"]
        assert isinstance(fusion["sensor_ids"], list)
