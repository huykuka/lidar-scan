"""Tests for configuration import/export API."""

import json


class TestConfigurationExport:
    """Tests for configuration export"""
    
    def test_export_empty_configuration(self, client):
        """Test exporting empty configuration"""
        response = client.get("/api/v1/config/export")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment" in response.headers.get("content-disposition", "")
        
        data = response.json()
        assert "lidars" in data
        assert "fusions" in data
        assert data["lidars"] == []
        assert data["fusions"] == []
    
    def test_export_with_data(self, client):
        """Test exporting configuration with lidars and fusions"""
        # Create some test data
        client.post("/api/v1/lidars", json={
            "name": "Test Lidar",
            "launch_args": "test_args"
        })
        client.post("/api/v1/fusions", json={
            "name": "Test Fusion",
            "topic": "fused",
            "sensor_ids": ["s1", "s2"]
        })
        
        response = client.get("/api/v1/config/export")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["lidars"]) == 1
        assert len(data["fusions"]) == 1
        assert data["lidars"][0]["name"] == "Test Lidar"
        assert data["fusions"][0]["name"] == "Test Fusion"


class TestConfigurationImport:
    """Tests for configuration import"""
    
    def test_import_empty_configuration(self, client):
        """Test importing empty configuration"""
        response = client.post("/api/v1/config/import", json={
            "lidars": [],
            "fusions": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["imported"]["lidars"] == 0
        assert data["imported"]["fusions"] == 0
    
    def test_import_replace_mode(self, client):
        """Test import in replace mode (default)"""
        # Create existing data
        client.post("/api/v1/lidars", json={
            "name": "Existing Lidar",
            "launch_args": "args"
        })
        
        # Import new configuration (should replace)
        response = client.post("/api/v1/config/import", json={
            "lidars": [
                {"name": "New Lidar", "launch_args": "new_args"}
            ],
            "fusions": [],
            "merge": False
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "replace"
        assert data["imported"]["lidars"] == 1
        
        # Verify old data is gone
        lidars_response = client.get("/api/v1/lidars")
        lidars = lidars_response.json()["lidars"]
        
        assert len(lidars) == 1
        assert lidars[0]["name"] == "New Lidar"
    
    def test_import_merge_mode(self, client):
        """Test import in merge mode"""
        # Create existing data
        client.post("/api/v1/lidars", json={
            "name": "Existing Lidar",
            "launch_args": "args"
        })
        
        # Import new configuration (should merge)
        response = client.post("/api/v1/config/import", json={
            "lidars": [
                {"name": "New Lidar", "launch_args": "new_args"}
            ],
            "fusions": [],
            "merge": True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "merge"
        assert data["imported"]["lidars"] == 1
        
        # Verify both exist
        lidars_response = client.get("/api/v1/lidars")
        lidars = lidars_response.json()["lidars"]
        
        assert len(lidars) == 2
        names = {l["name"] for l in lidars}
        assert names == {"Existing Lidar", "New Lidar"}
    
    def test_import_with_fusions(self, client):
        """Test importing fusions"""
        response = client.post("/api/v1/config/import", json={
            "lidars": [],
            "fusions": [
                {
                    "name": "Test Fusion",
                    "topic": "fused",
                    "sensor_ids": ["s1", "s2"]
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["imported"]["fusions"] == 1
        
        # Verify fusion was created
        fusions_response = client.get("/api/v1/fusions")
        fusions = fusions_response.json()["fusions"]
        
        assert len(fusions) == 1
        assert fusions[0]["name"] == "Test Fusion"


class TestConfigurationValidation:
    """Tests for configuration validation"""
    
    def test_validate_valid_configuration(self, client):
        """Test validating a valid configuration"""
        response = client.post("/api/v1/config/validate", json={
            "lidars": [
                {
                    "name": "Test Lidar",
                    "launch_args": "args"
                }
            ],
            "fusions": [
                {
                    "name": "Test Fusion",
                    "topic": "fused",
                    "sensor_ids": ["s1"]
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is True
        assert len(data["errors"]) == 0
        assert data["summary"]["lidars"] == 1
        assert data["summary"]["fusions"] == 1
    
    def test_validate_missing_required_fields(self, client):
        """Test validation catches missing required fields"""
        response = client.post("/api/v1/config/validate", json={
            "lidars": [
                {"launch_args": "args"}  # Missing name
            ],
            "fusions": [
                {"topic": "fused", "sensor_ids": []}  # Missing name
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is False
        assert len(data["errors"]) >= 2
        assert any("missing 'name'" in e for e in data["errors"])
    
    def test_validate_duplicate_ids(self, client):
        """Test validation catches duplicate IDs"""
        response = client.post("/api/v1/config/validate", json={
            "lidars": [
                {"id": "same_id", "name": "Lidar 1", "launch_args": "args1"},
                {"id": "same_id", "name": "Lidar 2", "launch_args": "args2"}
            ],
            "fusions": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is False
        assert any("duplicate ID" in e for e in data["errors"])
    
    def test_validate_duplicate_topic_prefix_warning(self, client):
        """Test validation warns about duplicate topic_prefix"""
        response = client.post("/api/v1/config/validate", json={
            "lidars": [
                {"name": "Lidar 1", "launch_args": "args1", "topic_prefix": "same"},
                {"name": "Lidar 2", "launch_args": "args2", "topic_prefix": "same"}
            ],
            "fusions": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be valid but with warnings
        assert data["valid"] is True
        assert len(data["warnings"]) > 0
        assert any("duplicate topic_prefix" in w for w in data["warnings"])
