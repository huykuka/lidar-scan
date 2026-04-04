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


# ---------------------------------------------------------------------------
# PUT /api/v1/dag/config — Phase 4: Diff Logic
# ---------------------------------------------------------------------------


class TestSaveDagConfigDiffLogic:
    """Tests for smart reload diff logic added in Phase 4.

    The service must classify each PUT into one of three change types:
    - topology    → full reload (node added/removed or edge added/removed)
    - param_change → selective reload per changed node
    - no_change    → no reload (only x/y/name changed)
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _seed(self, client, nodes, edges=None, base_version=0):
        """Seed the DB via PUT /dag/config, bypassing reload entirely."""
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ):
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=base_version, nodes=nodes, edges=edges or []),
            )
        assert resp.status_code == 200
        return resp.json()

    def _node(self, node_id="n1", hostname="192.168.1.10", x=100.0, y=200.0):
        return {
            "id": node_id,
            "name": f"Sensor {node_id}",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {"hostname": hostname, "port": 2115},
            "pose": None,
            "x": x,
            "y": y,
        }

    def _edge(self, edge_id="e1", source="n1", target="n2"):
        return {
            "id": edge_id,
            "source_node": source,
            "source_port": "out",
            "target_node": target,
            "target_port": "in",
        }

    # ------------------------------------------------------------------
    # Topology change → full reload
    # ------------------------------------------------------------------

    def test_save_topology_node_added_triggers_full_reload(self, client):
        """Adding a new node must trigger full reload (topology change)."""
        n1 = self._node("n1")
        self._seed(client, [n1])

        # Now add a second node
        n2 = self._node("n2")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1, n2], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_called_once()
        mock_selective.assert_not_called()
        data = resp.json()
        assert data["reload_mode"] == "full"
        assert data["reloaded_node_ids"] == []

    def test_save_topology_node_removed_triggers_full_reload(self, client):
        """Removing a node must trigger full reload (topology change)."""
        n1 = self._node("n1")
        n2 = self._node("n2")
        self._seed(client, [n1, n2])

        # Remove n2
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_called_once()
        mock_selective.assert_not_called()
        assert resp.json()["reload_mode"] == "full"

    def test_save_edge_added_triggers_full_reload(self, client):
        """Adding an edge must trigger full reload (topology change)."""
        n1 = self._node("n1")
        n2 = self._node("n2")
        self._seed(client, [n1, n2], edges=[])

        # Add an edge
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1, n2], edges=[self._edge()]),
            )

        assert resp.status_code == 200
        mock_full.assert_called_once()
        mock_selective.assert_not_called()
        assert resp.json()["reload_mode"] == "full"

    def test_save_edge_removed_triggers_full_reload(self, client):
        """Removing an edge must trigger full reload (topology change)."""
        n1 = self._node("n1")
        n2 = self._node("n2")
        self._seed(client, [n1, n2], edges=[self._edge()])

        # Remove the edge
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1, n2], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_called_once()
        mock_selective.assert_not_called()
        assert resp.json()["reload_mode"] == "full"

    # ------------------------------------------------------------------
    # Param change → selective reload
    # ------------------------------------------------------------------

    def test_save_param_change_triggers_selective_reload(self, client):
        """Changing a node's config param must trigger selective reload only for that node."""
        n1 = self._node("n1", hostname="192.168.1.10")
        self._seed(client, [n1])

        # Simulate the hash store being populated after a real load_config
        from app.services.nodes.config_hasher import compute_node_config_hash
        from app.services.nodes.instance import node_manager
        node_manager._config_hash_store.update("n1", compute_node_config_hash(n1))

        # Change hostname (runtime param)
        n1_changed = self._node("n1", hostname="10.0.0.99")
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1_changed], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_not_called()
        mock_selective.assert_called_once_with("n1")
        data = resp.json()
        assert data["reload_mode"] == "selective"
        assert "n1" in data["reloaded_node_ids"]

    def test_save_multiple_param_changes_selective_reload_all(self, client):
        """Multiple changed nodes must each get selective_reload_node called."""
        n1 = self._node("n1", hostname="192.168.1.10")
        n2 = self._node("n2", hostname="192.168.1.20")
        self._seed(client, [n1, n2])

        from app.services.nodes.config_hasher import compute_node_config_hash
        from app.services.nodes.instance import node_manager
        node_manager._config_hash_store.update("n1", compute_node_config_hash(n1))
        node_manager._config_hash_store.update("n2", compute_node_config_hash(n2))

        n1_c = self._node("n1", hostname="10.0.0.1")
        n2_c = self._node("n2", hostname="10.0.0.2")

        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1_c, n2_c], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_not_called()
        assert mock_selective.call_count == 2
        data = resp.json()
        assert data["reload_mode"] == "selective"
        assert set(data["reloaded_node_ids"]) == {"n1", "n2"}

    # ------------------------------------------------------------------
    # No change → no reload
    # ------------------------------------------------------------------

    def test_save_position_only_change_triggers_no_reload(self, client):
        """Changing only x/y (canvas position) must NOT trigger any reload."""
        n1 = self._node("n1", x=100.0, y=200.0)
        self._seed(client, [n1])

        from app.services.nodes.config_hasher import compute_node_config_hash
        from app.services.nodes.instance import node_manager
        node_manager._config_hash_store.update("n1", compute_node_config_hash(n1))

        # Same config, different x/y
        n1_moved = self._node("n1", x=999.0, y=888.0)
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1_moved], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_not_called()
        mock_selective.assert_not_called()
        data = resp.json()
        assert data["reload_mode"] == "none"
        assert data["reloaded_node_ids"] == []

    def test_save_name_only_change_triggers_no_reload(self, client):
        """Changing only the node name (display label) must NOT trigger any reload."""
        n1 = self._node("n1")
        self._seed(client, [n1])

        from app.services.nodes.config_hasher import compute_node_config_hash
        from app.services.nodes.instance import node_manager
        node_manager._config_hash_store.update("n1", compute_node_config_hash(n1))

        n1_renamed = {**n1, "name": "My Renamed Sensor"}
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ) as mock_full, patch(
            "app.api.v1.dag.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
        ) as mock_selective:
            resp = client.put(
                "/api/v1/dag/config",
                json=_put_body(base_version=1, nodes=[n1_renamed], edges=[]),
            )

        assert resp.status_code == 200
        mock_full.assert_not_called()
        mock_selective.assert_not_called()
        assert resp.json()["reload_mode"] == "none"

    # ------------------------------------------------------------------
    # Response shape
    # ------------------------------------------------------------------

    def test_save_response_includes_reload_mode_and_reloaded_node_ids(self, client):
        """Response must always contain reload_mode and reloaded_node_ids fields."""
        with patch(
            "app.api.v1.dag.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = client.put("/api/v1/dag/config", json=_put_body(base_version=0))
        assert resp.status_code == 200
        data = resp.json()
        assert "reload_mode" in data
        assert "reloaded_node_ids" in data
        assert isinstance(data["reloaded_node_ids"], list)

