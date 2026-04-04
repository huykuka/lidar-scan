"""
TDD Tests for ConfigHasher and ConfigHashStore.

Phase 7.1 — written BEFORE implementation per strict TDD.
"""
from __future__ import annotations

import pytest
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_node() -> Dict[str, Any]:
    return {
        "id": "abc12345",
        "type": "sensor",
        "category": "sensor",
        "enabled": True,
        "visible": True,
        "config": {
            "lidar_type": "multiscan",
            "hostname": "192.168.1.10",
            "port": 2115,
        },
        "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        # These should be EXCLUDED from hash:
        "x": 100.0,
        "y": 200.0,
        "name": "MultiScan Left",
    }


# ---------------------------------------------------------------------------
# compute_node_config_hash
# ---------------------------------------------------------------------------

class TestComputeNodeConfigHash:
    """Unit tests for compute_node_config_hash function."""

    def test_hash_is_deterministic(self):
        """Same input must produce same hash on every call."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node = _base_node()
        h1 = compute_node_config_hash(node)
        h2 = compute_node_config_hash(node)
        assert h1 == h2
        # Must be a 64-char hex SHA-256 digest
        assert len(h1) == 64
        assert all(c in "0123456789abcdef" for c in h1)

    def test_hash_differs_on_config_change(self):
        """Modifying config.hostname must produce a different hash."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["config"]["hostname"] = "10.0.0.99"
        assert compute_node_config_hash(node_a) != compute_node_config_hash(node_b)

    def test_hash_ignores_canvas_position_x(self):
        """x (canvas position) must NOT affect the hash."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["x"] = 999.0
        assert compute_node_config_hash(node_a) == compute_node_config_hash(node_b)

    def test_hash_ignores_canvas_position_y(self):
        """y (canvas position) must NOT affect the hash."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["y"] = 9999.0
        assert compute_node_config_hash(node_a) == compute_node_config_hash(node_b)

    def test_hash_ignores_name(self):
        """name must NOT affect the hash (does not affect runtime behavior)."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["name"] = "Totally Different Name"
        assert compute_node_config_hash(node_a) == compute_node_config_hash(node_b)

    def test_hash_differs_on_pose_change(self):
        """Modifying pose.yaw must produce a different hash."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["pose"]["yaw"] = 1.57
        assert compute_node_config_hash(node_a) != compute_node_config_hash(node_b)

    def test_hash_differs_on_enabled_toggle(self):
        """Setting enabled=False must produce a different hash than enabled=True."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["enabled"] = False
        assert compute_node_config_hash(node_a) != compute_node_config_hash(node_b)

    def test_hash_differs_on_visible_toggle(self):
        """Setting visible=False must produce a different hash than visible=True."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["visible"] = False
        assert compute_node_config_hash(node_a) != compute_node_config_hash(node_b)

    def test_hash_differs_on_type_change(self):
        """Changing node type must produce a different hash."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["type"] = "fusion"
        assert compute_node_config_hash(node_a) != compute_node_config_hash(node_b)

    def test_hash_stable_when_only_x_y_name_change(self):
        """Only changing x, y, and name together must yield the same hash (all excluded)."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node_a = _base_node()
        node_b = _base_node()
        node_b["x"] = 555.0
        node_b["y"] = 666.0
        node_b["name"] = "Renamed Node"
        assert compute_node_config_hash(node_a) == compute_node_config_hash(node_b)

    def test_hash_works_with_none_pose(self):
        """Node with pose=None must hash without error."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node = _base_node()
        node["pose"] = None
        h = compute_node_config_hash(node)
        assert len(h) == 64

    def test_hash_works_with_missing_optional_fields(self):
        """Node missing x, y, name, pose must still hash without error."""
        from app.services.nodes.config_hasher import compute_node_config_hash
        node = {
            "id": "minimal001",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {},
        }
        h = compute_node_config_hash(node)
        assert len(h) == 64


# ---------------------------------------------------------------------------
# ConfigHashStore
# ---------------------------------------------------------------------------

class TestConfigHashStore:
    """Unit tests for ConfigHashStore lifecycle."""

    def test_store_update_and_get(self):
        """update() then get() must return the stored hash."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        store.update("node_a", "deadbeef" * 8)
        assert store.get("node_a") == "deadbeef" * 8

    def test_store_get_missing_returns_none(self):
        """get() for unknown node_id must return None."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        assert store.get("nonexistent") is None

    def test_store_remove(self):
        """remove() must delete the entry so get() returns None."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        store.update("node_a", "abc123")
        store.remove("node_a")
        assert store.get("node_a") is None

    def test_store_remove_nonexistent_is_noop(self):
        """remove() on an absent key must not raise."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        store.remove("never_existed")  # Must not raise

    def test_store_clear(self):
        """clear() must remove all entries."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        store.update("a", "hash_a")
        store.update("b", "hash_b")
        store.update("c", "hash_c")
        store.clear()
        assert store.get("a") is None
        assert store.get("b") is None
        assert store.get("c") is None

    def test_store_update_overwrites(self):
        """Calling update() twice for the same node_id must overwrite the old hash."""
        from app.services.nodes.config_hasher import ConfigHashStore
        store = ConfigHashStore()
        store.update("node_a", "oldhash")
        store.update("node_a", "newhash")
        assert store.get("node_a") == "newhash"
