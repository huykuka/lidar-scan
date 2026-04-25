"""
Config hasher module for node configuration change detection.

Provides SHA-256 based hashing of node configuration data to detect
parameter changes without triggering full DAG reloads.

Spec: .opencode/plans/node-reload-improvement/backend-tasks.md § 1.1
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


# Keys included in the hash (affect runtime behavior)
_HASH_KEYS = ("id", "type", "category", "enabled", "visible", "config", "pose")

# Keys included in the config-only hash (excludes pose for hot-update detection)
_HASH_KEYS_NO_POSE = ("id", "type", "category", "enabled", "visible", "config")

# Keys explicitly excluded from the hash (canvas-only or display-only)
_EXCLUDED_KEYS = frozenset({"x", "y", "name"})


def compute_node_config_hash(node_data: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a node's runtime-relevant configuration.

    Included fields: ``id``, ``type``, ``category``, ``enabled``, ``visible``,
    ``config``, ``pose``.

    Excluded fields: ``x``, ``y`` (canvas position — cosmetic only),
    ``name`` (display label — does not affect node behavior).

    Args:
        node_data: Full node configuration dictionary from the database or request.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    # Build a canonical sub-dict with only the runtime-relevant keys
    canonical: Dict[str, Any] = {
        key: node_data.get(key)
        for key in _HASH_KEYS
    }

    # Serialize deterministically: sort_keys=True, default=str handles non-serializable values
    serialized = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_node_config_hash_no_pose(node_data: Dict[str, Any]) -> str:
    """Compute a config hash excluding pose — used to detect pose-only changes.

    When `compute_node_config_hash` differs but this hash matches, only the
    pose changed and a hot-update (no process restart) is sufficient.

    Args:
        node_data: Full node configuration dictionary.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    canonical: Dict[str, Any] = {
        key: node_data.get(key)
        for key in _HASH_KEYS_NO_POSE
    }
    serialized = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ConfigHashStore:
    """In-memory store for node_id → config hash mappings.

    Tracks the currently running configuration hash for each active node.
    Used by :class:`SelectiveReloadManager` to detect parameter changes
    without re-loading unchanged nodes.
    """

    def __init__(self) -> None:
        self._hashes: Dict[str, str] = {}

    def update(self, node_id: str, hash_val: str) -> None:
        """Store or overwrite the hash for a node.

        Args:
            node_id: Unique node identifier.
            hash_val: SHA-256 hex digest to store.
        """
        self._hashes[node_id] = hash_val

    def get(self, node_id: str) -> Optional[str]:
        """Retrieve the stored hash for a node.

        Args:
            node_id: Unique node identifier.

        Returns:
            Stored hash string, or ``None`` if not present.
        """
        return self._hashes.get(node_id)

    def remove(self, node_id: str) -> None:
        """Remove the hash entry for a node (no-op if absent).

        Args:
            node_id: Unique node identifier.
        """
        self._hashes.pop(node_id, None)

    def clear(self) -> None:
        """Remove all stored hashes (used before full config reload)."""
        self._hashes.clear()
