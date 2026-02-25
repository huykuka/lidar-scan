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
        assert data["nodes"] == []
        assert data["edges"] == []
    
    def test_export_with_data(self, client):
        """Test exporting configuration with nodes and edges"""
        # Create some test data
        client.post("/api/v1/nodes", json={
            "id": "s1",
            "name": "Test Lidar",
            "type": "sensor",
            "category": "Input",
            "config": {"launch_args": "test_args"}
        })
        client.post("/api/v1/nodes", json={
            "id": "f1",
            "name": "Test Fusion",
            "type": "fusion",
            "category": "Processing",
            "config": {"topic": "fused"}
        })
        
        response = client.get("/api/v1/config/export")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 0
        names = {n["name"] for n in data["nodes"]}
        assert names == {"Test Lidar", "Test Fusion"}


class TestConfigurationImport:
    """Tests for configuration import"""
    
    def test_import_empty_configuration(self, client):
        """Test importing empty configuration"""
        response = client.post("/api/v1/config/import", json={
            "nodes": [],
            "edges": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["imported"]["nodes"] == 0
        assert data["imported"]["edges"] == 0
    
    def test_import_replace_mode(self, client):
        """Test import in replace mode (default)"""
        # Create existing data
        client.post("/api/v1/nodes", json={
            "id": "old_s1",
            "name": "Existing Lidar",
            "type": "sensor",
            "category": "Input"
        })
        
        # Import new configuration (should replace)
        response = client.post("/api/v1/config/import", json={
            "nodes": [
                {"id": "new_s1", "name": "New Lidar", "type": "sensor", "category": "Input"}
            ],
            "edges": [],
            "merge": False
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "replace"
        assert data["imported"]["nodes"] == 1
        
        # Verify old data is gone
        nodes_response = client.get("/api/v1/nodes")
        nodes = nodes_response.json()
        
        assert len(nodes) == 1
        assert nodes[0]["name"] == "New Lidar"
    
    def test_import_merge_mode(self, client):
        """Test import in merge mode"""
        # Create existing data
        client.post("/api/v1/nodes", json={
            "id": "old_s1",
            "name": "Existing Lidar",
            "type": "sensor",
            "category": "Input"
        })
        
        # Import new configuration (should merge)
        response = client.post("/api/v1/config/import", json={
            "nodes": [
                {"id": "new_s1", "name": "New Lidar", "type": "sensor", "category": "Input"}
            ],
            "edges": [],
            "merge": True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "merge"
        assert data["imported"]["nodes"] == 1
        
        # Verify both exist
        nodes_response = client.get("/api/v1/nodes")
        nodes = nodes_response.json()
        
        assert len(nodes) == 2
        names = {n["name"] for n in nodes}
        assert names == {"Existing Lidar", "New Lidar"}
    
    def test_import_with_edges(self, client):
        """Test importing edges"""
        response = client.post("/api/v1/config/import", json={
            "nodes": [],
            "edges": [
                {
                    "id": "edge_1",
                    "source_node": "n1",
                    "source_port": "out",
                    "target_node": "n2",
                    "target_port": "in"
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["imported"]["edges"] == 1
        
        # Verify edge was created
        edges_response = client.get("/api/v1/edges")
        edges = edges_response.json()
        
        assert len(edges) == 1
        assert edges[0]["id"] == "edge_1"


class TestConfigurationValidation:
    """Tests for configuration validation"""
    
    def test_validate_valid_configuration(self, client):
        """Test validating a valid configuration"""
        response = client.post("/api/v1/config/validate", json={
            "nodes": [
                {
                    "id": "node1",
                    "name": "Test Node",
                    "type": "sensor"
                }
            ],
            "edges": [
                {
                    "id": "e1",
                    "source_node": "node1",
                    "source_port": "out",
                    "target_node": "node2",
                    "target_port": "in"
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is True
        assert len(data["errors"]) == 0
        assert data["summary"]["nodes"] == 1
        assert data["summary"]["edges"] == 1
    
    def test_validate_missing_required_fields(self, client):
        """Test validation catches missing required fields"""
        response = client.post("/api/v1/config/validate", json={
            "nodes": [
                {"type": "sensor"}  # Missing name
            ],
            "edges": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is False
        assert len(data["errors"]) >= 1
        assert any("missing 'name'" in e for e in data["errors"])
    
    def test_validate_duplicate_ids(self, client):
        """Test validation catches duplicate IDs"""
        response = client.post("/api/v1/config/validate", json={
            "nodes": [
                {"id": "same_id", "name": "Node 1", "type": "sensor"},
                {"id": "same_id", "name": "Node 2", "type": "sensor"}
            ],
            "edges": []
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is False
        assert any("duplicate ID" in e for e in data["errors"])
