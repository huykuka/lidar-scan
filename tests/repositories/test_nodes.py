import pytest
from app.repositories import NodeRepository, EdgeRepository

def test_node_upsert_and_list():
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
    
    # Delete
    repo.delete("test_sensor_1")
    nodes_after = repo.list()
    assert len([n for n in nodes_after if n["id"] == "test_sensor_1"]) == 0

def test_edge_save_all():
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
