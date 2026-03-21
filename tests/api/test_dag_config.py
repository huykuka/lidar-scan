"""TDD Tests for GET /api/v1/dag/config and PUT /api/v1/dag/config endpoints.

These tests are written BEFORE the implementation (TDD).
All tests must pass after the implementation is complete.

No user/session/version concurrency logic — last-write-wins with simple
optimistic locking via config_version integer.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_payload(node_id: str = "node001", name: str = "Test Sensor") -> Dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "type": "sensor",
        "category": "sensor",
        "enabled": True,
        "visible": True,
        "config": {"lidar_type": "multiscan", "hostname": "192.168.1.10", "port": 2115},
        "pose": None,
        "x": 100.0,
        "y": 200.0,
    }


def _edge_payload(
    edge_id: str = "edge001",
    source: str = "node001",
    target: str = "node002",
) -> Dict[str, Any]:
    return {
        "id": edge_id,
        "source_node": source,
        "source_port": "out",
        "target_node": target,
        "target_port": "in",
    }


def _put_body(base_version: int = 0, nodes=None, edges=None) -> Dict[str, Any]:
    return {
        "base_version": base_version,
        "nodes": nodes if nodes is not None else [],
        "edges": edges if edges is not None else [],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/dag/config
# ---------------------------------------------------------------------------


class TestGetDagConfig:
    """Tests for GET /api/v1/dag/config"""

    def test_get_returns_empty_dag_for_fresh_db(self, client):
        """Fresh DB must return empty nodes/edges with version=0."""
        resp = client.get("/api/v1/dag/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []
        assert data["config_version"] == 0

    def test_get_returns_correct_version_and_nodes(self, client):
        """Seed DB with 2 nodes + 1 edge via PUT /dag/config and verify GET returns them."""
        seed_nodes = [
            {"id": "aaa", "name": "Sensor A", "type": "sensor", "category": "sensor",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "bbb", "name": "Fusion B", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
        ]
        seed_edge = {
            "id": "e1", "source_node": "aaa", "source_port": "out",
            "target_node": "bbb", "target_port": "in",
        }
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            seed_resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=0, nodes=seed_nodes, edges=[seed_edge]),
            )
        assert seed_resp.status_code == 200

        resp = client.get("/api/v1/dag/config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        node_ids = {n["id"] for n in data["nodes"]}
        assert node_ids == {"aaa", "bbb"}

    def test_version_is_integer(self, client):
        """config_version must be a plain integer (not float/string)."""
        resp = client.get("/api/v1/dag/config")
        assert resp.status_code == 200
        cv = resp.json()["config_version"]
        assert isinstance(cv, int)
        assert not isinstance(cv, float)


# ---------------------------------------------------------------------------
# PUT /api/v1/dag/config
# ---------------------------------------------------------------------------


class TestSaveDagConfig:
    """Tests for PUT /api/v1/dag/config"""

    # ── Happy-path ──────────────────────────────────────────────────────────

    def test_save_success_increments_version(self, client):
        """PUT with base_version=0 must return config_version=1."""
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=0))
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_version"] == 1

    def test_save_replaces_nodes(self, client):
        """PUT with one node must leave only that node in DB (old nodes deleted)."""
        # Pre-seed two nodes via PUT /dag/config
        old_nodes = [
            {"id": "old1", "name": "Old A", "type": "sensor", "category": "sensor",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "old2", "name": "Old B", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
        ]
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            client.put("/api/v1/dag/config", json=_put_body(base_version=0, nodes=old_nodes))

        new_node = _node_payload("new1", "New Sensor")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=1, nodes=[new_node]))
        assert resp.status_code == 200

        # Only the new node should exist
        nodes_resp = client.get("/api/v1/nodes")
        node_ids = [n["id"] for n in nodes_resp.json()]
        assert node_ids == ["new1"]

    def test_save_replaces_edges(self, client):
        """PUT with 0 edges after seeding 2 edges must result in DB having 0 edges."""
        # Seed nodes and edges via PUT /dag/config
        seed_nodes = [
            {"id": "n1", "name": "N1", "type": "sensor", "category": "sensor",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "n2", "name": "N2", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "n3", "name": "N3", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
        ]
        seed_edges = [
            _edge_payload("e1", "n1", "n2"),
            _edge_payload("e2", "n1", "n3"),
        ]
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=0, nodes=seed_nodes, edges=seed_edges),
            )

        # Save with no edges, keeping just n1
        n1 = _node_payload("n1", "N1")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1], edges=[]),
            )
        assert resp.status_code == 200

        edges_resp = client.get("/api/v1/edges")
        assert edges_resp.json() == []

    def test_save_assigns_new_id_for_temp_nodes(self, client):
        """Node with id='__new__abc' must be persisted with a server-generated UUID."""
        temp_node = _node_payload("__new__abc", "Temp Node")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(nodes=[temp_node]))
        assert resp.status_code == 200
        data = resp.json()
        # node_id_map must map temp ID → new server ID
        assert "__new__abc" in data["node_id_map"]
        server_id = data["node_id_map"]["__new__abc"]
        assert server_id != "__new__abc"
        assert len(server_id) > 0

        # Verify the node was actually saved with the new ID
        nodes_resp = client.get("/api/v1/nodes")
        saved_ids = [n["id"] for n in nodes_resp.json()]
        assert server_id in saved_ids
        assert "__new__abc" not in saved_ids

    # ── 409 Conflict ────────────────────────────────────────────────────────

    def test_save_409_on_version_conflict(self, client):
        """If stored version is ahead, PUT must return 409."""
        # First save to bump version to 1
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            client.put("/api/v1/dag/config", json=_put_body(base_version=0))

        # Now try to save again with stale base_version=0
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=0))
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "conflict" in detail.lower() or "version" in detail.lower()

    def test_save_409_on_reload_in_progress(self, client):
        """If _reload_lock is held, PUT must return 409 immediately."""
        with patch(
            "app.api.v1.dag.service.node_manager._reload_lock"
        ) as mock_lock:
            mock_lock.locked.return_value = True
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=0))
        assert resp.status_code == 409
        assert "progress" in resp.json()["detail"].lower()

    # ── Reload trigger ───────────────────────────────────────────────────────

    def test_save_triggers_reload(self, client):
        """On success, node_manager.reload_config() must be called exactly once."""
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_reload:
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=0))
        assert resp.status_code == 200
        mock_reload.assert_called_once()

    # ── Error handling ───────────────────────────────────────────────────────

    def test_save_does_not_increment_on_db_error(self, client):
        """On DB error: version must stay unchanged, 500 returned."""
        with patch(
            "app.api.v1.dag.service.NodeRepository.upsert",
            side_effect=RuntimeError("DB error"),
        ), patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(nodes=[_node_payload()]),
            )
        assert resp.status_code == 500

        # Version must still be 0
        get_resp = client.get("/api/v1/dag/config")
        assert get_resp.json()["config_version"] == 0

    def test_save_422_on_missing_node_name(self, client):
        """PUT with a node missing the required 'name' field must return 422."""
        bad_node = {
            "id": "x1",
            # "name" intentionally omitted
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {},
        }
        resp = client.put("/api/v1/dag/config", json=_put_body(nodes=[bad_node]))
        assert resp.status_code == 422

    # ── node_id_map is empty when no temp IDs ────────────────────────────────

    def test_save_returns_empty_node_id_map_for_existing_ids(self, client):
        """When no temp IDs are used, node_id_map must be an empty dict."""
        node = _node_payload("existingnode001")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(nodes=[node]))
        assert resp.status_code == 200
        assert resp.json()["node_id_map"] == {}

    def test_no_ghost_records_after_put(self, client):
        """PUT with N nodes then PUT with N-1 nodes must leave exactly N-1 nodes and 0 dangling edges."""
        # First PUT: 3 nodes + 2 edges
        first_nodes = [
            {"id": "g1", "name": "Ghost 1", "type": "sensor", "category": "sensor",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "g2", "name": "Ghost 2", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "g3", "name": "Ghost 3", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
        ]
        first_edges = [
            _edge_payload("ge1", "g1", "g2"),
            _edge_payload("ge2", "g1", "g3"),
        ]
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            r1 = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=0, nodes=first_nodes, edges=first_edges),
            )
        assert r1.status_code == 200

        # Second PUT: only 2 nodes, no edges — g3 and both edges should disappear
        second_nodes = [
            {"id": "g1", "name": "Ghost 1", "type": "sensor", "category": "sensor",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
            {"id": "g2", "name": "Ghost 2", "type": "fusion", "category": "fusion",
             "enabled": True, "visible": True, "config": {}, "pose": None, "x": 0.0, "y": 0.0},
        ]
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            r2 = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=second_nodes, edges=[]),
            )
        assert r2.status_code == 200

        # Exactly 2 nodes, 0 edges — no ghost records
        nodes_resp = client.get("/api/v1/nodes")
        assert len(nodes_resp.json()) == 2
        node_ids = {n["id"] for n in nodes_resp.json()}
        assert node_ids == {"g1", "g2"}
        assert "g3" not in node_ids

        edges_resp = client.get("/api/v1/edges")
        assert edges_resp.json() == []
