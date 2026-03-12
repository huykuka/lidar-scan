import pytest
from app.repositories import NodeRepository, EdgeRepository

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a test database with proper schema."""
    db_file = tmp_path / "test_repo.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    
    from app.db.migrate import ensure_schema
    from app.db.session import init_engine
    
    engine = init_engine()
    ensure_schema(engine)

def test_node_upsert_and_list(test_db):
    repo = NodeRepository()
    
    # Create
    config = {
        "id": "test_sensor_1",
        "name": "Test Sensor",
        "type": "sensor",
        "category": "Input",
        "config": {"launch_args": "foo.launch.py"}
    }
    node_id = repo.upsert(config)
    assert node_id == "test_sensor_1"
    
    # List
    nodes = repo.list()
    assert len([n for n in nodes if n["id"] == "test_sensor_1"]) == 1
    
    # Check that visible field is included and defaults to True
    test_node = next(n for n in nodes if n["id"] == "test_sensor_1")
    assert "visible" in test_node
    assert test_node["visible"] is True
    
    # Delete
    repo.delete("test_sensor_1")
    nodes_after = repo.list()
    assert len([n for n in nodes_after if n["id"] == "test_sensor_1"]) == 0

def test_edge_save_all(test_db):
    repo = EdgeRepository()
    
    edges = [
        {
            "id": "edge_1",
            "source_node": "node_1",
            "source_port": "out",
            "target_node": "node_2",
            "target_port": "in"
        }
    ]
    
    repo.save_all(edges)
    
    saved = repo.list()
    assert len([e for e in saved if e["id"] == "edge_1"]) == 1
    
    # Save empty should clear
    repo.save_all([])
    assert len(repo.list()) == 0
