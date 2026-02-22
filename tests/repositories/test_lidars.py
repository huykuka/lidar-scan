"""Tests for LidarRepository (ORM)."""

import pytest

from app.repositories import LidarRepository
from app.db.migrate import ensure_schema
from app.db.session import init_engine


@pytest.fixture
def lidar_repo(tmp_path, monkeypatch):
    """Creates a LidarRepository with a temporary SQLite DB."""

    db_file = tmp_path / "test_repo_lidars.db"
    database_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    engine = init_engine(database_url)
    ensure_schema(engine)

    yield LidarRepository()


class TestLidarRepository:
    """Test suite for LidarRepository"""
    
    def test_list_empty(self, lidar_repo):
        """Test list returns empty array on fresh database"""
        result = lidar_repo.list()
        assert result == []
    
    def test_upsert_creates_new_lidar(self, lidar_repo):
        """Test upsert creates a new lidar configuration"""
        config = {
            "name": "Front Lidar",
            "launch_args": "sensor_ip:=192.168.1.10",
            "pipeline_name": "downsample",
            "mode": "real",
            "x": 1.0,
            "y": 0.0,
            "z": 0.5,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0
        }
        
        sensor_id = lidar_repo.upsert(config)
        
        assert sensor_id is not None
        assert len(sensor_id) == 32  # UUID hex format
        
        # Verify it was saved
        lidars = lidar_repo.list()
        assert len(lidars) == 1
        assert lidars[0]["name"] == "Front Lidar"
        assert lidars[0]["id"] == sensor_id
    
    def test_upsert_generates_topic_prefix(self, lidar_repo):
        """Test upsert auto-generates topic_prefix from name"""
        config = {
            "name": "Front Lidar #1",
            "launch_args": "test",
        }
        
        sensor_id = lidar_repo.upsert(config)
        lidars = lidar_repo.list()
        
        assert lidars[0]["topic_prefix"] == "Front_Lidar_1"
    
    def test_upsert_preserves_topic_prefix(self, lidar_repo):
        """Test upsert preserves custom topic_prefix"""
        config = {
            "name": "Test Sensor",
            "launch_args": "test",
            "topic_prefix": "custom_prefix"
        }
        
        sensor_id = lidar_repo.upsert(config)
        lidars = lidar_repo.list()
        
        assert lidars[0]["topic_prefix"] == "custom_prefix"
    
    def test_upsert_handles_topic_collision(self, lidar_repo):
        """Test upsert handles topic_prefix collisions"""
        # Create first lidar
        config1 = {
            "name": "Sensor",
            "launch_args": "test1",
        }
        id1 = lidar_repo.upsert(config1)
        
        # Create second with same name
        config2 = {
            "name": "Sensor",
            "launch_args": "test2",
        }
        id2 = lidar_repo.upsert(config2)
        
        lidars = lidar_repo.list()
        assert len(lidars) == 2
        
        prefix1 = lidars[0]["topic_prefix"]
        prefix2 = lidars[1]["topic_prefix"]
        
        # Prefixes should be different
        assert prefix1 != prefix2
        assert prefix1 == "Sensor"
        assert prefix2.startswith("Sensor_")
    
    def test_upsert_updates_existing(self, lidar_repo):
        """Test upsert updates existing lidar by ID"""
        config = {
            "name": "Original Name",
            "launch_args": "test",
        }
        
        sensor_id = lidar_repo.upsert(config)
        
        # Update it
        config["id"] = sensor_id
        config["name"] = "Updated Name"
        config["x"] = 5.0
        
        updated_id = lidar_repo.upsert(config)
        
        assert updated_id == sensor_id
        
        lidars = lidar_repo.list()
        assert len(lidars) == 1
        assert lidars[0]["name"] == "Updated Name"
        assert lidars[0]["x"] == 5.0
    
    def test_upsert_preserves_enabled_on_update(self, lidar_repo):
        """Test upsert preserves enabled flag when not provided"""
        config = {
            "name": "Test Sensor",
            "launch_args": "test",
            "enabled": False
        }
        
        sensor_id = lidar_repo.upsert(config)
        
        # Update without specifying enabled
        update_config = {
            "id": sensor_id,
            "name": "Updated Name",
            "launch_args": "test",
        }
        lidar_repo.upsert(update_config)
        
        lidars = lidar_repo.list()
        assert lidars[0]["enabled"] is False
    
    def test_upsert_converts_enabled_to_bool(self, lidar_repo):
        """Test list converts enabled integer to boolean"""
        config = {
            "name": "Test",
            "launch_args": "test",
            "enabled": True
        }
        
        lidar_repo.upsert(config)
        lidars = lidar_repo.list()
        
        assert lidars[0]["enabled"] is True
        assert isinstance(lidars[0]["enabled"], bool)
    
    def test_set_enabled_true(self, lidar_repo):
        """Test set_enabled enables a lidar"""
        config = {
            "name": "Test",
            "launch_args": "test",
            "enabled": False
        }
        
        sensor_id = lidar_repo.upsert(config)
        lidar_repo.set_enabled(sensor_id, True)
        
        lidars = lidar_repo.list()
        assert lidars[0]["enabled"] is True
    
    def test_set_enabled_false(self, lidar_repo):
        """Test set_enabled disables a lidar"""
        config = {
            "name": "Test",
            "launch_args": "test",
            "enabled": True
        }
        
        sensor_id = lidar_repo.upsert(config)
        lidar_repo.set_enabled(sensor_id, False)
        
        lidars = lidar_repo.list()
        assert lidars[0]["enabled"] is False
    
    def test_delete(self, lidar_repo):
        """Test delete removes a lidar"""
        config = {
            "name": "Test",
            "launch_args": "test",
        }
        
        sensor_id = lidar_repo.upsert(config)
        lidar_repo.delete(sensor_id)
        
        lidars = lidar_repo.list()
        assert len(lidars) == 0
    
    def test_delete_nonexistent(self, lidar_repo):
        """Test delete handles nonexistent ID gracefully"""
        # Should not raise
        lidar_repo.delete("nonexistent_id")
    
    def test_list_multiple_lidars(self, lidar_repo):
        """Test list returns all lidars"""
        configs = [
            {"name": "Front", "launch_args": "test1"},
            {"name": "Rear", "launch_args": "test2"},
            {"name": "Left", "launch_args": "test3"},
        ]
        
        for config in configs:
            lidar_repo.upsert(config)
        
        lidars = lidar_repo.list()
        assert len(lidars) == 3
        names = {lidar["name"] for lidar in lidars}
        assert names == {"Front", "Rear", "Left"}
    
    def test_upsert_all_pose_parameters(self, lidar_repo):
        """Test upsert stores all pose parameters correctly"""
        config = {
            "name": "Test",
            "launch_args": "test",
            "x": 1.5,
            "y": -2.0,
            "z": 0.8,
            "roll": 0.1,
            "pitch": -0.05,
            "yaw": 1.57
        }
        
        lidar_repo.upsert(config)
        lidars = lidar_repo.list()
        
        assert lidars[0]["x"] == 1.5
        assert lidars[0]["y"] == -2.0
        assert lidars[0]["z"] == 0.8
        assert lidars[0]["roll"] == 0.1
        assert lidars[0]["pitch"] == -0.05
        assert lidars[0]["yaw"] == 1.57
    
    def test_upsert_sim_mode_with_pcd_path(self, lidar_repo):
        """Test upsert handles simulation mode configuration"""
        config = {
            "name": "Sim Sensor",
            "launch_args": "test",
            "mode": "sim",
            "pcd_path": "/path/to/test.pcd"
        }
        
        lidar_repo.upsert(config)
        lidars = lidar_repo.list()
        
        assert lidars[0]["mode"] == "sim"
        assert lidars[0]["pcd_path"] == "/path/to/test.pcd"
