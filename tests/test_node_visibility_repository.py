"""Tests for node visibility repository layer changes."""

import pytest
from app.repositories import NodeRepository


@pytest.fixture
def node_repo(tmp_path, monkeypatch):
    """Create a NodeRepository with test database."""
    db_file = tmp_path / "test_repo_visibility.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    
    from app.db.migrate import ensure_schema
    from app.db.session import init_engine
    
    engine = init_engine()
    ensure_schema(engine)
    
    return NodeRepository()


class TestNodeRepositoryVisibility:
    """Test NodeRepository methods with visibility support."""
    
    def test_upsert_reads_visible_field(self, node_repo):
        """Test that upsert() reads and stores visible field from input."""
        data = {
            "name": "Visible Test Node",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "visible": False,  # Explicitly set to False
            "config": {"test": "config"},
            "x": 150.0,
            "y": 250.0
        }
        
        node_id = node_repo.upsert(data)
        assert node_id is not None
        
        # Retrieve and verify visible field was stored
        retrieved = node_repo.get_by_id(node_id)
        assert retrieved is not None
        assert retrieved["visible"] is False
    
    def test_upsert_defaults_visible_true(self, node_repo):
        """Test that upsert() defaults visible to True when not provided."""
        data = {
            "name": "Default Visible Node",
            "type": "sensor",
            "category": "sensor", 
            "enabled": True,
            # visible not provided
            "config": {}
        }
        
        node_id = node_repo.upsert(data)
        retrieved = node_repo.get_by_id(node_id)
        assert retrieved["visible"] is True
    
    def test_upsert_updates_existing_visible(self, node_repo):
        """Test that upsert() updates visible field on existing nodes."""
        # Create initial node
        data = {
            "id": "update_test_node",
            "name": "Update Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {}
        }
        
        node_repo.upsert(data)
        
        # Update to invisible
        update_data = {
            "id": "update_test_node",
            "name": "Update Test",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "visible": False,  # Changed to False
            "config": {}
        }
        
        node_repo.upsert(update_data)
        retrieved = node_repo.get_by_id("update_test_node")
        assert retrieved["visible"] is False
    
    def test_upsert_preserves_existing_visible_when_not_specified(self, node_repo):
        """Test that upsert() preserves existing visible when not in update data."""
        # Create initial node with visible=False
        data = {
            "id": "preserve_test_node",
            "name": "Preserve Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {}
        }
        
        node_repo.upsert(data)
        
        # Update without visible field
        update_data = {
            "id": "preserve_test_node",
            "name": "Preserve Test Updated",  # Only change name
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            # visible not specified
            "config": {}
        }
        
        node_repo.upsert(update_data)
        retrieved = node_repo.get_by_id("preserve_test_node")
        assert retrieved["visible"] is False  # Should be preserved
        assert retrieved["name"] == "Preserve Test Updated"
    
    def test_set_visible_method_exists_and_works(self, node_repo):
        """Test that set_visible() method works correctly."""
        # First create a node
        data = {
            "id": "toggle_test_node",
            "name": "Toggle Test",
            "type": "sensor",
            "category": "sensor", 
            "enabled": True,
            "visible": True,
            "config": {}
        }
        
        node_repo.upsert(data)
        
        # Toggle to invisible
        node_repo.set_visible("toggle_test_node", False)
        retrieved = node_repo.get_by_id("toggle_test_node")
        assert retrieved["visible"] is False
        
        # Toggle back to visible
        node_repo.set_visible("toggle_test_node", True)
        retrieved = node_repo.get_by_id("toggle_test_node")
        assert retrieved["visible"] is True
    
    def test_set_visible_atomic_update_only_visible(self, node_repo):
        """Test that set_visible() only updates visible column, nothing else."""
        # Create node with known values
        original_data = {
            "id": "atomic_test_node",
            "name": "Atomic Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {"important": "config"},
            "x": 123.45,
            "y": 678.90
        }
        
        node_repo.upsert(original_data)
        
        # Use set_visible to change only visibility
        node_repo.set_visible("atomic_test_node", False)
        
        # Verify only visible changed, everything else preserved
        retrieved = node_repo.get_by_id("atomic_test_node")
        assert retrieved["visible"] is False  # Changed
        assert retrieved["name"] == "Atomic Test"  # Preserved
        assert retrieved["type"] == "sensor"  # Preserved
        assert retrieved["category"] == "sensor"  # Preserved
        assert retrieved["enabled"] is True  # Preserved
        assert retrieved["config"] == {"important": "config"}  # Preserved
        assert retrieved["x"] == 123.45  # Preserved
        assert retrieved["y"] == 678.90  # Preserved
    
    def test_set_visible_raises_value_error_for_missing_node(self, node_repo):
        """Test that set_visible() raises ValueError for non-existent node."""
        with pytest.raises(ValueError, match="Node .* not found"):
            node_repo.set_visible("nonexistent_node", True)
    
    def test_set_visible_rollback_on_exception(self, node_repo):
        """Test that set_visible() rolls back transaction on any exception."""
        # This test ensures the method follows the rollback pattern
        # We'll test by causing a constraint violation or similar
        
        # Create a node first
        data = {
            "id": "rollback_test_node",
            "name": "Rollback Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {}
        }
        
        node_repo.upsert(data)
        
        # Verify exception handling by testing nonexistent node
        original = node_repo.get_by_id("rollback_test_node")
        
        try:
            node_repo.set_visible("nonexistent_node", False)
        except ValueError:
            pass  # Expected
        
        # Verify original node wasn't affected by failed transaction
        after_error = node_repo.get_by_id("rollback_test_node")
        assert after_error["visible"] == original["visible"]


class TestRepositoryVisibilityIntegration:
    """Integration tests for repository visibility features."""
    
    def test_list_includes_visible_field(self, node_repo):
        """Test that list() includes visible field for all nodes."""
        # Create nodes with different visibility states
        visible_node = {
            "id": "visible_list_node",
            "name": "Visible Node",
            "type": "sensor",
            "category": "sensor",
            "visible": True
        }
        
        invisible_node = {
            "id": "invisible_list_node", 
            "name": "Invisible Node",
            "type": "sensor",
            "category": "sensor",
            "visible": False
        }
        
        node_repo.upsert(visible_node)
        node_repo.upsert(invisible_node)
        
        # List all nodes
        all_nodes = node_repo.list()
        
        # Find our test nodes
        visible_result = next(n for n in all_nodes if n["id"] == "visible_list_node")
        invisible_result = next(n for n in all_nodes if n["id"] == "invisible_list_node")
        
        assert "visible" in visible_result
        assert "visible" in invisible_result
        assert visible_result["visible"] is True
        assert invisible_result["visible"] is False
    
    def test_get_by_id_includes_visible_field(self, node_repo):
        """Test that get_by_id() includes visible field."""
        data = {
            "id": "get_by_id_test",
            "name": "Get By ID Test",
            "type": "sensor",
            "category": "sensor",
            "visible": False
        }
        
        node_repo.upsert(data)
        retrieved = node_repo.get_by_id("get_by_id_test")
        
        assert "visible" in retrieved
        assert retrieved["visible"] is False